#!/usr/bin/env python3
"""ONE command that prepares any image as a black/white texture. Run it; do not write your own classifier, halftone code or viewer.

Usage:  prepare_image.py image [--prompt "<the user's request, verbatim>"] [-o outdir]
Prints one JSON line and exits:
  0   texture ready: {"action": "as_is|threshold|qr", "texture": "<outdir>/texture_bw.png"}  -> continue with dual-tone-apply apply_texture.py
  10  continuous-tone image: {"action": "halftone", "viewer": "<outdir>/halftone_viewer.html"}  -> give the viewer to the user and wait for the PNG / Apply
  2   unreadable image
Library: prepare_image(path, prompt="", outdir=None) -> dict"""
import argparse, json, os, shutil, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import detect_image as D, halftone as H, make_halftone_viewer as V
from PIL import Image


def prepare_image(path, prompt="", outdir=None):
    info = D.detect_image(path)
    if "error" in info: return {"error": info["error"]}
    outdir = outdir or os.path.dirname(os.path.abspath(path)) or "."; os.makedirs(outdir, exist_ok=True); act = info["action"]
    if act == "halftone":
        r = V.make_halftone_viewer(path, os.path.join(outdir, "halftone_viewer.html"), prompt=prompt)
        return dict(action=act, viewer=r["output"], message="Continuous-tone image: give the viewer to the user; they pick a look and press Apply to 3D model (or download the PNG). Wait for the PNG.")
    out = os.path.join(outdir, "texture_bw.png")
    if act == "as_is":
        im = Image.open(path); im.load(); im.convert("L").point(lambda v: 255 if v >= 128 else 0).convert("1").save(out)         # already black/white: keep the pixels, store 1-bit
    else:                                                                                                                       # threshold / qr: hard threshold at the native resolution (up to 2048 px)
        with Image.open(path) as im0: width = min(im0.width, 2048)
        bits, _ = H.halftone_image(path, "threshold", width); H.save_bw_png(bits, out)
    return dict(action=act, texture=out, message="Texture ready: continue with dual-tone-apply apply_texture.py.")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter); ap.add_argument("image"); ap.add_argument("--prompt", default=""); ap.add_argument("-o", "--outdir")
    a = ap.parse_args(argv)
    try: r = prepare_image(a.image, a.prompt, a.outdir)
    except (OSError, ValueError) as e: r = {"error": str(e)}
    print(json.dumps(r))
    if "error" in r: return 2
    return 10 if r["action"] == "halftone" else 0


if __name__ == "__main__": sys.exit(main())
