#!/usr/bin/env python3
"""Offline QR code generator: text -> pure black/white QR PNG (standard library only; no network, no pip).

QR Code Model 2 (ISO/IEC 18004): numeric / alphanumeric / UTF-8 byte mode, versions 1-40, error correction L/M/Q/H, all 8 masks with the standard penalty rules.
The payload is encoded exactly as given (never trimmed or normalised).

Usage:
  make_qr.py "https://example.com/a?b=1" -o qr.png [--ecc Q] [--module-px 12] [--quiet 4] [--min-version 1] [--mask N]
              [--size-mm 30 [--size-basis symbol|modules]] [--json]
Output PNG: 1-bit, #000000 modules on #FFFFFF, quiet zone included (default 4 modules, the minimum for reliable scanning).
--size-mm reports the physical sizes: by default N mm = the WHOLE symbol including the quiet zone (this Skill's convention); --size-basis modules = the dark-module square only.
Library:  make_qr(text, ecc='Q', min_version=1, mask=None) -> dict(matrix [rows of bools, True = dark], version, modules, ecc, mask, mode)
          qr_png(matrix, module_px=12, quiet=4) -> bytes     qr_report(info, module_px, quiet, size_mm, size_basis) -> dict
Exit code: 0 ok; 2 payload empty / too long / bad arguments."""
import argparse, json, struct, sys, zlib

ECC_IDX = {"L": 0, "M": 1, "Q": 2, "H": 3}
ECC_FMT = {"L": 1, "M": 0, "Q": 3, "H": 2}                                          # format-information bits
ECC_PER_BLOCK = {                                                                    # error-correction codewords per block, versions 1..40
    "L": [7, 10, 15, 20, 26, 18, 20, 24, 30, 18, 20, 24, 26, 30, 22, 24, 28, 30, 28, 28, 28, 28, 30, 30, 26, 28, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30],
    "M": [10, 16, 26, 18, 24, 16, 18, 22, 22, 26, 30, 22, 22, 24, 24, 28, 28, 26, 26, 26, 26, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28],
    "Q": [13, 22, 18, 26, 18, 24, 18, 22, 20, 24, 28, 26, 24, 20, 30, 24, 28, 28, 26, 30, 28, 30, 30, 30, 30, 28, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30],
    "H": [17, 28, 22, 16, 22, 28, 26, 26, 24, 28, 24, 28, 22, 24, 24, 30, 28, 28, 26, 28, 30, 24, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30]}
NUM_BLOCKS = {                                                                       # number of error-correction blocks, versions 1..40
    "L": [1, 1, 1, 1, 1, 2, 2, 2, 2, 4, 4, 4, 4, 4, 6, 6, 6, 6, 7, 8, 8, 9, 9, 10, 12, 12, 12, 13, 14, 15, 16, 17, 18, 19, 19, 20, 21, 22, 24, 25],
    "M": [1, 1, 1, 2, 2, 4, 4, 4, 5, 5, 5, 8, 9, 9, 10, 10, 11, 13, 14, 16, 17, 17, 18, 20, 21, 23, 25, 26, 28, 29, 31, 33, 35, 37, 38, 40, 43, 45, 47, 49],
    "Q": [1, 1, 2, 2, 4, 4, 6, 6, 8, 8, 8, 10, 12, 16, 12, 17, 16, 18, 21, 20, 23, 23, 25, 27, 29, 34, 34, 35, 38, 40, 43, 45, 48, 51, 53, 56, 59, 62, 65, 68],
    "H": [1, 1, 2, 4, 4, 4, 5, 6, 8, 8, 11, 11, 16, 16, 18, 16, 19, 21, 25, 25, 25, 34, 30, 32, 35, 37, 40, 42, 45, 48, 51, 54, 57, 60, 63, 66, 70, 74, 77, 81]}
ALNUM = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ $%*+-./:"


def _raw_modules(v):
    r = (16 * v + 128) * v + 64
    if v >= 2:
        n = v // 7 + 2; r -= (25 * n - 10) * n - 55
        if v >= 7: r -= 36
    return r

def _data_codewords(v, ecc): return _raw_modules(v) // 8 - ECC_PER_BLOCK[ecc][v - 1] * NUM_BLOCKS[ecc][v - 1]

def _align_positions(v):
    if v == 1: return []
    n = v // 7 + 2; size = v * 4 + 17; step = 26 if v == 32 else (v * 4 + n * 2 + 1) // (n * 2 - 2) * 2
    pos, out = size - 7, [6]
    for _ in range(n - 1): out.insert(1, pos); pos -= step
    return out

# ---- Reed-Solomon over GF(256), polynomial 0x11D
def _gf_mul(x, y):
    z = 0
    for i in range(7, -1, -1):
        z = (z << 1) ^ ((z >> 7) * 0x11D); z ^= ((y >> i) & 1) * x
    return z

def _rs_divisor(degree):
    res = [0] * (degree - 1) + [1]; root = 1
    for _ in range(degree):
        for j in range(degree):
            res[j] = _gf_mul(res[j], root)
            if j + 1 < degree: res[j] ^= res[j + 1]
        root = _gf_mul(root, 0x02)
    return res

def _rs_remainder(data, divisor):
    res = [0] * len(divisor)
    for b in data:
        f = b ^ res.pop(0); res.append(0)
        for i, c in enumerate(divisor): res[i] ^= _gf_mul(c, f)
    return res

# ---- data encoding
def _bits(val, n): return [(val >> i) & 1 for i in range(n - 1, -1, -1)]

def _segment(text):
    if text and all(c in "0123456789" for c in text): return "numeric"
    if text and all(c in ALNUM for c in text): return "alphanumeric"
    return "byte"

def _cc_bits(mode, v):
    k = 0 if v <= 9 else (1 if v <= 26 else 2)
    return {"numeric": (10, 12, 14), "alphanumeric": (9, 11, 13), "byte": (8, 16, 16)}[mode][k]

def _encode_data(text, mode, v):
    bits = []
    if mode == "numeric":
        bits += _bits(1, 4) + _bits(len(text), _cc_bits(mode, v))
        for i in range(0, len(text), 3): chunk = text[i:i + 3]; bits += _bits(int(chunk), len(chunk) * 3 + 1)
    elif mode == "alphanumeric":
        bits += _bits(2, 4) + _bits(len(text), _cc_bits(mode, v))
        for i in range(0, len(text) - 1, 2): bits += _bits(ALNUM.index(text[i]) * 45 + ALNUM.index(text[i + 1]), 11)
        if len(text) % 2: bits += _bits(ALNUM.index(text[-1]), 6)
    else:
        raw = text.encode("utf-8"); bits += _bits(4, 4) + _bits(len(raw), _cc_bits(mode, v))
        for b in raw: bits += _bits(b, 8)
    return bits

def _choose_version(text, mode, ecc, min_version):
    for v in range(max(1, min_version), 41):
        if len(_encode_data(text, mode, v)) <= _data_codewords(v, ecc) * 8: return v
    raise ValueError(f"payload too long for a QR code at error correction {ecc} (max version 40)")

def _codewords(text, mode, v, ecc):
    cap = _data_codewords(v, ecc) * 8; bits = _encode_data(text, mode, v)
    bits += [0] * min(4, cap - len(bits)); bits += [0] * (-len(bits) % 8)
    data = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    pad = 0xEC
    while len(data) * 8 < cap: data.append(pad); pad ^= 0xEC ^ 0x11
    nb, el, raw = NUM_BLOCKS[ecc][v - 1], ECC_PER_BLOCK[ecc][v - 1], _raw_modules(v) // 8
    nshort, slen, div, blocks, k = nb - raw % nb, raw // nb, _rs_divisor(el), [], 0
    for i in range(nb):
        dat = data[k:k + slen - el + (0 if i < nshort else 1)]; k += len(dat)
        ecc_cw = _rs_remainder(dat, div)
        if i < nshort: dat = dat + [0]                                                  # placeholder so block columns line up; dropped again when interleaving
        blocks.append(dat + ecc_cw)
    out = []
    for i in range(len(blocks[0])):
        for j, blk in enumerate(blocks):
            if i != slen - el or j >= nshort: out.append(blk[i])
    return out

# ---- matrix construction
class _Matrix:
    def __init__(self, v, ecc):
        self.v, self.ecc, self.size = v, ecc, v * 4 + 17
        self.m = [[False] * self.size for _ in range(self.size)]; self.fn = [[False] * self.size for _ in range(self.size)]
        self._draw_function_patterns()

    def _set(self, x, y, dark): self.m[y][x] = bool(dark); self.fn[y][x] = True

    def _draw_function_patterns(self):
        n = self.size
        for i in range(n): self._set(6, i, i % 2 == 0); self._set(i, 6, i % 2 == 0)
        for cx, cy in ((3, 3), (n - 4, 3), (3, n - 4)):
            for dy in range(-4, 5):
                for dx in range(-4, 5):
                    x, y, d = cx + dx, cy + dy, max(abs(dx), abs(dy))
                    if 0 <= x < n and 0 <= y < n: self._set(x, y, d not in (2, 4))
        pos = _align_positions(self.v)
        for i, cy in enumerate(pos):
            for j, cx in enumerate(pos):
                if (i == 0 and j == 0) or (i == 0 and j == len(pos) - 1) or (i == len(pos) - 1 and j == 0): continue
                for dy in range(-2, 3):
                    for dx in range(-2, 3): self._set(cx + dx, cy + dy, max(abs(dx), abs(dy)) != 1)
        self._draw_format(0); self._draw_version()

    def _draw_format(self, mask):
        data = ECC_FMT[self.ecc] << 3 | mask; rem = data
        for _ in range(10): rem = (rem << 1) ^ ((rem >> 9) * 0x537)
        bits = (data << 10 | rem) ^ 0x5412; n = self.size; b = lambda i: (bits >> i) & 1
        for i in range(6): self._set(8, i, b(i))
        self._set(8, 7, b(6)); self._set(8, 8, b(7)); self._set(7, 8, b(8))
        for i in range(9, 15): self._set(14 - i, 8, b(i))
        for i in range(8): self._set(n - 1 - i, 8, b(i))
        for i in range(8, 15): self._set(8, n - 15 + i, b(i))
        self._set(8, n - 8, True)

    def _draw_version(self):
        if self.v < 7: return
        rem = self.v
        for _ in range(12): rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
        bits = self.v << 12 | rem
        for i in range(18):
            a, b = self.size - 11 + i % 3, i // 3; self._set(a, b, (bits >> i) & 1); self._set(b, a, (bits >> i) & 1)

    def place(self, cw):
        n, i = self.size, 0
        for right in range(n - 1, 0, -2):
            if right <= 6: right -= 1
            for vert in range(n):
                for j in range(2):
                    x = right - j; y = n - 1 - vert if ((right + 1) & 2) == 0 else vert
                    if not self.fn[y][x] and i < len(cw) * 8: self.m[y][x] = ((cw[i >> 3] >> (7 - (i & 7))) & 1) == 1; i += 1

    def apply_mask(self, mask):
        f = (lambda x, y: (x + y) % 2 == 0, lambda x, y: y % 2 == 0, lambda x, y: x % 3 == 0, lambda x, y: (x + y) % 3 == 0, lambda x, y: (x // 3 + y // 2) % 2 == 0,
             lambda x, y: x * y % 2 + x * y % 3 == 0, lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0, lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0)[mask]
        for y in range(self.size):
            for x in range(self.size):
                if not self.fn[y][x] and f(x, y): self.m[y][x] = not self.m[y][x]

    def penalty(self):
        n, m, score = self.size, self.m, 0
        lines = [row for row in m] + [[m[y][x] for y in range(n)] for x in range(n)]
        pat1, pat2 = [1, 0, 1, 1, 1, 0, 1, 0, 0, 0, 0], [0, 0, 0, 0, 1, 0, 1, 1, 1, 0, 1]
        for line in lines:
            run = 1
            for i in range(1, n):
                if line[i] == line[i - 1]: run += 1
                else:
                    if run >= 5: score += 3 + run - 5
                    run = 1
            if run >= 5: score += 3 + run - 5
            li = [1 if c else 0 for c in line]
            for i in range(n - 10):
                w = li[i:i + 11]
                if w == pat1 or w == pat2: score += 40
        for y in range(n - 1):
            for x in range(n - 1):
                if m[y][x] == m[y][x + 1] == m[y + 1][x] == m[y + 1][x + 1]: score += 3
        dark = sum(sum(1 for c in row if c) for row in m); k = (abs(dark * 20 - n * n * 10) + n * n - 1) // (n * n) - 1
        return score + k * 10


def make_qr(text, ecc="Q", min_version=1, mask=None):
    """Return dict(matrix, version, modules, ecc, mask, mode). The payload is encoded verbatim."""
    ecc = str(ecc).upper()
    if ecc not in ECC_IDX: raise ValueError("ecc must be one of L, M, Q, H")
    if not isinstance(text, str) or text == "": raise ValueError("payload is empty")
    mode = _segment(text); v = _choose_version(text, mode, ecc, int(min_version)); cw = _codewords(text, mode, v, ecc)
    if mask is not None and not 0 <= int(mask) <= 7: raise ValueError("mask must be 0..7")
    best = None
    for mk in ([int(mask)] if mask is not None else range(8)):
        q = _Matrix(v, ecc); q.place(cw); q.apply_mask(mk); q._draw_format(mk); sc = q.penalty() if mask is None else 0
        if best is None or sc < best[0]: best = (sc, mk, q)
    q = best[2]
    return dict(matrix=[row[:] for row in q.m], version=v, modules=q.size, ecc=ecc, mask=best[1], mode=mode)


# ---- PNG output (1-bit grayscale, white background)
def qr_png(matrix, module_px=12, quiet=4):
    n, px = len(matrix), int(module_px); side = (n + 2 * quiet) * px; rb = (side + 7) // 8
    rows = []
    for y in range(side):
        my = y // px - quiet
        if not 0 <= my < n: rows.append(b"\x00" + b"\xff" * rb); continue                                   # quiet-zone row: all white
        line = bytearray(b"\xff" * rb)
        for mx in range(n):
            if matrix[my][mx]:
                x0 = (mx + quiet) * px
                for x in range(x0, x0 + px): line[x >> 3] &= ~(0x80 >> (x & 7)) & 0xFF
        rows.append(b"\x00" + bytes(line))
    raw = b"".join(rows)
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", side, side, 1, 0, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def qr_report(info, module_px=12, quiet=4, size_mm=None, size_basis="symbol"):
    n = info["modules"]; sym = n + 2 * quiet; rep = dict(version=info["version"], modules=n, symbol_modules=sym, quiet_modules=quiet, ecc=info["ecc"], mask=info["mask"], mode=info["mode"],
                                                          png_px=sym * module_px, module_px=module_px, warnings=[])
    if module_px < 6: rep["warnings"].append("fewer than 6 px per module: raise --module-px so the texture stays scannable")
    if quiet < 4: rep["warnings"].append("quiet zone below 4 modules: many scanners will fail")
    if size_mm:
        mm = float(size_mm) / (sym if size_basis == "symbol" else n)
        rep.update(size_basis=size_basis, module_mm=round(mm, 4), dark_square_mm=round(mm * n, 3), symbol_mm=round(mm * sym, 3))
    return rep


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("text"); ap.add_argument("-o", "--output"); ap.add_argument("--ecc", default="Q", choices=list(ECC_IDX), type=str.upper); ap.add_argument("--module-px", type=int, default=12)
    ap.add_argument("--quiet", type=int, default=4); ap.add_argument("--min-version", type=int, default=1); ap.add_argument("--mask", type=int); ap.add_argument("--size-mm", type=float)
    ap.add_argument("--size-basis", choices=("symbol", "modules"), default="symbol"); ap.add_argument("--json", action="store_true"); a = ap.parse_args(argv)
    try:
        if a.module_px < 1 or a.quiet < 0: raise ValueError("--module-px must be >= 1 and --quiet >= 0")
        info = make_qr(a.text, a.ecc, a.min_version, a.mask)
        rep = qr_report(info, a.module_px, a.quiet, a.size_mm, a.size_basis)
        if a.output:
            with open(a.output, "wb") as f: f.write(qr_png(info["matrix"], a.module_px, a.quiet))
            rep["output"] = a.output
    except ValueError as e:
        print(f"make_qr: {e}", file=sys.stderr); return 2
    if a.json or not a.output: print(json.dumps(rep, indent=2))
    else: print(f"qr: {a.output} (version {rep['version']}, {rep['modules']}x{rep['modules']} modules + {a.quiet} quiet, ecc {rep['ecc']}, {rep['png_px']} px)" + "".join(f"\nwarning: {w}" for w in rep["warnings"]))
    return 0


if __name__ == "__main__": sys.exit(main())
