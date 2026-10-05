/* Halftone engine: pure functions, no DOM. tone = Float32Array in [0,1], 1 = white paper. Output = Uint8Array, 1 = paper (white), 0 = ink (black).
   Shared by the viewer (inlined into the HTML) and the node tests. Mirrors scripts/halftone.py. */
(function (root) {
'use strict';
var KERNELS = {
  floyd:      { d: 16, k: [[1,0,7],[-1,1,3],[0,1,5],[1,1,1]] },
  jarvis:     { d: 48, k: [[1,0,7],[2,0,5],[-2,1,3],[-1,1,5],[0,1,7],[1,1,5],[2,1,3],[-2,2,1],[-1,2,3],[0,2,5],[1,2,3],[2,2,1]] },
  stucki:     { d: 42, k: [[1,0,8],[2,0,4],[-2,1,2],[-1,1,4],[0,1,8],[1,1,4],[2,1,2],[-2,2,1],[-1,2,2],[0,2,4],[1,2,2],[2,2,1]] },
  atkinson:   { d: 8,  k: [[1,0,1],[2,0,1],[-1,1,1],[0,1,1],[1,1,1],[0,2,1]] },
  burkes:     { d: 32, k: [[1,0,8],[2,0,4],[-2,1,2],[-1,1,4],[0,1,8],[1,1,4],[2,1,2]] },
  sierra:     { d: 32, k: [[1,0,5],[2,0,3],[-2,1,2],[-1,1,4],[0,1,5],[1,1,4],[2,1,2],[-1,2,2],[0,2,3],[1,2,2]] },
  sierra2:    { d: 16, k: [[1,0,4],[2,0,3],[-2,1,1],[-1,1,2],[0,1,3],[1,1,2],[2,1,1]] },
  sierraLite: { d: 4,  k: [[1,0,2],[-1,1,1],[0,1,1]] }
};
var SHAPES = ['round', 'ellipse', 'square', 'diamond', 'line', 'cross', 'ring'], GRIDS = ['square', 'hex', 'radial', 'ring'];

function mulberry32(a) { return function () { a |= 0; a = a + 0x6D2B79F5 | 0; var t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }

// ---- tone preparation -------------------------------------------------------------------------------------------------------------
function boxBlur(src, w, h, r) {
  r = Math.round(r); if (r < 1) return Float32Array.from(src);
  var tmp = new Float32Array(w * h), out = new Float32Array(w * h), x, y, k, acc, n = 2 * r + 1;
  for (y = 0; y < h; y++) { acc = 0; for (k = -r; k <= r; k++) acc += src[y * w + Math.min(w - 1, Math.max(0, k))]; for (x = 0; x < w; x++) { tmp[y * w + x] = acc / n; acc += src[y * w + Math.min(w - 1, x + r + 1)] - src[y * w + Math.max(0, x - r)]; } }
  for (x = 0; x < w; x++) { acc = 0; for (k = -r; k <= r; k++) acc += tmp[Math.min(h - 1, Math.max(0, k)) * w + x]; for (y = 0; y < h; y++) { out[y * w + x] = acc / n; acc += tmp[Math.min(h - 1, y + r + 1) * w + x] - tmp[Math.max(0, y - r) * w + x]; } }
  return out;
}
// o: {blur (px radius), sharpen (0..3), normalize, bp/wp (black/white point 0..1), brightness (-1..1), contrast (-100..100), gamma (0.2..3), wave ('saw'|'tri'), waveN, invert, linear}
function prepare(lum, w, h, o) {
  o = o || {}; var n = w * h, t = Float32Array.from(lum), i;
  if (o.blur > 0) t = boxBlur(boxBlur(t, w, h, o.blur), w, h, o.blur);                            // two box passes ~ gaussian
  if (o.sharpen > 0) { var b = boxBlur(boxBlur(t, w, h, 2), w, h, 2); for (i = 0; i < n; i++) t[i] = t[i] + o.sharpen * (t[i] - b[i]); }
  if (o.normalize) {                                                                               // stretch the 0.5%..99.5% tone range to 0..1 (1024-bin histogram)
    var hist = new Int32Array(1024), lo = 0, hi = 1, acc = 0; for (i = 0; i < n; i++) { var q = t[i] < 0 ? 0 : t[i] > 1 ? 1 : t[i]; hist[Math.min(1023, Math.floor(q * 1024))]++; }
    for (i = 0; i < 1024; i++) { acc += hist[i]; if (acc >= 0.005 * n) { lo = i / 1024; break; } } acc = 0;
    for (i = 1023; i >= 0; i--) { acc += hist[i]; if (acc >= 0.005 * n) { hi = (i + 1) / 1024; break; } }
    if (hi > lo) for (i = 0; i < n; i++) t[i] = (t[i] - lo) / (hi - lo);
  }
  var bp = +o.bp || 0, wp = o.wp == null ? 1 : +o.wp; if (bp > 0 || wp < 1) { var span = Math.max(1e-3, wp - bp); for (i = 0; i < n; i++) t[i] = (t[i] - bp) / span; }
  var br = +o.brightness || 0, cf = Math.pow(4, (+o.contrast || 0) / 100), ig = 1 / Math.max(0.05, o.gamma || 1), wn = Math.max(1, +o.waveN || 1), wv = o.wave === 'saw' || o.wave === 'tri' ? o.wave : null;
  for (i = 0; i < n; i++) {
    var v = (t[i] + br - 0.5) * cf + 0.5; v = v < 0 ? 0 : v > 1 ? 1 : v; v = Math.pow(v, ig);
    if (wv && v < 1) { var sv = v * wn; if (wv === 'saw') v = sv - Math.floor(sv); else { var qv = sv - 2 * Math.floor(sv / 2); v = qv <= 1 ? qv : 2 - qv; } }
    if (o.invert) v = 1 - v; t[i] = v;
  }
  if (o.linear) for (i = 0; i < n; i++) { var s2 = t[i]; t[i] = s2 <= 0.04045 ? s2 / 12.92 : Math.pow((s2 + 0.055) / 1.055, 2.4); }
  return t;
}

// ---- methods ----------------------------------------------------------------------------------------------------------------------
function threshold(tone, w, h, p) { var th = p.threshold == null ? 0.5 : p.threshold, out = new Uint8Array(w * h); for (var i = 0; i < out.length; i++) out[i] = tone[i] > th ? 1 : 0; return out; }

function bayerMatrix(n) { var m = [[0]], s = 1; while (s < n) { var N = []; for (var y = 0; y < 2 * s; y++) { N.push([]); for (var x = 0; x < 2 * s; x++) { var q = m[y % s][x % s] * 4, ox = x >= s ? 1 : 0, oy = y >= s ? 1 : 0; N[y].push(q + (oy === 0 ? (ox === 0 ? 0 : 2) : (ox === 0 ? 3 : 1))); } } m = N; s *= 2; } return m; }
function ordered(tone, w, h, mat, size) { var out = new Uint8Array(w * h), nn = size * size; for (var y = 0; y < h; y++) for (var x = 0; x < w; x++) out[y * w + x] = tone[y * w + x] > (mat[(y % size) * size + (x % size)] + 0.5) / nn ? 1 : 0; return out; }
function bayer(tone, w, h, p) { var size = +p.size || 4, m = bayerMatrix(size), flat = []; m.forEach(function (r) { r.forEach(function (v) { flat.push(v); }); }); return ordered(tone, w, h, flat, size); }

var _blue = null;
function blueNoiseMatrix() {                                                                 // void-and-cluster (Ulichney 1993), 64x64 torus, sigma 1.5, deterministic
  if (_blue) return _blue; var N = 64, n = N * N, sigma = 1.5, R = 6, rnd = mulberry32(12345), i, x, y;
  var kern = [], dx, dy; for (dy = -R; dy <= R; dy++) for (dx = -R; dx <= R; dx++) kern.push([dx, dy, Math.exp(-(dx * dx + dy * dy) / (2 * sigma * sigma))]);
  var E = new Float64Array(n), bin = new Uint8Array(n);
  function toggle(idx, on) { var px = idx % N, py = (idx / N) | 0, sg = on ? 1 : -1; bin[idx] = on ? 1 : 0; for (var k = 0; k < kern.length; k++) { var xx = (px + kern[k][0] + N) % N, yy = (py + kern[k][1] + N) % N; E[yy * N + xx] += sg * kern[k][2]; } }
  function tightest() { var b = -1, bv = -1; for (var j = 0; j < n; j++) if (bin[j] && E[j] > bv) { bv = E[j]; b = j; } return b; }
  function largestVoid() { var b = -1, bv = 1e18; for (var j = 0; j < n; j++) if (!bin[j] && E[j] < bv) { bv = E[j]; b = j; } return b; }
  var ones = Math.round(n * 0.1), order = []; for (i = 0; i < n; i++) order.push(i); for (i = n - 1; i > 0; i--) { var j2 = Math.floor(rnd() * (i + 1)), tmp = order[i]; order[i] = order[j2]; order[j2] = tmp; }
  for (i = 0; i < ones; i++) toggle(order[i], true);
  for (var guard = 0; guard < 5000; guard++) { var c = tightest(); toggle(c, false); var v = largestVoid(); toggle(c, true); if (v === c) break; toggle(c, false); toggle(v, true); }
  var rank = new Int32Array(n), proto = Uint8Array.from(bin), r;
  for (r = ones - 1; r >= 0; r--) { var c2 = tightest(); toggle(c2, false); rank[c2] = r; }                          // phase 1
  bin.fill(0); E.fill(0); for (i = 0; i < n; i++) if (proto[i]) toggle(i, true);
  for (r = ones; r < (n >> 1); r++) { var v2 = largestVoid(); rank[v2] = r; toggle(v2, true); }                       // phase 2
  for (r = n >> 1; r < n; r++) { var cl = -1, cv = 1e18; for (var j4 = 0; j4 < n; j4++) if (!bin[j4] && E[j4] < cv) { cv = E[j4]; cl = j4; } rank[cl] = r; toggle(cl, true); }   // phase 3 (remaining zeros, largest void first)
  _blue = rank; return _blue;
}
function blue(tone, w, h, p) { var m = blueNoiseMatrix(), out = new Uint8Array(w * h), N = 64, nn = N * N; for (var y = 0; y < h; y++) for (var x = 0; x < w; x++) out[y * w + x] = tone[y * w + x] > (m[(y % N) * N + (x % N)] + 0.5) / nn ? 1 : 0; return out; }
function ign(tone, w, h) { var out = new Uint8Array(w * h); for (var y = 0; y < h; y++) for (var x = 0; x < w; x++) { var f = (0.06711056 * x + 0.00583715 * y) % 1; var v = (52.9829189 * f) % 1; out[y * w + x] = tone[y * w + x] > v ? 1 : 0; } return out; }
function white(tone, w, h, p) { var r = mulberry32((p && p.seed) || 1), out = new Uint8Array(w * h); for (var i = 0; i < out.length; i++) out[i] = tone[i] > r() ? 1 : 0; return out; }

function diffusion(tone, w, h, p) {
  var K = KERNELS[p.kernel || 'floyd'], buf = Float32Array.from(tone), out = new Uint8Array(w * h), th = p.threshold == null ? 0.5 : p.threshold, amt = p.amount == null ? 1 : p.amount, serp = p.serpentine !== false;
  for (var y = 0; y < h; y++) {
    var rev = serp && (y & 1), x0 = rev ? w - 1 : 0, x1 = rev ? -1 : w, st = rev ? -1 : 1;
    for (var x = x0; x !== x1; x += st) {
      var i = y * w + x, old = buf[i], nv = old > th ? 1 : 0, err = (old - nv) * amt; out[i] = nv;
      for (var k = 0; k < K.k.length; k++) { var xx = x + K.k[k][0] * st, yy = y + K.k[k][1]; if (xx < 0 || xx >= w || yy >= h) continue; buf[yy * w + xx] += err * K.k[k][2] / K.d; }
    }
  }
  return out;
}

function hilbertD2XY(n, d) { var x = 0, y = 0, t = d; for (var s = 1; s < n; s *= 2) { var rx = 1 & (t >> 1), ry = 1 & (t ^ rx); if (ry === 0) { if (rx === 1) { x = s - 1 - x; y = s - 1 - y; } var tm = x; x = y; y = tm; } x += s * rx; y += s * ry; t >>= 2; } return [x, y]; }
function riemersma(tone, w, h, p) {
  var hist = Math.max(2, Math.round(p.history || 16)), amt = p.amount == null ? 1 : p.amount, th = p.threshold == null ? 0.5 : p.threshold, ratio = 1 / 16, wt = [], sum = 0, j;
  for (j = 0; j < hist; j++) { wt.push(Math.pow(ratio, j / (hist - 1))); sum += wt[j]; }
  var q = new Float32Array(hist), n = 1; while (n < Math.max(w, h)) n *= 2; var out = new Uint8Array(w * h), head = 0;
  for (var d = 0; d < n * n; d++) { var xy = hilbertD2XY(n, d), x = xy[0], y = xy[1]; if (x >= w || y >= h) continue;
    var acc = 0; for (j = 0; j < hist; j++) acc += q[(head - j + hist) % hist] * wt[j]; acc = acc / sum * amt;
    var v = tone[y * w + x] + acc, nv = v > th ? 1 : 0; out[y * w + x] = nv; head = (head + 1) % hist; q[head] = v - nv; }
  return out;
}

// AM screens: dot/line/ring cells on a square, hex, radial or ring grid. A 64x64 spot-order LUT gives exact area coverage = darkness.
function spotG(shape, fx, fy) {
  switch (shape) { case 'ellipse': return Math.sqrt(fx * fx + (fy / 0.6) * (fy / 0.6)); case 'square': return Math.max(Math.abs(fx), Math.abs(fy)); case 'diamond': return Math.abs(fx) + Math.abs(fy);
    case 'line': return Math.abs(fy); case 'cross': return Math.min(Math.abs(fx), Math.abs(fy)); case 'ring': return Math.abs(Math.sqrt(fx * fx + fy * fy) - 0.33); default: return Math.sqrt(fx * fx + fy * fy); }
}
var _lut = {}, HEXH = 0.8660254037844386;
function spotLut(shape, hex) {
  var key = shape + (hex ? ':hex' : ''); if (_lut[key]) return _lut[key]; var N = 64, n = N * N, g = new Float64Array(n), idx = [], inside = new Uint8Array(n), i, x, y, span = hex ? 1.2 : 1;
  for (y = 0; y < N; y++) for (x = 0; x < N; x++) { var fx = (x + 0.5) / N * span - span / 2, fy = (y + 0.5) / N * span - span / 2, ok = 1;
    if (hex) ok = Math.abs(fx) <= 0.5 && Math.abs(0.5 * fx + HEXH * fy) <= 0.5 && Math.abs(-0.5 * fx + HEXH * fy) <= 0.5 ? 1 : 0;
    g[y * N + x] = spotG(shape, fx, fy) + 1e-9 * (y * N + x); inside[y * N + x] = ok; if (ok) idx.push(y * N + x); }
  idx.sort(function (a, b) { return g[a] - g[b]; }); var thr = new Float32Array(n).fill(1); for (i = 0; i < idx.length; i++) thr[idx[i]] = (i + 0.5) / idx.length; return (_lut[key] = thr);
}
function bilinear(a, w, h, x, y) { x = Math.min(w - 1, Math.max(0, x)); y = Math.min(h - 1, Math.max(0, y)); var x0 = Math.floor(x), y0 = Math.floor(y), x1 = Math.min(w - 1, x0 + 1), y1 = Math.min(h - 1, y0 + 1), fx = x - x0, fy = y - y0; return (a[y0 * w + x0] * (1 - fx) + a[y0 * w + x1] * fx) * (1 - fy) + (a[y1 * w + x0] * (1 - fx) + a[y1 * w + x1] * fx) * fy; }
function hash2(ix, iy, seed) { var h = (Math.imul(ix | 0, 374761393) + Math.imul(iy | 0, 668265263) + Math.imul(seed | 0, 1442695041)) | 0; h = Math.imul(h ^ (h >>> 13), 1274126177); h = (h ^ (h >>> 16)) >>> 0; return h / 4294967296; }
function vnoise(x, y, seed) { var ix = Math.floor(x), iy = Math.floor(y), fx = x - ix, fy = y - iy, u = fx * fx * (3 - 2 * fx), v = fy * fy * (3 - 2 * fy), a = hash2(ix, iy, seed), b = hash2(ix + 1, iy, seed), c = hash2(ix, iy + 1, seed), d = hash2(ix + 1, iy + 1, seed), top = a + (b - a) * u; return top + ((c + (d - c) * u) - top) * v; }
function am(tone, w, h, p) {
  var cell = Math.max(2, +p.cell || 6), ang = (+p.angle || 0) * Math.PI / 180, ca = Math.cos(ang), sa = Math.sin(ang), grid = p.grid || 'square', shape = grid === 'ring' ? 'line' : (p.shape || 'round'), TWO_PI = 2 * Math.PI;
  var resp = p.response == null ? 1 : +p.response, off = +p.offset || 0, warp = +p.warp || 0, wl = cell * Math.max(1, +p.warpScale || 4), cx0 = (p.cx == null ? 0.5 : +p.cx) * w, cy0 = (p.cy == null ? 0.5 : +p.cy) * h;
  var N = 64, lut = spotLut(shape, grid === 'hex'), smooth = p.centre === false ? null : boxBlur(tone, w, h, cell * 0.5), out = new Uint8Array(w * h);
  for (var y = 0; y < h; y++) for (var x = 0; x < w; x++) {
    var ox = x + 0.5, oy = y + 0.5, px = ox, py = oy, thr, ux = ox, uy = oy, t;
    if (warp > 0) { px = ox + warp * cell * (2 * vnoise(ox / wl, oy / wl, 1) - 1); py = oy + warp * cell * (2 * vnoise(ox / wl, oy / wl, 2) - 1); ux = px; uy = py; }
    if (grid === 'square') {
      var sx = (px * ca + py * sa) / cell, sy = (-px * sa + py * ca) / cell, i = Math.floor(sx), j = Math.floor(sy), fx = sx - i, fy = sy - j, bx = (i + 0.5) * cell, by = (j + 0.5) * cell;
      ux = bx * ca - by * sa; uy = bx * sa + by * ca; thr = lut[Math.min(N - 1, (fy * N) | 0) * N + Math.min(N - 1, (fx * N) | 0)];
    } else if (grid === 'hex') {
      var hx = (px * ca + py * sa) / cell, hy = (-px * sa + py * ca) / cell, jf = hy / HEXH, i0 = Math.floor(hx - 0.5 * jf), j0 = Math.floor(jf), bd = 1e18, bi = 0, bj = 0, bcx = 0, bcy = 0;
      for (var q = 0; q < 4; q++) { var ii = i0 + (q & 1), jj = j0 + (q >> 1), cxl = ii + 0.5 * jj, cyl = jj * HEXH, d2 = (hx - cxl) * (hx - cxl) + (hy - cyl) * (hy - cyl); if (d2 < bd) { bd = d2; bcx = cxl; bcy = cyl; } }
      var ddx = hx - bcx, ddy = hy - bcy; ux = bcx * cell * ca - bcy * cell * sa; uy = bcx * cell * sa + bcy * cell * ca;
      thr = lut[Math.max(0, Math.min(N - 1, Math.floor((ddy + 0.6) / 1.2 * N))) * N + Math.max(0, Math.min(N - 1, Math.floor((ddx + 0.6) / 1.2 * N)))];
    } else {                                                                                                 // radial | ring
      var dxr = px - cx0, dyr = py - cy0, r = Math.sqrt(dxr * dxr + dyr * dyr), th = Math.atan2(dyr, dxr) - ang; while (th < 0) th += TWO_PI; while (th >= TWO_PI) th -= TWO_PI;
      var k = Math.floor(r / cell), fy2 = r / cell - k, rc = (k + 0.5) * cell;
      if (grid === 'radial') { var nn = Math.max(1, Math.floor(TWO_PI * rc / cell + 0.5)), aa = th / TWO_PI * nn, ia = Math.floor(aa), fx2 = aa - ia, thc = (ia + 0.5) / nn * TWO_PI + ang; ux = cx0 + rc * Math.cos(thc); uy = cy0 + rc * Math.sin(thc); thr = lut[Math.min(N - 1, (fy2 * N) | 0) * N + Math.min(N - 1, (fx2 * N) | 0)]; }
      else { ux = cx0 + rc * Math.cos(th + ang); uy = cy0 + rc * Math.sin(th + ang); thr = lut[Math.min(N - 1, (fy2 * N) | 0) * N + (N >> 1)]; }
    }
    t = smooth ? bilinear(smooth, w, h, ux - 0.5, uy - 0.5) : tone[y * w + x];
    var d = 1 - t; d = d < 0 ? 0 : d > 1 ? 1 : d; if (resp !== 1) d = Math.pow(d, resp); d += off; d = d < 0 ? 0 : d > 1 ? 1 : d;
    out[y * w + x] = d > thr ? 0 : 1;
  }
  return out;
}

// Stipple: variable-radius Poisson-disk points (spacing shrinks with darkness), optional repulsion relaxation, dots drawn as circles. Trig-free so JS and Python agree.
function stipple(tone, w, h, p) {
  var smin = Math.max(1.5, +p.spacingMin || 4), smax = Math.max(smin, +p.spacingMax || 12), dot = Math.max(0.2, p.dot == null ? 1 : +p.dot), byTone = p.sizeByTone !== false, relax = Math.max(0, Math.min(20, Math.round(+p.relax || 0))), rnd = mulberry32((p.seed | 0) || 1);
  var cs = smin / Math.SQRT2, gw = Math.ceil(w / cs) + 1, gh = Math.ceil(h / cs) + 1, grid = new Int32Array(gw * gh).fill(-1), xs = [], ys = [], rs = [], ds = [], active = [], MAXP = 700000;
  function dens(x, y) { var d = 1 - bilinear(tone, w, h, x - 0.5, y - 0.5); return d < 0 ? 0 : d > 1 ? 1 : d; }
  function add(x, y) { var d = dens(x, y), i = xs.length; xs.push(x); ys.push(y); ds.push(d); rs.push(smax + (smin - smax) * d); grid[Math.floor(y / cs) * gw + Math.floor(x / cs)] = i; active.push(i); }
  add(rnd() * w, rnd() * h);
  while (active.length && xs.length < MAXP) {
    var ai = Math.floor(rnd() * active.length), pi = active[ai], r0 = rs[pi], ok = false;
    for (var k = 0; k < 20 && !ok; k++) {
      var a, b, q; do { a = rnd() * 4 - 2; b = rnd() * 4 - 2; q = a * a + b * b; } while (q < 1 || q >= 4);
      var cx = xs[pi] + a * r0, cy = ys[pi] + b * r0; if (cx < 0 || cy < 0 || cx >= w || cy >= h) continue;
      var dc = dens(cx, cy), rc = smax + (smin - smax) * dc, R = Math.ceil((rc + smax) / 2 / cs), gx = Math.floor(cx / cs), gy = Math.floor(cy / cs), free = true;
      for (var yy = Math.max(0, gy - R); yy <= Math.min(gh - 1, gy + R) && free; yy++) for (var xx = Math.max(0, gx - R); xx <= Math.min(gw - 1, gx + R); xx++) {
        var j = grid[yy * gw + xx]; if (j < 0) continue; var dx = cx - xs[j], dy = cy - ys[j], rr = (rc + rs[j]) / 2; if (dx * dx + dy * dy < rr * rr) { free = false; break; } }
      if (free) { add(cx, cy); ok = true; }
    }
    if (!ok) { active[ai] = active[active.length - 1]; active.pop(); }
  }
  for (var it = 0; it < relax; it++) {                                                                          // Jacobi repulsion: push apart neighbours closer than their mean target spacing
    var hc = smax, hw = Math.ceil(w / hc) + 1, hh = Math.ceil(h / hc) + 1, bk = new Array(hw * hh), i;
    for (i = 0; i < xs.length; i++) { var bi = Math.floor(ys[i] / hc) * hw + Math.floor(xs[i] / hc); (bk[bi] || (bk[bi] = [])).push(i); }
    var nx = xs.slice(), ny = ys.slice();
    for (i = 0; i < xs.length; i++) {
      var fxs = 0, fys = 0, bx = Math.floor(xs[i] / hc), by = Math.floor(ys[i] / hc);
      for (var oy = -1; oy <= 1; oy++) for (var ox = -1; ox <= 1; ox++) { var cx2 = bx + ox, cy2 = by + oy; if (cx2 < 0 || cy2 < 0 || cx2 >= hw || cy2 >= hh) continue; var L = bk[cy2 * hw + cx2]; if (!L) continue;
        for (var m = 0; m < L.length; m++) { var j2 = L[m]; if (j2 === i) continue; var ddx = xs[i] - xs[j2], ddy = ys[i] - ys[j2], d2 = ddx * ddx + ddy * ddy, rr2 = 0.6 * (rs[i] + rs[j2]); if (d2 < rr2 * rr2 && d2 > 1e-18) { var dd = Math.sqrt(d2), f = (rr2 - dd) * 0.25 / dd; fxs += ddx * f; fys += ddy * f; } } }
      nx[i] = Math.min(w - 1e-6, Math.max(0, xs[i] + fxs)); ny[i] = Math.min(h - 1e-6, Math.max(0, ys[i] + fys));
    }
    xs = nx; ys = ny; for (i = 0; i < xs.length; i++) { ds[i] = dens(xs[i], ys[i]); rs[i] = smax + (smin - smax) * ds[i]; }
  }
  var out = new Uint8Array(w * h).fill(1);
  for (var n2 = 0; n2 < xs.length; n2++) {
    if (ds[n2] < 0.02) continue;                                                                               // pure white stays white
    var rad = dot * (byTone ? rs[n2] * Math.sqrt(1.7 * ds[n2] / Math.PI) : 0.45 * smin), r2 = rad * rad, x0 = Math.max(0, Math.floor(xs[n2] - rad)), x1 = Math.min(w - 1, Math.ceil(xs[n2] + rad)), y0 = Math.max(0, Math.floor(ys[n2] - rad)), y1 = Math.min(h - 1, Math.ceil(ys[n2] + rad));
    for (var py2 = y0; py2 <= y1; py2++) for (var px2 = x0; px2 <= x1; px2++) { var ex = px2 + 0.5 - xs[n2], ey = py2 + 0.5 - ys[n2]; if (ex * ex + ey * ey <= r2) out[py2 * w + px2] = 0; }
    out[Math.floor(ys[n2]) * w + Math.floor(xs[n2])] = 0;
  }
  return out;
}

var METHODS = {
  threshold:  { fn: threshold },  bayer: { fn: bayer }, blue: { fn: blue }, ign: { fn: ign }, white: { fn: white },
  diffusion:  { fn: diffusion },  riemersma: { fn: riemersma }, am: { fn: am }, stipple: { fn: stipple }
};
function halftone(method, params, tone, w, h) { var m = METHODS[method]; if (!m) throw new Error('unknown halftone method: ' + method); return m.fn(tone, w, h, params || {}); }

var api = { KERNELS: KERNELS, SHAPES: SHAPES, GRIDS: GRIDS, prepare: prepare, halftone: halftone, bayerMatrix: bayerMatrix, blueNoiseMatrix: blueNoiseMatrix, hilbertD2XY: hilbertD2XY, boxBlur: boxBlur, mulberry32: mulberry32 };
if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.HalftoneEngine = api;
})(typeof window !== 'undefined' ? window : this);
