#!/usr/bin/env python3
"""Make a self-contained halftone viewer (one offline HTML file) for a grayscale or colour image (numpy + Pillow).

The page shows the original and the black/white halftone side by side with presets, tone controls, 19 presets across screens, lines, error diffusion,
ordered and blue-noise methods, a 1-bit PNG download, and an Apply button that hands the result plus the ORIGINAL REQUEST to the 3D skill.

Usage:  make_halftone_viewer.py image.png [-o halftone_viewer.html] [--prompt "original user request"] [--preset newsprint] [--width 800] [--title T] [--json]
Library: make_halftone_viewer(path, out=None, prompt='', preset=None, width=800, title=None) -> dict
Exit code: 0 viewer written; 2 unreadable image."""
import argparse, base64, io, json, os, sys
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import detect_image as D

ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
MAX_SIDE = 2048

def _read(name): return open(os.path.join(ASSETS, name), encoding="utf-8").read()

def _embed(path):
    im, _ = D._flatten(Image.open(path))                                           # alpha -> white, RGB
    if max(im.size) > MAX_SIDE:
        k = MAX_SIDE / max(im.size); im = im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.LANCZOS)
    buf = io.BytesIO(); im.save(buf, "PNG", optimize=True); mime, data = "image/png", buf.getvalue()
    if len(data) > 5 * 1024 * 1024:                                                 # big photos: JPEG keeps the page small
        buf = io.BytesIO(); im.save(buf, "JPEG", quality=90); mime, data = "image/jpeg", buf.getvalue()
    return f"data:{mime};base64," + base64.b64encode(data).decode(), im.size

def make_halftone_viewer(path, out=None, prompt="", preset=None, width=800, title=None):
    if not os.path.isfile(path): raise FileNotFoundError(path)
    info = D.detect_image(path)
    if "error" in info: raise ValueError(info["error"])
    out = out or os.path.splitext(path)[0] + "_halftone_viewer.html"
    uri, size = _embed(path)
    presets = json.load(open(os.path.join(ASSETS, "presets.json"), encoding="utf-8")); ids = {p["id"] for p in presets}
    preset = preset if preset in ids else (info.get("recommended_preset") or "newsprint")
    fn = os.path.basename(path); title = title or f"Halftone · {os.path.splitext(fn)[0]}"
    meta = dict(title=title, filename=fn, prompt=prompt or "", preset=preset, width=min(int(width), size[0]), detect=info)
    html = _read("halftone_template.html")
    for key, val in (("__TITLE__", title.replace("&", "&amp;").replace("<", "&lt;")), ("__ENGINE__", _read("halftone_engine.js")), ("__PRESETS__", json.dumps(presets)),
                     ("__META__", json.dumps(meta).replace("</", "<\\/")), ("__IMAGE__", uri)):
        html = html.replace(key, val)
    with open(out, "w", encoding="utf-8") as f: f.write(html)
    return dict(output=out, bytes=os.path.getsize(out), mode=info["mode"], kind=info["kind"], needs_halftone=info["needs_halftone"], is_qr=info["is_qr"], preset=preset, source_size=list(size))

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path"); ap.add_argument("-o", "--output"); ap.add_argument("--prompt", default=""); ap.add_argument("--preset"); ap.add_argument("--width", type=int, default=800)
    ap.add_argument("--title"); ap.add_argument("--json", action="store_true"); a = ap.parse_args(argv)
    try: r = make_halftone_viewer(a.path, a.output, a.prompt, a.preset, a.width, a.title)
    except (OSError, ValueError) as e: print(f"make_halftone_viewer: {e}", file=sys.stderr); return 2
    print(json.dumps(r, indent=2) if a.json else f"halftone viewer: {r['output']} ({r['bytes'] / 1024:.0f} KB; {r['mode']} / {r['kind']}; preset {r['preset']})" + ("\nwarning: this looks like a QR code; do not halftone it" if r["is_qr"] else ""))
    return 0
if __name__ == "__main__": sys.exit(main())
