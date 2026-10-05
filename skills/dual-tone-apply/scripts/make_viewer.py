#!/usr/bin/env python3
"""Make a self-contained Three.js viewer (one offline HTML file) for a 3MF, with live UV controls (standard library only).

The page shows the model and, per texture, sliders for rotate (-180..180 deg), translate u / v (-0.5..0.5) and scale (slider 0..3, larger values can be typed = texture size on the
surface). A Projection dropdown (planar / cylindrical / spherical / box) with a viewport gimbal can re-project the texture, and Paint / Flood tools choose which triangles carry it. The preview updates live; "Download adjusted 3MF" bakes the adjusted UVs into a new 3MF. Models without textures still get a viewer.

Usage:  make_viewer.py model.3mf [-o viewer.html] [--title TITLE] [--projection box [--projection-scale K]] [--json]
Library: make_viewer(path, out=None, title=None, projection=None) -> dict   (projection={'type': 'box', 'scale': 1.0} starts the viewer with that projector active)
"""
import argparse, base64, json, os, re, sys, zipfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import preflight_3mf

ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
LIMIT_MB = 25

def _read(name): return open(os.path.join(ASSETS, name), encoding="utf-8").read()

def _model_info(path):
    """(texture count, triangle count) from the model part; (0, 0) when unreadable."""
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read("3D/3dmodel.model").decode("utf-8", "replace")
    except (OSError, KeyError, zipfile.BadZipFile): return 0, 0
    return len(re.findall(r"<(?:\w+:)?texture2d\b", xml)), len(re.findall(r"<(?:\w+:)?triangle\b", xml))

def make_viewer(path, out=None, title=None, projection=None, texture=None):
    """Write the viewer next to the 3MF (or to out). Returns a JSON-serialisable dict; never raises for an invalid 3MF (the page shows the errors)."""
    warnings = []
    if not os.path.isfile(path): raise FileNotFoundError(path)
    out = out or os.path.splitext(path)[0] + "_viewer.html"
    rep = preflight_3mf.validate(path)
    textures, tris = _model_info(path)
    data = open(path, "rb").read()
    if len(data) > LIMIT_MB * 1024 * 1024: warnings.append(f"3MF is {len(data) / 1048576:.1f} MB; the viewer may be slow to open")
    if not rep["valid"]: warnings.append("preflight failed; the viewer shows the errors and may not render the model")
    fn = os.path.basename(path); title = title or os.path.splitext(fn)[0]
    tex = dict(name=os.path.basename(texture), b64=base64.b64encode(open(texture, 'rb').read()).decode()) if texture else None            # a picture to add as a new texture covering every triangle (a model without textures)
    meta = json.dumps(dict(title=title, filename=fn, triangles=tris, preflight=rep, projection=projection, texture=tex)).replace("</", "<\\/")
    html = _read("viewer_template.html")
    for key, val in (("__TITLE__", title.replace("&", "&amp;").replace("<", "&lt;")), ("__BUNDLE__", _read("viewer_bundle.js")), ("__UVMATH__", _read("uvmath.js")),
                     ("__META__", meta), ("__MODEL__", base64.b64encode(data).decode())):
        html = html.replace(key, val)
    with open(out, "w", encoding="utf-8") as f: f.write(html)
    return dict(output=out, bytes=os.path.getsize(out), textures=textures, triangles=tris, valid=rep["valid"], errors=[e["code"] for e in rep["errors"]], warnings=warnings)

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path"); ap.add_argument("-o", "--output"); ap.add_argument("--title"); ap.add_argument("--projection", choices=["planar", "cylindrical", "spherical", "box"]); ap.add_argument("--projection-scale", type=float, default=1.0); ap.add_argument("--json", action="store_true"); a = ap.parse_args(argv)
    try: r = make_viewer(a.path, a.output, a.title, {"type": a.projection, "scale": a.projection_scale} if a.projection else None)
    except OSError as e: print(f"make_viewer: {e}", file=sys.stderr); return 2
    print(json.dumps(r, indent=2) if a.json else f"viewer: {r['output']} ({r['bytes'] / 1024:.0f} KB)" + ("" if r['valid'] else " - WARNING: the model has problems and may not open correctly") + "".join(f"\nwarning: {w}" for w in r["warnings"]))
    return 0 if r["valid"] else 1
if __name__ == "__main__": sys.exit(main())
