#!/usr/bin/env python3
"""Headless halftone: grayscale/colour image -> pure black/white PNG (numpy + Pillow). Same algorithms and presets as the HTML viewer (assets/halftone_engine.js).

Usage:
  halftone.py in.png out.png [--preset newsprint] [--width 800] [--method am --param cell=6 --param angle=45 --param shape=round]
              [--brightness 0] [--contrast 0] [--gamma 1] [--blur 0] [--sharpen 0] [--invert] [--linear] [--json]
  halftone.py --list-presets
Library: halftone_image(path_or_array, preset='newsprint', width=800, ...) -> (bits uint8 1=white 0=black, info dict);  save_bw_png(bits, path)
Output PNG is 1-bit (pure #000000 / #FFFFFF). Alpha is flattened onto white first."""
import argparse, json, math, os, sys
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
PRESETS = json.load(open(os.path.join(os.path.dirname(HERE), "assets", "presets.json"), encoding="utf-8"))
KERNELS = {
    "floyd": (16, [(1, 0, 7), (-1, 1, 3), (0, 1, 5), (1, 1, 1)]),
    "jarvis": (48, [(1, 0, 7), (2, 0, 5), (-2, 1, 3), (-1, 1, 5), (0, 1, 7), (1, 1, 5), (2, 1, 3), (-2, 2, 1), (-1, 2, 3), (0, 2, 5), (1, 2, 3), (2, 2, 1)]),
    "stucki": (42, [(1, 0, 8), (2, 0, 4), (-2, 1, 2), (-1, 1, 4), (0, 1, 8), (1, 1, 4), (2, 1, 2), (-2, 2, 1), (-1, 2, 2), (0, 2, 4), (1, 2, 2), (2, 2, 1)]),
    "atkinson": (8, [(1, 0, 1), (2, 0, 1), (-1, 1, 1), (0, 1, 1), (1, 1, 1), (0, 2, 1)]),
    "burkes": (32, [(1, 0, 8), (2, 0, 4), (-2, 1, 2), (-1, 1, 4), (0, 1, 8), (1, 1, 4), (2, 1, 2)]),
    "sierra": (32, [(1, 0, 5), (2, 0, 3), (-2, 1, 2), (-1, 1, 4), (0, 1, 5), (1, 1, 4), (2, 1, 2), (-1, 2, 2), (0, 2, 3), (1, 2, 2)]),
    "sierra2": (16, [(1, 0, 4), (2, 0, 3), (-2, 1, 1), (-1, 1, 2), (0, 1, 3), (1, 1, 2), (2, 1, 1)]),
    "sierraLite": (4, [(1, 0, 2), (-1, 1, 1), (0, 1, 1)]),
}
SHAPES = ["round", "ellipse", "square", "diamond", "line", "cross", "ring"]
GRIDS = ["square", "hex", "radial", "ring"]
HEXH = 0.8660254037844386

def box_blur(a, r):
    r = int(round(r))
    if r < 1: return a.astype(np.float32).copy()
    out = a.astype(np.float64)
    for axis in (0, 1):
        pad = [(0, 0), (0, 0)]; pad[axis] = (r + 1, r)
        p = np.pad(out, pad, mode="edge"); c = np.cumsum(p, axis=axis, dtype=np.float64)
        n = 2 * r + 1
        if axis == 0: out = (c[n:, :] - c[:-n, :]) / n
        else: out = (c[:, n:] - c[:, :-n]) / n
    return out.astype(np.float32)

def prepare(lum, brightness=0.0, contrast=0.0, gamma=1.0, blur=0, sharpen=0.0, invert=False, linear=False, normalize=False, bp=0.0, wp=1.0, wave=None, waveN=1):
    t = lum.astype(np.float32)
    if blur and blur > 0: t = box_blur(box_blur(t, blur), blur)
    if sharpen and sharpen > 0: b = box_blur(box_blur(t, 2), 2); t = t + sharpen * (t - b)
    if normalize:                                                      # stretch the 0.5%..99.5% tone range (1024-bin histogram), same as the JS engine
        n = t.size; bins = np.minimum(1023, np.floor(np.clip(t, 0, 1).astype(np.float64) * 1024).astype(np.int64)); hist = np.bincount(bins.ravel(), minlength=1024)
        lo, hi, acc = 0.0, 1.0, 0
        for i in range(1024):
            acc += hist[i]
            if acc >= 0.005 * n: lo = i / 1024; break
        acc = 0
        for i in range(1023, -1, -1):
            acc += hist[i]
            if acc >= 0.005 * n: hi = (i + 1) / 1024; break
        if hi > lo: t = ((t - lo) / (hi - lo)).astype(np.float32)
    if bp > 0 or wp < 1: t = ((t - bp) / max(1e-3, wp - bp)).astype(np.float32)
    cf = 4.0 ** (contrast / 100.0); ig = 1.0 / max(0.05, gamma)
    v = np.clip((t + brightness - 0.5) * cf + 0.5, 0, 1) ** ig
    if wave in ("saw", "tri"):
        wn = max(1.0, float(waveN)); sv = v * wn; m = v < 1
        if wave == "saw": v = np.where(m, sv - np.floor(sv), v)
        else: q = sv - 2 * np.floor(sv / 2); v = np.where(m, np.where(q <= 1, q, 2 - q), v)
    if invert: v = 1 - v
    if linear: v = np.where(v <= 0.04045, v / 12.92, ((v + 0.055) / 1.055) ** 2.4)
    return v.astype(np.float32)

def mulberry32(seed):
    a = [seed & 0xFFFFFFFF]
    def nxt():
        a[0] = (a[0] + 0x6D2B79F5) & 0xFFFFFFFF; t = a[0]
        t = ((t ^ (t >> 15)) * (1 | t)) & 0xFFFFFFFF
        t = ((t + (((t ^ (t >> 7)) * (61 | t)) & 0xFFFFFFFF)) & 0xFFFFFFFF) ^ t
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296.0
    return nxt

def bayer_matrix(n):
    m = np.zeros((1, 1), dtype=np.int64); s = 1
    while s < n:
        m = np.block([[4 * m, 4 * m + 2], [4 * m + 3, 4 * m + 1]]); s *= 2
    return m

def _tile(mat, h, w):
    n = mat.shape[0]
    return np.tile(mat, (h // n + 1, w // mat.shape[1] + 1))[:h, :w]

def threshold(tone, p): return (tone > p.get("threshold", 0.5)).astype(np.uint8)
def bayer(tone, p):
    n = int(p.get("size", 4)); m = (bayer_matrix(n) + 0.5) / (n * n); return (tone > _tile(m, *tone.shape)).astype(np.uint8)

_BLUE = None
def blue_noise_matrix():
    global _BLUE
    if _BLUE is not None: return _BLUE
    N, n, sigma, R = 64, 64 * 64, 1.5, 6
    rnd = mulberry32(12345)
    kern = [(dx, dy, math.exp(-(dx * dx + dy * dy) / (2 * sigma * sigma))) for dy in range(-R, R + 1) for dx in range(-R, R + 1)]
    E = np.zeros(n); b = np.zeros(n, dtype=bool)
    def toggle(idx, on):
        px, py = idx % N, idx // N; sg = 1.0 if on else -1.0; b[idx] = on
        for dx, dy, wgt in kern: E[((py + dy) % N) * N + (px + dx) % N] += sg * wgt
    tight = lambda: int(np.argmax(np.where(b, E, -1.0)))
    void = lambda: int(np.argmin(np.where(b, 1e18, E)))
    ones = round(n * 0.1); order = list(range(n))
    for i in range(n - 1, 0, -1):
        j = int(math.floor(rnd() * (i + 1))); order[i], order[j] = order[j], order[i]
    for i in range(ones): toggle(order[i], True)
    for _ in range(5000):
        c = tight(); toggle(c, False); v = void(); toggle(c, True)
        if v == c: break
        toggle(c, False); toggle(v, True)
    rank = np.zeros(n, dtype=np.int64); proto = b.copy()
    for r in range(ones - 1, -1, -1):
        c = tight(); toggle(c, False); rank[c] = r
    b[:] = False; E[:] = 0
    for i in range(n):
        if proto[i]: toggle(i, True)
    for r in range(ones, n):
        v = void(); rank[v] = r; toggle(v, True)
    _BLUE = rank.reshape(N, N); return _BLUE

def blue(tone, p): m = (blue_noise_matrix() + 0.5) / 4096.0; return (tone > _tile(m, *tone.shape)).astype(np.uint8)
def ign(tone, p):
    h, w = tone.shape; y, x = np.mgrid[0:h, 0:w].astype(np.float64); f = (0.06711056 * x + 0.00583715 * y) % 1.0
    return (tone > (52.9829189 * f) % 1.0).astype(np.uint8)
def white(tone, p):
    r = mulberry32(int(p.get("seed", 1))); flat = np.array([r() for _ in range(tone.size)]).reshape(tone.shape); return (tone > flat).astype(np.uint8)

def diffusion(tone, p):
    d, taps = KERNELS[p.get("kernel", "floyd")]; h, w = tone.shape; buf = tone.astype(np.float64).copy(); out = np.zeros((h, w), dtype=np.uint8)
    th, amt, serp = p.get("threshold", 0.5), p.get("amount", 1.0), p.get("serpentine", True)
    for y in range(h):
        rev = serp and (y & 1)
        xs = range(w - 1, -1, -1) if rev else range(w); st = -1 if rev else 1
        for x in xs:
            old = buf[y, x]; nv = 1 if old > th else 0; err = (old - nv) * amt; out[y, x] = nv
            for dx, dy, wt in taps:
                xx, yy = x + dx * st, y + dy
                if 0 <= xx < w and yy < h: buf[yy, xx] += err * wt / d
    return out

def hilbert_d2xy(n, d):
    x = y = 0; t = d; s = 1
    while s < n:
        rx = 1 & (t >> 1); ry = 1 & (t ^ rx)
        if ry == 0:
            if rx == 1: x = s - 1 - x; y = s - 1 - y
            x, y = y, x
        x += s * rx; y += s * ry; t >>= 2; s *= 2
    return x, y

def riemersma(tone, p):
    h, w = tone.shape; hist = max(2, int(round(p.get("history", 16)))); amt, th = p.get("amount", 1.0), p.get("threshold", 0.5)
    wt = [(1 / 16) ** (j / (hist - 1)) for j in range(hist)]; sm = sum(wt); q = [0.0] * hist; head = 0
    n = 1
    while n < max(w, h): n *= 2
    out = np.zeros((h, w), dtype=np.uint8)
    for d in range(n * n):
        x, y = hilbert_d2xy(n, d)
        if x >= w or y >= h: continue
        acc = sum(q[(head - j) % hist] * wt[j] for j in range(hist)) / sm * amt
        v = float(tone[y, x]) + acc; nv = 1 if v > th else 0; out[y, x] = nv; head = (head + 1) % hist; q[head] = v - nv
    return out

def spot_g(shape, fx, fy):
    return {"ellipse": np.sqrt(fx * fx + (fy / 0.6) * (fy / 0.6)), "square": np.maximum(abs(fx), abs(fy)), "diamond": abs(fx) + abs(fy), "line": abs(fy), "cross": np.minimum(abs(fx), abs(fy)),
            "ring": abs(np.sqrt(fx * fx + fy * fy) - 0.33)}.get(shape, np.sqrt(fx * fx + fy * fy))

_LUT = {}
def spot_lut(shape, hexgrid=False):
    key = (shape, hexgrid)
    if key in _LUT: return _LUT[key]
    N = 64; span = 1.2 if hexgrid else 1.0; y, x = np.mgrid[0:N, 0:N]; fx = (x + 0.5) / N * span - span / 2; fy = (y + 0.5) / N * span - span / 2
    inside = (abs(fx) <= 0.5) & (abs(0.5 * fx + HEXH * fy) <= 0.5) & (abs(-0.5 * fx + HEXH * fy) <= 0.5) if hexgrid else np.ones((N, N), bool)
    g = (spot_g(shape, fx, fy) + 1e-9 * (y * N + x)).ravel(); ins = np.flatnonzero(inside.ravel()); order = ins[np.argsort(g[ins], kind="stable")]
    thr = np.ones(N * N); thr[order] = (np.arange(len(order)) + 0.5) / len(order)
    _LUT[key] = thr.reshape(N, N); return _LUT[key]

def bilinear_np(a, x, y):
    h, w = a.shape; x = np.clip(x, 0, w - 1); y = np.clip(y, 0, h - 1); x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int); x1, y1 = np.minimum(w - 1, x0 + 1), np.minimum(h - 1, y0 + 1); fx, fy = x - x0, y - y0
    return (a[y0, x0] * (1 - fx) + a[y0, x1] * fx) * (1 - fy) + (a[y1, x0] * (1 - fx) + a[y1, x1] * fx) * fy

def _hash2(ix, iy, seed):
    M = 0xFFFFFFFF; h = (ix * 374761393 + iy * 668265263 + seed * 1442695041) & M
    h = ((h ^ (h >> 13)) * 1274126177) & M; h = (h ^ (h >> 16)) & M; return h / 4294967296.0
def vnoise(x, y, seed):
    fx0, fy0 = np.floor(x), np.floor(y); ix, iy = fx0.astype(np.int64), fy0.astype(np.int64); fx, fy = x - fx0, y - fy0; u = fx * fx * (3 - 2 * fx); v = fy * fy * (3 - 2 * fy)
    a, b, c, d = _hash2(ix, iy, seed), _hash2(ix + 1, iy, seed), _hash2(ix, iy + 1, seed), _hash2(ix + 1, iy + 1, seed); top = a + (b - a) * u
    return top + ((c + (d - c) * u) - top) * v

def am(tone, p):
    h, w = tone.shape; cell = max(2.0, float(p.get("cell", 6))); ang = math.radians(float(p.get("angle", 0))); ca, sa = math.cos(ang), math.sin(ang); grid = p.get("grid", "square"); shape = "line" if grid == "ring" else p.get("shape", "round")
    resp, off, warp = float(p.get("response", 1)), float(p.get("offset", 0)), float(p.get("warp", 0)); wl = cell * max(1.0, float(p.get("warpScale", 4) or 4)); cx0, cy0 = float(p.get("cx", 0.5)) * w, float(p.get("cy", 0.5)) * h
    N = 64; TWO_PI = 2 * math.pi; lut = spot_lut(shape, grid == "hex"); yy, xx = np.mgrid[0:h, 0:w].astype(np.float64); ox, oy = xx + .5, yy + .5; px, py = ox.copy(), oy.copy()
    if warp > 0: px = ox + warp * cell * (2 * vnoise(ox / wl, oy / wl, 1) - 1); py = oy + warp * cell * (2 * vnoise(ox / wl, oy / wl, 2) - 1)
    ux, uy = px.copy(), py.copy()
    if grid == "square":
        sx = (px * ca + py * sa) / cell; sy = (-px * sa + py * ca) / cell; i, j = np.floor(sx), np.floor(sy); fx, fy = sx - i, sy - j; bx, by = (i + .5) * cell, (j + .5) * cell
        ux, uy = bx * ca - by * sa, bx * sa + by * ca; thr = lut[np.minimum(N - 1, (fy * N).astype(int)), np.minimum(N - 1, (fx * N).astype(int))]
    elif grid == "hex":
        hx = (px * ca + py * sa) / cell; hy = (-px * sa + py * ca) / cell; jf = hy / HEXH; i0, j0 = np.floor(hx - 0.5 * jf), np.floor(jf); bd = np.full(hx.shape, 1e18); bcx = np.zeros_like(hx); bcy = np.zeros_like(hx)
        for q in range(4):
            ii, jj = i0 + (q & 1), j0 + (q >> 1); cxl, cyl = ii + 0.5 * jj, jj * HEXH; d2 = (hx - cxl) ** 2 + (hy - cyl) ** 2; m = d2 < bd; bd = np.where(m, d2, bd); bcx = np.where(m, cxl, bcx); bcy = np.where(m, cyl, bcy)
        ddx, ddy = hx - bcx, hy - bcy; ux, uy = bcx * cell * ca - bcy * cell * sa, bcx * cell * sa + bcy * cell * ca
        thr = lut[np.clip(np.floor((ddy + 0.6) / 1.2 * N).astype(int), 0, N - 1), np.clip(np.floor((ddx + 0.6) / 1.2 * N).astype(int), 0, N - 1)]
    else:
        dxr, dyr = px - cx0, py - cy0; r = np.sqrt(dxr * dxr + dyr * dyr); th = np.arctan2(dyr, dxr) - ang
        for _ in range(2): th = np.where(th < 0, th + TWO_PI, th)
        for _ in range(2): th = np.where(th >= TWO_PI, th - TWO_PI, th)
        k = np.floor(r / cell); fy2 = r / cell - k; rc = (k + .5) * cell
        if grid == "radial":
            nn = np.maximum(1, np.floor(TWO_PI * rc / cell + 0.5)); aa = th / TWO_PI * nn; ia = np.floor(aa); fx2 = aa - ia; thc = (ia + .5) / nn * TWO_PI + ang
            ux, uy = cx0 + rc * np.cos(thc), cy0 + rc * np.sin(thc); thr = lut[np.minimum(N - 1, (fy2 * N).astype(int)), np.minimum(N - 1, (fx2 * N).astype(int))]
        else:
            ux, uy = cx0 + rc * np.cos(th + ang), cy0 + rc * np.sin(th + ang); thr = lut[np.minimum(N - 1, (fy2 * N).astype(int)), N >> 1]
    t = bilinear_np(box_blur(tone, cell * 0.5).astype(np.float64), ux - .5, uy - .5) if p.get("centre", True) is not False else tone.astype(np.float64)
    d = np.clip(1 - t, 0, 1)
    if resp != 1: d = d ** resp
    d = np.clip(d + off, 0, 1)
    return np.where(d > thr, 0, 1).astype(np.uint8)

def stipple(tone, p):
    h, w = tone.shape; smin = max(1.5, float(p.get("spacingMin", 4))); smax = max(smin, float(p.get("spacingMax", 12))); dot = max(0.2, float(p.get("dot", 1))); by_tone = p.get("sizeByTone", True) is not False
    relax = max(0, min(20, int(round(float(p.get("relax", 0)))))); rnd = mulberry32(int(p.get("seed", 1)) or 1); T = tone.astype(np.float64).ravel().tolist()
    def bil(x, y):
        x = min(w - 1, max(0, x)); y = min(h - 1, max(0, y)); x0 = int(math.floor(x)); y0 = int(math.floor(y)); x1 = min(w - 1, x0 + 1); y1 = min(h - 1, y0 + 1); fx = x - x0; fy = y - y0
        return (T[y0 * w + x0] * (1 - fx) + T[y0 * w + x1] * fx) * (1 - fy) + (T[y1 * w + x0] * (1 - fx) + T[y1 * w + x1] * fx) * fy
    def dens(x, y):
        d = 1 - bil(x - 0.5, y - 0.5); return 0.0 if d < 0 else (1.0 if d > 1 else d)
    cs = smin / math.sqrt(2); gw = int(math.ceil(w / cs)) + 1; gh = int(math.ceil(h / cs)) + 1; grid = [-1] * (gw * gh); xs, ys, rs, ds, active = [], [], [], [], []; MAXP = 700000
    def add(x, y):
        d = dens(x, y); i = len(xs); xs.append(x); ys.append(y); ds.append(d); rs.append(smax + (smin - smax) * d); grid[int(math.floor(y / cs)) * gw + int(math.floor(x / cs))] = i; active.append(i)
    add(rnd() * w, rnd() * h)
    while active and len(xs) < MAXP:
        ai = int(math.floor(rnd() * len(active))); pi = active[ai]; r0 = rs[pi]; ok = False; k = 0
        while k < 20 and not ok:
            k += 1
            while True:
                a = rnd() * 4 - 2; b = rnd() * 4 - 2; q = a * a + b * b
                if 1 <= q < 4: break
            cx = xs[pi] + a * r0; cy = ys[pi] + b * r0
            if cx < 0 or cy < 0 or cx >= w or cy >= h: continue
            dc = dens(cx, cy); rc = smax + (smin - smax) * dc; R = int(math.ceil((rc + smax) / 2 / cs)); gx = int(math.floor(cx / cs)); gy = int(math.floor(cy / cs)); free = True
            for yy in range(max(0, gy - R), min(gh - 1, gy + R) + 1):
                if not free: break
                for xx in range(max(0, gx - R), min(gw - 1, gx + R) + 1):
                    j = grid[yy * gw + xx]
                    if j < 0: continue
                    dx = cx - xs[j]; dy = cy - ys[j]; rr = (rc + rs[j]) / 2
                    if dx * dx + dy * dy < rr * rr: free = False; break
            if free: add(cx, cy); ok = True
        if not ok: active[ai] = active[-1]; active.pop()
    for _ in range(relax):
        hc = smax; hw = int(math.ceil(w / hc)) + 1; hh = int(math.ceil(h / hc)) + 1; bk = {}
        for i in range(len(xs)): bk.setdefault(int(math.floor(ys[i] / hc)) * hw + int(math.floor(xs[i] / hc)), []).append(i)
        nx, ny = xs[:], ys[:]
        for i in range(len(xs)):
            fxs = fys = 0.0; bx = int(math.floor(xs[i] / hc)); by = int(math.floor(ys[i] / hc))
            for oy in (-1, 0, 1):
                for ox in (-1, 0, 1):
                    cx2, cy2 = bx + ox, by + oy
                    if cx2 < 0 or cy2 < 0 or cx2 >= hw or cy2 >= hh: continue
                    for j2 in bk.get(cy2 * hw + cx2, ()):
                        if j2 == i: continue
                        ddx = xs[i] - xs[j2]; ddy = ys[i] - ys[j2]; d2 = ddx * ddx + ddy * ddy; rr2 = 0.6 * (rs[i] + rs[j2])
                        if d2 < rr2 * rr2 and d2 > 1e-18: dd = math.sqrt(d2); f = (rr2 - dd) * 0.25 / dd; fxs += ddx * f; fys += ddy * f
            nx[i] = min(w - 1e-6, max(0.0, xs[i] + fxs)); ny[i] = min(h - 1e-6, max(0.0, ys[i] + fys))
        xs, ys = nx, ny
        for i in range(len(xs)): ds[i] = dens(xs[i], ys[i]); rs[i] = smax + (smin - smax) * ds[i]
    out = np.ones((h, w), dtype=np.uint8)
    for n2 in range(len(xs)):
        if ds[n2] < 0.02: continue
        rad = dot * (rs[n2] * math.sqrt(1.7 * ds[n2] / math.pi) if by_tone else 0.45 * smin); r2 = rad * rad
        x0 = max(0, int(math.floor(xs[n2] - rad))); x1 = min(w - 1, int(math.ceil(xs[n2] + rad))); y0 = max(0, int(math.floor(ys[n2] - rad))); y1 = min(h - 1, int(math.ceil(ys[n2] + rad)))
        if x1 >= x0 and y1 >= y0:
            gx_, gy_ = np.meshgrid(np.arange(x0, x1 + 1) + 0.5 - xs[n2], np.arange(y0, y1 + 1) + 0.5 - ys[n2]); blk = out[y0:y1 + 1, x0:x1 + 1]; blk[(gx_ * gx_ + gy_ * gy_) <= r2] = 0
        out[int(math.floor(ys[n2])), int(math.floor(xs[n2]))] = 0
    return out

METHODS = {"threshold": threshold, "bayer": bayer, "blue": blue, "ign": ign, "white": white, "diffusion": diffusion, "riemersma": riemersma, "am": am, "stipple": stipple}

def halftone(method, params, tone):
    if method not in METHODS: raise ValueError(f"unknown halftone method: {method}")
    return METHODS[method](tone, params or {})

def load_luminance(src, width=None, max_side=4096):
    im = src if isinstance(src, Image.Image) else Image.open(src)
    im.load()
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        im = im.convert("RGBA"); bg = Image.new("RGBA", im.size, (255, 255, 255, 255)); bg.alpha_composite(im); im = bg
    im = im.convert("RGB")
    if width is None: width = min(im.width, max_side)
    width = int(width)
    if im.width != width: im = im.resize((width, max(1, round(im.height * width / im.width))), Image.LANCZOS)
    a = np.asarray(im, dtype=np.float32) / 255.0
    return (0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]).astype(np.float32)

def halftone_image(src, preset="newsprint", width=800, method=None, params=None, **tone):
    pr = next((q for q in PRESETS if q["id"] == preset), None)
    if method is None:
        if pr is None: raise ValueError(f"unknown preset {preset!r}; try --list-presets")
        method, params, base = pr["method"], dict(pr["params"], **(params or {})), dict(pr.get("tone", {}))
    else: params, base = dict(params or {}), {}
    base.update({k: v for k, v in tone.items() if v is not None})
    lum = load_luminance(src, width); t = prepare(lum, **{k: base[k] for k in ("brightness", "contrast", "gamma", "blur", "sharpen", "invert", "linear", "normalize", "bp", "wp", "wave", "waveN") if k in base})
    bits = halftone(method, params, t)
    return bits, dict(method=method, params=params, tone=base, width=int(bits.shape[1]), height=int(bits.shape[0]), ink_fraction=float(1 - bits.mean()))

def save_bw_png(bits, path):
    im = Image.fromarray((bits * 255).astype(np.uint8), "L").convert("1"); im.save(path, optimize=True); return path

def _kv(items):
    out = {}
    for it in items or []:
        k, _, v = it.partition("="); 
        try: out[k] = json.loads(v)
        except ValueError: out[k] = v
    return out

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", nargs="?"); ap.add_argument("output", nargs="?"); ap.add_argument("--preset", default="newsprint"); ap.add_argument("--width", type=int, default=None, help="output width in px (default 800; the threshold preset keeps the native width up to 2048)")
    ap.add_argument("--method"); ap.add_argument("--param", action="append"); ap.add_argument("--brightness", type=float); ap.add_argument("--contrast", type=float); ap.add_argument("--gamma", type=float)
    ap.add_argument("--blur", type=float); ap.add_argument("--sharpen", type=float); ap.add_argument("--invert", action="store_true", default=None); ap.add_argument("--linear", action="store_true", default=None)
    ap.add_argument("--normalize", action="store_true", default=None); ap.add_argument("--bp", type=float); ap.add_argument("--wp", type=float); ap.add_argument("--list-presets", action="store_true"); ap.add_argument("--json", action="store_true"); a = ap.parse_args(argv)
    if a.list_presets:
        for q in PRESETS: print(f"{q['id']:<12} {q['group']:<18} {q['name']}")
        return 0
    if not a.input or not a.output: ap.error("input and output are required")
    try:
        width = a.width
        if width is None:
            width = 800
            if a.preset == "threshold" and not a.method:
                with Image.open(a.input) as im0: width = min(im0.width, 2048)                  # block colours: keep the artwork's resolution
        bits, info = halftone_image(a.input, a.preset, width, a.method, _kv(a.param), brightness=a.brightness, contrast=a.contrast, gamma=a.gamma, blur=a.blur, sharpen=a.sharpen, invert=a.invert, linear=a.linear, normalize=a.normalize, bp=a.bp, wp=a.wp)
    except (OSError, ValueError) as e: print(f"halftone: {e}", file=sys.stderr); return 2
    save_bw_png(bits, a.output); info["output"] = a.output
    print(json.dumps(info, indent=2) if a.json else f"halftone: {a.output} ({info['width']}x{info['height']}, {info['method']}, ink {info['ink_fraction']:.1%})")
    return 0
if __name__ == "__main__": sys.exit(main())
