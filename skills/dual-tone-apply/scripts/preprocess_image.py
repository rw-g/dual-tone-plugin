#!/usr/bin/env python3
"""Deterministic image preprocessing for 3D annotation textures (Pillow + NumPy only; no AI segmentation, no network).

  preprocess_image.py inspect  art.png                       -> JSON: size, alpha, colours, background, artwork bounds, padding, likely role, seamless score
  preprocess_image.py process  art.png out.png [options]     -> cleaned RGBA PNG + JSON metadata (what was done, bounds, mm per pixel)

process options:
  --role auto|logo|sticker|qr|pattern   (auto = use inspect's guess; says so in the metadata)
  --background auto|none|white|black|#RRGGBB   which colour counts as removable background (auto = dominant border colour, only if the border is uniform)
  --tolerance N      colour distance (0-255) for "same as background" (default 24)
  --threshold otsu|N  binarisation threshold on luminance (default otsu)
  --keep-color       do NOT binarise (use when the user explicitly asked to keep colours)
  --invert           swap which luminance side is ink
  --no-trim          keep the full canvas (default for logo/sticker: crop to the artwork bounds so a requested width means ARTWORK width)
  --width-mm W       requested physical width; reports mm_per_px and height_mm for the output
  --qr-quiet-modules N   (qr) quiet zone in modules (default 4)
  --qr-transparent-light  (qr) make light modules/quiet zone transparent (ONLY safe on a light surface; default keeps them opaque white)
  --qr-size-includes quiet|dark   what --width-mm measures for a QR (default quiet = whole symbol incl. quiet zone)
  --verify-qr        decode input and output with OpenCV (if available) and compare the payloads

Output convention for logo/sticker/qr: ink = opaque black (0,0,0,255); artwork-internal light areas = opaque white; removed background = (255,255,255,0).
Background is only removed where it is connected to the image border, so white inside the artwork (letter counters, QR light modules, holes) is kept.
"""
import argparse, json, sys
import numpy as np
from PIL import Image

class ImageError(ValueError): pass

def load_rgba(path):
    try: im = Image.open(path)
    except Exception as e: raise ImageError(f"cannot open image: {e}")
    info = dict(mode=im.mode, format=im.format, has_palette_transparency="transparency" in im.info)
    return np.array(im.convert("RGBA")), info

def luminance(rgb): return 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]

def composite_white(rgba):
    a = rgba[..., 3:4].astype(float) / 255.0
    return (rgba[..., :3] * a + 255.0 * (1 - a)).round().astype(np.uint8)

def otsu(values):
    """Otsu threshold for 8-bit luminance values (1-D array). Returns an int t; ink is value < t."""
    hist = np.bincount(values.astype(np.uint8).ravel(), minlength=256).astype(float); total = hist.sum()
    if total == 0: return 128
    sum_all = (np.arange(256) * hist).sum(); wb = sb = 0.0; best, thr = -1.0, 128
    for t in range(256):
        wb += hist[t]
        if wb == 0: continue
        wf = total - wb
        if wf == 0: break
        sb += t * hist[t]; mb, mf = sb / wb, (sum_all - sb) / wf; var = wb * wf * (mb - mf) ** 2
        if var > best: best, thr = var, t + 1
    return int(thr)

def _label(mask):
    try:
        from scipy import ndimage
        lab, n = ndimage.label(mask); return lab, n
    except ImportError:
        lab = np.zeros(mask.shape, np.int32); n = 0   # slow pure-numpy fallback: propagate from the border only (labels: 1 = connected to border)
        return None, 0

def border_connected(candidate):
    """Pixels of `candidate` that are 4-connected to the image border."""
    h, w = candidate.shape
    lab, n = _label(candidate)
    if lab is not None:
        edge = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]])); edge = edge[edge > 0]
        return np.isin(lab, edge)
    reach = np.zeros_like(candidate); reach[0] |= candidate[0]; reach[-1] |= candidate[-1]; reach[:, 0] |= candidate[:, 0]; reach[:, -1] |= candidate[:, -1]
    while True:   # iterative dilation constrained to candidate
        nxt = reach.copy(); nxt[1:] |= reach[:-1]; nxt[:-1] |= reach[1:]; nxt[:, 1:] |= reach[:, :-1]; nxt[:, :-1] |= reach[:, 1:]; nxt &= candidate
        if (nxt == reach).all(): return reach
        reach = nxt

def border_stats(rgb):
    edge = np.concatenate([rgb[0], rgb[-1], rgb[1:-1, 0], rgb[1:-1, -1]]).astype(int)
    q = (edge >> 3); key = q[:, 0] * 1024 + q[:, 1] * 32 + q[:, 2]; vals, counts = np.unique(key, return_counts=True); k = vals[counts.argmax()]
    sel = edge[key == k]; return tuple(int(x) for x in sel.mean(0).round()), float(counts.max() / len(edge))

def parse_color(s):
    s = s.lower()
    if s == "white": return (255, 255, 255)
    if s == "black": return (0, 0, 0)
    if s.startswith("#") and len(s) == 7: return tuple(int(s[i:i + 2], 16) for i in (1, 3, 5))
    raise ImageError(f"bad colour '{s}'")

def background_mask(rgba, background="auto", tolerance=24):
    """-> (bg_mask, info). Transparent pixels (alpha<128) are background. Otherwise a colour-matching region connected to the border."""
    alpha_bg = rgba[..., 3] < 128; info = dict(method=None, color=None)
    if alpha_bg.mean() > 0.001 and background in ("auto", "none"):
        info.update(method="alpha"); return alpha_bg, info
    if background == "none": return alpha_bg, dict(method="none", color=None)
    rgb = composite_white(rgba)
    if background == "auto":
        col, frac = border_stats(rgb); info["border_uniform_fraction"] = round(frac, 4)
        if frac < 0.85: info.update(method="skipped: border is not a uniform colour (ambiguous background, nothing removed)"); return alpha_bg, info
    else: col = parse_color(background)
    dist = np.abs(rgb.astype(int) - np.array(col)).max(-1); cand = dist <= tolerance
    bg = border_connected(cand) | alpha_bg; info.update(method="border flood fill", color=list(col)); return bg, info

def bbox_of(mask):
    ys, xs = np.where(mask)
    if len(xs) == 0: return None
    return [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]

def seam_ratio(rgb):
    """How much worse the wrap-around seam is than a normal neighbouring row/column: ~1 = tiles seamlessly, >>1 = visible seam."""
    g = luminance(rgb); eps = 0.5
    cx = np.abs(g[:, 0] - g[:, -1]).mean() / (np.abs(np.diff(g, axis=1)).mean() + eps); cy = np.abs(g[0] - g[-1]).mean() / (np.abs(np.diff(g, axis=0)).mean() + eps)
    return float(max(cx, cy))

def _runs(line):
    out, cur, n = [], line[0], 1
    for v in line[1:]:
        if v == cur: n += 1
        else: out.append((cur, n)); cur, n = v, 1
    out.append((cur, n)); return out
def finder_rows(binary_dark):
    """Number of rows containing the QR finder signature dark:light:dark:light:dark = 1:1:3:1:1."""
    hits = 0
    for row in binary_dark[:: max(1, binary_dark.shape[0] // 400)]:
        r = _runs(row.tolist())
        for i in range(len(r) - 4):
            seq = r[i:i + 5]
            if seq[0][0] and not seq[1][0] and seq[2][0] and not seq[3][0] and seq[4][0]:
                m = seq[0][1]; 
                if m > 0 and all(abs(seq[k][1] - c * m) <= max(1, 0.6 * m) for k, c in enumerate((1, 1, 3, 1, 1))): hits += 1; break
    return hits

def qr_decode(rgb):
    try: import cv2
    except ImportError: return None
    g = luminance(rgb).astype(np.uint8); det = cv2.QRCodeDetector()
    for s in (1.0, 0.5, 2.0):
        im = g if s == 1.0 else cv2.resize(g, None, fx=s, fy=s, interpolation=cv2.INTER_NEAREST if s > 1 else cv2.INTER_AREA)
        pad = max(20, im.shape[0] // 10); im = np.pad(im, pad, constant_values=255); txt, _, _ = det.detectAndDecode(im)
        if txt: return txt
    return ""

def inspect(path):
    rgba, meta = load_rgba(path); h, w = rgba.shape[:2]; alpha = rgba[..., 3]; rgb = composite_white(rgba); g = luminance(rgb)
    packed = rgb[..., 0].astype(np.int64) * 65536 + rgb[..., 1].astype(np.int64) * 256 + rgb[..., 2]; uniq = int(len(np.unique(packed)))
    is_bw = bool(((rgb[..., 0] == rgb[..., 1]) & (rgb[..., 1] == rgb[..., 2]) & ((rgb[..., 0] == 0) | (rgb[..., 0] == 255))).all())
    is_gray = bool((rgb.max(-1).astype(int) - rgb.min(-1).astype(int)).max() <= 2)
    bg_mask, bginfo = background_mask(rgba, "auto"); fg = ~bg_mask; box = bbox_of(fg)
    col, frac = border_stats(rgb)
    out = dict(file=path, width=w, height=h, aspect_ratio=round(w / h, 6), mode=meta["mode"], format=meta["format"], has_alpha=bool(alpha.min() < 255), transparent_fraction=round(float((alpha < 128).mean()), 5),
               unique_colors=uniq, is_binary_black_white=is_bw, is_grayscale=is_gray, luminance_mean=round(float(g.mean()), 2), border_color=list(col), border_uniform_fraction=round(frac, 4), background=bginfo)
    out["artwork_bbox_px"] = box
    if box:
        x0, y0, x1, y1 = box; out["artwork_size_px"] = [x1 - x0, y1 - y0]; out["padding_px"] = dict(left=x0, top=y0, right=w - x1, bottom=h - y1)
        out["artwork_fraction_of_canvas"] = round((x1 - x0) * (y1 - y0) / float(w * h), 4)
    out["seam_ratio"] = round(seam_ratio(rgb), 3); out["seamless_likely"] = bool(out["seam_ratio"] <= 2.0 and frac < 0.85)
    dark = g < 128; fr = finder_rows(dark) if is_bw or uniq < 8 else 0; cvq = qr_decode(rgb) if (w * h) < 4_000_000 else None
    out["qr_hint"] = dict(finder_pattern_rows=fr, opencv_decoded=cvq if cvq else None)
    reasons = []
    if cvq or fr >= 6: role = "qr"; reasons.append("QR finder patterns detected" if fr >= 6 else "OpenCV decoded a QR payload")
    elif out["has_alpha"] or (frac >= 0.85 and out.get("artwork_fraction_of_canvas", 1) < 0.92): role = "logo"; reasons.append("uniform border/transparent background around a bounded artwork")
    elif out.get("artwork_fraction_of_canvas", 1) >= 0.92 and frac < 0.85: role = "pattern"; reasons.append("content fills the canvas with no uniform border" + ("; edges match (seamless-looking)" if out["seamless_likely"] else ""))
    else: role = "ambiguous"; reasons.append("could be a logo or a pattern: decide from the user's wording")
    out["likely_role"] = role; out["role_reasons"] = reasons; return out

def process(src, dst, role="auto", background="auto", tolerance=24, threshold="otsu", keep_color=False, invert=False, trim=None, width_mm=None,
            qr_quiet_modules=4, qr_transparent_light=False, qr_size_includes="quiet", verify_qr=False):
    rgba, meta = load_rgba(src); H, W = rgba.shape[:2]; notes = []; ins = inspect(src)
    resolved = role if role != "auto" else ins["likely_role"]
    if role == "auto": notes.append(f"role auto-detected as '{resolved}' ({'; '.join(ins['role_reasons'])})")
    if resolved == "ambiguous": notes.append("role ambiguous: treated as 'logo'; confirm with the user if it matters"); resolved = "logo"
    rgb = composite_white(rgba); g = luminance(rgb); res = dict(source=src, output=dst, role=resolved, canvas_px=[W, H], notes=notes)
    out = np.zeros((H, W, 4), np.uint8); out[..., :3] = 255
    def thr_for(vals):
        if keep_color: return None
        if threshold == "otsu":
            if vals.size == 0 or vals.max() - vals.min() < 30: return 128 if vals.size == 0 or vals.mean() >= 128 else 256   # one tone only
            return otsu(vals)
        return int(threshold)
    if resolved == "pattern":
        if keep_color: out = rgba.copy(); res["binarized"] = False
        else:
            t = thr_for(g); ink = (g < t) if not invert else (g >= t); out[..., :3] = np.where(ink[..., None], 0, 255); out[..., 3] = np.where(rgba[..., 3] < 128, 0, 255) if ins["has_alpha"] else 255
            res.update(binarized=True, threshold=t, ink_fraction=round(float(ink.mean()), 4))
        res["background_removed"] = False; res["trimmed"] = False; res["artwork_bbox_px"] = [0, 0, W, H]
        res["tiling"] = dict(seamless_likely=ins["seamless_likely"], seam_ratio=ins["seam_ratio"], advice="repeat with tilestyleu/v='wrap' at the requested physical tile size" if ins["seamless_likely"] else "edges do not match: avoid visible tiling, use 'mirror' tiles or a single stretch")
        Image.fromarray(out).save(dst, "PNG"); return _finish(res, out, width_mm, ins)
    bg, binfo = background_mask(rgba, background, tolerance); fg = ~bg; res["background"] = binfo
    if not fg.any(): raise ImageError("no foreground left after background removal; try --background none or a different --tolerance")
    box = bbox_of(fg); res["artwork_bbox_px"] = box
    if resolved == "qr":
        dark = (g < (otsu(g[fg]) if threshold == "otsu" else int(threshold))) & fg if not keep_color else (g < 128) & fg
        if ins["is_binary_black_white"]: dark = g < 128; notes.append("input already pure black/white: structure preserved exactly")
        qbox = bbox_of(dark); 
        if qbox is None: raise ImageError("no dark QR modules found")
        x0, y0, x1, y1 = qbox; row = dark[y0, x0:x1]; run = _runs(row.tolist())[0][1]; module = max(1.0, run / 7.0); sym = max(x1 - x0, y1 - y0); modules = int(round(sym / module))
        quiet = int(round(qr_quiet_modules * module)); cx0, cy0, cx1, cy1 = x0 - quiet, y0 - quiet, x1 + quiet, y1 + quiet
        canvas = np.full((cy1 - cy0, cx1 - cx0, 4), 255, np.uint8); canvas[..., 3] = 255
        sx0, sy0, sx1, sy1 = max(cx0, 0), max(cy0, 0), min(cx1, W), min(cy1, H); sub = np.where(dark[sy0:sy1, sx0:sx1, None], 0, 255).astype(np.uint8)
        canvas[sy0 - cy0:sy1 - cy0, sx0 - cx0:sx1 - cx0, :3] = sub
        if qr_transparent_light: canvas[..., 3] = np.where(canvas[..., 0] == 0, 255, 0); notes.append("light modules and quiet zone are TRANSPARENT: only scannable on a light surface")
        res.update(binarized=True, module_px_estimate=round(module, 3), modules_estimate=modules, dark_square_px=[x1 - x0, y1 - y0], quiet_zone_px=quiet, quiet_zone_modules=qr_quiet_modules, trimmed=True, background_removed=True,
                   output_canvas_includes_quiet_zone=True, symbol_px_with_quiet=[cx1 - cx0, cy1 - cy0])
        if cx0 < 0 or cy0 < 0 or cx1 > W or cy1 > H: notes.append("source image had less than the requested quiet zone: white padding was added")
        out = canvas
        if width_mm:
            full = (cx1 - cx0); dark_w = (x1 - x0)
            mm_px = width_mm / (full if qr_size_includes == "quiet" else dark_w); res["mm_per_px"] = mm_px; res["size_basis"] = qr_size_includes
            res["dark_square_mm"] = round(dark_w * mm_px, 4); res["symbol_mm_with_quiet"] = round(full * mm_px, 4); res["module_mm"] = round(module * mm_px, 4)
        if verify_qr:
            a, b = qr_decode(rgb), qr_decode(out[..., :3]); res["qr_verification"] = dict(available=a is not None, input_payload=a, output_payload=b, match=(a is not None and a != "" and a == b))
        Image.fromarray(out).save(dst, "PNG"); res["output_px"] = [out.shape[1], out.shape[0]]; return _finish(res, out, None, ins, done=True)
    # logo / sticker
    if keep_color: out[..., :3] = rgba[..., :3]; out[..., 3] = np.where(fg, 255, 0); res["binarized"] = False
    else:
        t = thr_for(g[fg]); ink = fg & ((g < t) if not invert else (g >= t)); out[..., :3] = 255; out[..., 3] = np.where(fg, 255, 0)
        out[ink, :3] = 0; res.update(binarized=True, threshold=t, ink_fraction_of_artwork=round(float(ink.sum() / max(fg.sum(), 1)), 4))
        if ins["is_binary_black_white"] and not ink.any(): notes.append("no ink found: check --invert")
    res["background_removed"] = bool(bg.any()); do_trim = (resolved in ("logo", "sticker")) if trim is None else trim
    if do_trim:
        x0, y0, x1, y1 = box; out = out[y0:y1, x0:x1]; res["trimmed"] = True; res["artwork_in_output_px"] = [0, 0, x1 - x0, y1 - y0]
    else: res["trimmed"] = False; res["artwork_in_output_px"] = box
    Image.fromarray(out).save(dst, "PNG"); res["output_px"] = [out.shape[1], out.shape[0]]
    return _finish(res, out, width_mm, ins, art_w=(box[2] - box[0]))

def _finish(res, out, width_mm, ins, done=False, art_w=None):
    res.setdefault("output_px", [out.shape[1], out.shape[0]])
    if width_mm and not done:
        basis = art_w if (art_w and res.get("trimmed") is False and res["role"] != "pattern") else res["output_px"][0]
        if res["role"] in ("logo", "sticker") and not res.get("trimmed"): basis = art_w; res["size_basis"] = "visible artwork width (canvas not trimmed)"
        else: res["size_basis"] = "output image width"
        mm_px = width_mm / basis; res["mm_per_px"] = mm_px; res["output_size_mm"] = [round(res["output_px"][0] * mm_px, 4), round(res["output_px"][1] * mm_px, 4)]
        if res["role"] in ("logo", "sticker"): res["artwork_size_mm"] = [round((res["artwork_in_output_px"][2] - res["artwork_in_output_px"][0]) * mm_px, 4), round((res["artwork_in_output_px"][3] - res["artwork_in_output_px"][1]) * mm_px, 4)]
    res["input"] = {k: ins[k] for k in ("width", "height", "mode", "has_alpha", "is_binary_black_white", "unique_colors", "likely_role")}
    return res

def inspect_image(path):
    """Library entry point: JSON-serialisable image metadata (alias of inspect)."""
    return inspect(path)

def preprocess_image(src, dst, **options):
    """Library entry point: see process() for options; returns JSON-serialisable metadata."""
    return process(src, dst, **options)

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter); sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("inspect"); i.add_argument("image")
    p = sub.add_parser("process"); p.add_argument("image"); p.add_argument("output"); p.add_argument("--role", default="auto", choices=["auto", "logo", "sticker", "qr", "pattern"])
    p.add_argument("--background", default="auto"); p.add_argument("--tolerance", type=int, default=24); p.add_argument("--threshold", default="otsu"); p.add_argument("--keep-color", action="store_true"); p.add_argument("--invert", action="store_true")
    p.add_argument("--no-trim", action="store_true"); p.add_argument("--width-mm", type=float); p.add_argument("--qr-quiet-modules", type=int, default=4); p.add_argument("--qr-transparent-light", action="store_true")
    p.add_argument("--qr-size-includes", choices=["quiet", "dark"], default="quiet"); p.add_argument("--verify-qr", action="store_true"); p.add_argument("--meta", help="also write the metadata JSON here")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "inspect": print(json.dumps(inspect(a.image), indent=1)); return 0
        res = process(a.image, a.output, a.role, a.background, a.tolerance, a.threshold, a.keep_color, a.invert, False if a.no_trim else None, a.width_mm, a.qr_quiet_modules, a.qr_transparent_light, a.qr_size_includes, a.verify_qr)
        if a.meta: json.dump(res, open(a.meta, "w"), indent=1)
        print(json.dumps(res, indent=1)); return 0
    except ImageError as e: print(json.dumps(dict(error=str(e))), file=sys.stderr); return 2
if __name__ == "__main__": sys.exit(main())
