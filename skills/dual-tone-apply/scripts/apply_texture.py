#!/usr/bin/env python3
"""Apply a texture image to a whole STL / 3MF part with a BOX projection and write a 3MF plus the 3D editor (standard library only; Pillow only if the texture is not already a PNG).

No feature recognition: every triangle takes the texture from the face of the box (+X -X +Y -Y +Z -Z around the part) that it points at most, one tile = `--tile-mm`
(default: the part's largest dimension, so each face of a cube shows the picture once). The user then refines placement in the viewer (paint / flood the triangles,
move / rotate / scale the projector, switch projection, or clear the texture and start fresh).

Usage:  apply_texture.py model.stl|model.3mf texture.png [-o out.3mf] [--tile-mm N] [--no-viewer] [--json]
Writes out.3mf (geometry unchanged, texture on every triangle) and out_viewer.html (unless --no-viewer). Exit 0 ok; 2 unreadable model / texture; 3 texture is not black/white (run halftone-image/scripts/prepare_image.py); 4 the 3MF already has textures and no editor is available; 1 the written 3MF failed its own checks.
A 3MF that already has textures is kept as is (copied unchanged); the new picture waits in the 3D editor's texture list with no triangles (Paint / Flood places it).
Library: apply_texture(model, texture, out=None, tile_mm=None, viewer=True) -> dict"""
import argparse, json, math, os, struct, sys, zipfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
PNG_SIG = b"\x89PNG\r\n\x1a\n"


# ---- reading
def _read_stl(path):
    data = open(path, "rb").read(); tris = []
    if len(data) >= 84 and 84 + 50 * struct.unpack("<I", data[80:84])[0] == len(data):          # binary STL
        n = struct.unpack("<I", data[80:84])[0]
        for i in range(n):
            f = struct.unpack("<12fH", data[84 + 50 * i:134 + 50 * i]); tris.append((f[3:6], f[6:9], f[9:12]))
    else:                                                                                          # ASCII STL
        pts = []
        for line in data.decode("utf-8", "replace").splitlines():
            p = line.split()
            if len(p) == 4 and p[0].lower() == "vertex": pts.append(tuple(float(x) for x in p[1:]))
        if not pts or len(pts) % 3: raise ValueError("not a readable STL file")
        tris = [tuple(pts[i:i + 3]) for i in range(0, len(pts), 3)]
    index, verts, out = {}, [], []
    for t in tris:                                                                                 # weld identical corners into an indexed mesh
        row = []
        for p in t:
            k = tuple(round(float(c), 6) for c in p)
            if k not in index: index[k] = len(verts); verts.append(k)
            row.append(index[k])
        out.append(tuple(row))
    return verts, out


def read_mesh(path):
    """-> (vertices [(x,y,z)] in millimetres, world space; triangles [(a,b,c)])."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".stl": verts, tris = _read_stl(path)
    elif ext == ".3mf":
        import apply_3mf_transform as T
        try: meshes = T.world_meshes(path)
        except (T.TransformError, KeyError, zipfile.BadZipFile, ValueError) as e: raise ValueError(f"cannot read 3MF: {e}")
        verts, tris = [], []
        for m in meshes:
            base = len(verts); verts += [tuple(v) for v in m["vertices"]]; tris += [(a + base, b + base, c + base) for a, b, c in m["triangles"]]
    else: raise ValueError("model must be .stl or .3mf")
    tris = [t for t in tris if len({*t}) == 3]
    if not tris: raise ValueError("the model has no triangles")
    return verts, tris


def read_texture(path):
    data = open(path, "rb").read()
    if data[:8] == PNG_SIG: return data
    try:
        import io
        from PIL import Image
        im = Image.open(path); im.load(); buf = io.BytesIO(); (im.convert("RGBA") if im.mode in ("P", "LA") else im).save(buf, "PNG"); return buf.getvalue()
    except Exception as e: raise ValueError(f"texture must be a PNG (or an image Pillow can convert): {e}")


class NotBlackWhite(ValueError): pass


def prepare_hint(texture):
    here = os.path.dirname(os.path.abspath(__file__)); sib = os.path.normpath(os.path.join(here, "..", "..", "halftone-image", "scripts", "prepare_image.py"))
    where = sib if os.path.isfile(sib) else "$(find / -name prepare_image.py -path '*halftone-image*' 2>/dev/null | head -1)"
    return f'python3 {where} "{texture}" --prompt "<the user\'s request, verbatim>" -o prepared'


def check_black_white(path, tol=12, allowed=0.01):
    """Refuse a texture that is not (almost) pure black/white: the halftone-image Skill must prepare it first (needs Pillow; skipped silently without it)."""
    try: from PIL import Image
    except ImportError: return
    try:
        im = Image.open(path); im.load()
        if im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info):
            im = im.convert("RGBA"); bg = Image.new("RGBA", im.size, (255, 255, 255, 255)); bg.alpha_composite(im); im = bg
        h = im.convert("L").histogram()
    except Exception: return
    n = sum(h); off = n - sum(h[:tol + 1]) - sum(h[255 - tol:])
    if n and off / n > allowed:
        raise NotBlackWhite(f"the texture is not pure black/white ({off / n:.0%} of its pixels are grey or colour). Do not write your own halftone code or viewer. Prepare it with the bundled script, then run apply_texture.py again with the texture_bw.png it makes "
                            f"(or give the user the halftone viewer it builds for continuous-tone images):\n  {prepare_hint(path)}")


# ---- box projection (identical to projectTriangle('box') in assets/uvmath.js with an identity projector)
def box_uv(tri, centre, tile):
    L = [[p[i] - centre[i] for i in range(3)] for p in tri]; s = tile
    a = [L[1][k] - L[0][k] for k in range(3)]; b = [L[2][k] - L[0][k] for k in range(3)]
    n = [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]; ax, ay, az = abs(n[0]), abs(n[1]), abs(n[2]); out = []
    for x, y, z in L:
        if az >= ax and az >= ay: out += [(x if n[2] >= 0 else -x) / s + 0.5, y / s + 0.5]
        elif ax >= ay: out += [(y if n[0] >= 0 else -y) / s + 0.5, z / s + 0.5]
        else: out += [(-x if n[1] >= 0 else x) / s + 0.5, z / s + 0.5]
    return out


# ---- writing
CT = ('<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
      '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/><Default Extension="png" ContentType="image/png"/></Types>')
RELS = ('<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
MODEL_RELS = ('<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
              '<Relationship Target="/3D/Textures/texture.png" Id="rel1" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dtexture"/></Relationships>')


def write_3mf(path, verts, tris, uvs, png):
    out = ['<?xml version="1.0" encoding="UTF-8"?><model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
           'xmlns:m="http://schemas.microsoft.com/3dmanufacturing/material/2015/02"><resources>',
           '<m:texture2d id="1" path="/3D/Textures/texture.png" contenttype="image/png" tilestyleu="wrap" tilestylev="wrap" filter="nearest"/>', '<m:texture2dgroup id="2" texid="1">']
    out += [f'<m:tex2coord u="{u:.6f}" v="{v:.6f}"/>' for t in uvs for u, v in zip(t[0::2], t[1::2])]
    out += ['</m:texture2dgroup><object id="3" type="model"><mesh><vertices>']
    out += [f'<vertex x="{x:.6f}" y="{y:.6f}" z="{z:.6f}"/>' for x, y, z in verts]
    out += ['</vertices><triangles>']
    out += [f'<triangle v1="{a}" v2="{b}" v3="{c}" pid="2" p1="{3 * i}" p2="{3 * i + 1}" p3="{3 * i + 2}"/>' for i, (a, b, c) in enumerate(tris)]
    out += ['</triangles></mesh></object></resources><build><item objectid="3"/></build></model>']
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CT); z.writestr("_rels/.rels", RELS); z.writestr("3D/3dmodel.model", "".join(out))
        z.writestr("3D/_rels/3dmodel.model.rels", MODEL_RELS); z.writestr("3D/Textures/texture.png", png)


class HasTextures(ValueError): pass


def count_textures(path):
    """Number of texture2d resources in a 3MF (0 for STL / unreadable)."""
    if os.path.splitext(path)[1].lower() != ".3mf": return 0
    try:
        with zipfile.ZipFile(path) as z:
            import re
            return sum(len(re.findall(rb"<(?:\w+:)?texture2d\b", z.read(n))) for n in z.namelist() if n.lower().endswith(".model"))
    except (OSError, zipfile.BadZipFile): return 0


def apply_texture(model, texture, out=None, tile_mm=None, viewer=True):
    check_black_white(texture); n_tex = count_textures(model)
    if n_tex:                                                                                      # keep every existing texture: copy the file unchanged, the editor gets the new picture with NO triangles
        if not viewer: raise HasTextures(f"the model already has {n_tex} texture{'s' if n_tex > 1 else ''}, which this tool would overwrite. Open the 3MF in the 3D editor (or Dual-Tone Studio), add the new picture there with Add New, place it with Paint or Flood and download the 3MF")
        import shutil
        out = out or os.path.splitext(model)[0] + "_textured.3mf"
        if os.path.abspath(out) != os.path.abspath(model): shutil.copyfile(model, out)
        res = dict(output=out, existing_textures=n_tex, new_texture_pending=True, projection="box", valid=True, errors=[])
        try:
            import make_viewer
            vp = os.path.splitext(out)[0] + "_viewer.html"; r = make_viewer.make_viewer(out, vp, projection={"type": "box", "scale": 1.0}, texture=texture); res["viewer"] = vp; res["valid"] = r["valid"]; res["errors"] = r["errors"]
        except (ImportError, OSError): res["viewer_unavailable"] = True
        return res
    verts, tris = read_mesh(model); png = read_texture(texture)
    lo = [min(v[i] for v in verts) for i in range(3)]; hi = [max(v[i] for v in verts) for i in range(3)]
    centre = [(lo[i] + hi[i]) / 2 for i in range(3)]; dim = max(hi[i] - lo[i] for i in range(3)) or 1.0; tile = float(tile_mm) if tile_mm else dim
    if tile <= 0: raise ValueError("--tile-mm must be positive")
    out = out or os.path.splitext(model)[0] + "_textured.3mf"
    uvs = [box_uv([verts[a], verts[b], verts[c]], centre, tile) for a, b, c in tris]
    write_3mf(out, verts, tris, uvs, png)
    try: import preflight_3mf; rep = preflight_3mf.validate(out)                                  # the checker may be absent when the scripts were recreated from the source mirrors
    except ImportError: rep = {"valid": True, "errors": []}
    res = dict(output=out, triangles=len(tris), size_mm=[round(hi[i] - lo[i], 3) for i in range(3)], tile_mm=round(tile, 4), projection="box", valid=rep["valid"], errors=[e["code"] for e in rep["errors"]])
    if viewer:
        try:
            import make_viewer
            vp = os.path.splitext(out)[0] + "_viewer.html"
            make_viewer.make_viewer(out, vp, projection={"type": "box", "scale": round(tile / dim, 6)}); res["viewer"] = vp
        except (ImportError, OSError): res["viewer_unavailable"] = True                            # no bundled viewer files here: the 3MF alone is the result
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("model"); ap.add_argument("texture"); ap.add_argument("-o", "--output"); ap.add_argument("--tile-mm", type=float); ap.add_argument("--no-viewer", action="store_true"); ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try: r = apply_texture(a.model, a.texture, a.output, a.tile_mm, not a.no_viewer)
    except HasTextures as e: print(f"apply_texture: {e}", file=sys.stderr); return 4
    except NotBlackWhite as e: print(f"apply_texture: {e}", file=sys.stderr); return 3
    except (OSError, ValueError) as e: print(f"apply_texture: {e}", file=sys.stderr); return 2
    if a.json: print(json.dumps(r, indent=2))
    else: print(("kept the model's existing textures; the new picture waits in the editor's texture list with no triangles (Paint or Flood places it)\n" if r.get("new_texture_pending") else "") + f"textured: {r['output']}" + (f"\nviewer: {r['viewer']}" if "viewer" in r else "\n(the 3D editor files are not available in this environment: deliver the 3MF only and say the editor needs the full plugin)" if r.get("viewer_unavailable") else "") + ("" if r["valid"] else "\nWARNING: the written file has problems: " + ", ".join(r["errors"])))
    return 0 if r["valid"] else 1


if __name__ == "__main__": sys.exit(main())
