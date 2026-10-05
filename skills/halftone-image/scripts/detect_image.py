#!/usr/bin/env python3
"""Decide what an image needs before it goes on a 3D model (numpy + Pillow; OpenCV optional for QR detection).

Usage:  detect_image.py image.png [--json]
action (also the exit code):
  as_is     0   already pure black/white: use directly
  halftone  10  continuous tone (photo, shading, gradients): open the halftone viewer
  qr        11  QR code: never halftone; hard threshold and verify it decodes
  threshold 12  block colours (logo, silhouette, line art, text, near two-colour pattern, soft anti-aliased edges): just threshold every pixel to black or white, no viewer
  (2 = unreadable)
Library: detect_image(path) -> dict {mode, kind, action, needs_halftone, needs_threshold, recommended_preset, is_qr, ...}
mode: binary | grayscale | color.   kind: binary | flat (few tones/colours) | continuous (many tones)."""
import argparse, json, sys
import numpy as np
from PIL import Image

def _flatten(im):
    im.load()
    has_alpha = im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info)
    if has_alpha:
        im = im.convert("RGBA"); bg = Image.new("RGBA", im.size, (255, 255, 255, 255)); bg.alpha_composite(im); im = bg
    return im.convert("RGB"), has_alpha

def detect_image(path, tol=12):
    try: im, has_alpha = _flatten(Image.open(path))
    except Exception as e: return {"error": f"cannot read image: {e}", "needs_halftone": False}
    a = np.asarray(im, dtype=np.int16); h, w, _ = a.shape
    spread = a.max(axis=2) - a.min(axis=2); gray = a.mean(axis=2)
    is_gray = float((spread <= tol).mean()) >= 0.99
    near_bw = float(((gray <= tol) | (gray >= 255 - tol)).mean())
    binary = is_gray and near_bw >= 0.995
    mode = "binary" if binary else ("grayscale" if is_gray else "color")
    q = (a // 16).reshape(-1, 3); keys = q[:, 0] * 256 + q[:, 1] * 16 + q[:, 2]; vals, counts = np.unique(keys, return_counts=True)
    order = np.sort(counts)[::-1]; cover = np.cumsum(order) / order.sum(); dominant = int(np.searchsorted(cover, 0.95) + 1)
    kind = "binary" if binary else ("flat" if dominant <= 6 else "continuous")
    is_qr = False
    try:
        import cv2
        g8 = np.clip(gray, 0, 255).astype(np.uint8); txt, pts, _ = cv2.QRCodeDetector().detectAndDecode(g8); is_qr = bool(txt) or (pts is not None and len(pts) > 0 and bool(txt))
    except Exception: pass
    two_tone = near_bw >= 0.90                                                       # mostly pure black/white: the rest is anti-aliased edge pixels
    if binary: action = "as_is"
    elif is_qr: action = "qr"
    elif kind == "flat" or two_tone: action = "threshold"
    else: action = "halftone"
    needs = action == "halftone"
    preset = {"threshold": "threshold", "halftone": "newsprint"}.get(action)
    return dict(path=str(path), width=int(w), height=int(h), mode=mode, kind=kind, has_alpha=bool(has_alpha), dominant_colors=dominant, near_black_white_fraction=round(near_bw, 4),
                is_qr=is_qr, action=action, needs_halftone=needs, needs_threshold=action == "threshold", recommended_preset=preset,
                advice={"as_is": "pure black/white: apply directly", "qr": "QR code: never halftone; binarise with a hard threshold and verify decoding",
                        "threshold": "block colours / near two-tone: threshold to black and white with halftone.py --preset threshold, no viewer",
                        "halftone": "continuous tone: open the halftone viewer before applying"}[action])

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter); ap.add_argument("path"); ap.add_argument("--json", action="store_true"); a = ap.parse_args(argv)
    r = detect_image(a.path)
    print(json.dumps(r, indent=2) if a.json else "; ".join(f"{k}={v}" for k, v in r.items()))
    if "error" in r: return 2
    return {"as_is": 0, "halftone": 10, "qr": 11, "threshold": 12}[r["action"]]
if __name__ == "__main__": sys.exit(main())
