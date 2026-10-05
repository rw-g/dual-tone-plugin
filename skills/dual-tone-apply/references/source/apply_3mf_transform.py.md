# Source of `scripts/apply_3mf_transform.py` (color-3d-model)

Verbatim copy. If `scripts/apply_3mf_transform.py` is not on disk, write the block below UNCHANGED to `color-3d-model/scripts/apply_3mf_transform.py` (keep the folder layout) and run it from there.

````python
#!/usr/bin/env python3
"""3MF transform helper: build, describe, compose and BAKE 3MF transforms (deterministic, standard library only).

CONVENTION (3MF Core spec): a transform is 12 numbers  "m00 m01 m02 m10 m11 m12 m20 m21 m22 m30 m31 m32"
and points are ROW vectors:   [x' y' z'] = [x y z] * R + t
    x' = m00*x + m10*y + m20*z + m30
    y' = m01*x + m11*y + m21*z + m31
    z' = m02*x + m12*y + m22*z + m32
so  m30 m31 m32 is the translation and a counter-clockwise rotation by theta about +Z (seen from +Z) is
    cos  sin  0   -sin  cos  0   0 0 1   0 0 0
A column-vector reading (x' = m00*x + m01*y + ...) reverses every rotation: that was the Phase 0 sign error (+30 deg became -30 deg).
Composition: "apply A first, then B" is the row-vector product A*B.
Hierarchy: world = vertex * component_transform * ... * build_item_transform  (innermost first).

Usage:
  apply_3mf_transform.py make [--scale SX SY SZ] [--rotate-x D] [--rotate-y D] [--rotate-z D] [--translate X Y Z]   (applied in the order given)
  apply_3mf_transform.py describe "m00 ... m32"
  apply_3mf_transform.py bake in.3mf out.stl|out.3mf [--json]     bake every build item's transforms into world-space vertices
"""
import argparse, json, math, re, struct, sys, zipfile
from xml.etree import ElementTree as ET

IDENTITY12 = [1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0]
class TransformError(ValueError): pass

# ---- 4x4 row-vector matrices as nested lists: p' = [x y z 1] . M
def identity(): return [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
def from12(v):
    try: v = [float(x) for x in v]
    except (TypeError, ValueError): raise TransformError("transform values must be numbers")
    if len(v) != 12 or not all(math.isfinite(x) for x in v): raise TransformError("a 3MF transform needs exactly 12 finite numbers")
    return [v[0:3] + [0.0], v[3:6] + [0.0], v[6:9] + [0.0], v[9:12] + [1.0]]
def to12(M): return [M[0][0], M[0][1], M[0][2], M[1][0], M[1][1], M[1][2], M[2][0], M[2][1], M[2][2], M[3][0], M[3][1], M[3][2]]
def parse_transform(s):
    if s is None or not str(s).strip(): return identity()
    return from12(str(s).replace(",", " ").split())
def to_string(M, digits=9): return " ".join(f"{(0.0 if abs(x) < 1e-12 else x):.{digits}g}" for x in to12(M))
def matmul(A, B): return [[sum(A[i][k] * B[k][j] for k in range(4)) for j in range(4)] for i in range(4)]
def compose(*ms):
    """compose(A, B, C) = apply A first, then B, then C  (row-vector product A*B*C)."""
    out = identity()
    for m in ms: out = matmul(out, m)
    return out
def translation(tx, ty, tz): M = identity(); M[3][:3] = [tx, ty, tz]; return M
def scaling(sx, sy=None, sz=None):
    sy = sx if sy is None else sy; sz = sx if sz is None else sz; M = identity(); M[0][0], M[1][1], M[2][2] = sx, sy, sz; return M
def rotation_z(deg): c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg)); M = identity(); M[0][0], M[0][1], M[1][0], M[1][1] = c, s, -s, c; return M
def rotation_x(deg): c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg)); M = identity(); M[1][1], M[1][2], M[2][1], M[2][2] = c, s, -s, c; return M
def rotation_y(deg): c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg)); M = identity(); M[0][0], M[0][2], M[2][0], M[2][2] = c, -s, s, c; return M
def apply_point(M, p): x, y, z = p; return tuple(x * M[0][j] + y * M[1][j] + z * M[2][j] + M[3][j] for j in range(3))
def apply_points(M, pts): return [apply_point(M, p) for p in pts]
def det3(M):
    a = M
    return (a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1]) - a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0]) + a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0]))
def is_identity(M, tol=1e-12): return all(abs(M[i][j] - (1.0 if i == j else 0.0)) <= tol for i in range(4) for j in range(4))
def describe(M):
    sx, sy, sz = (math.sqrt(sum(M[i][j] ** 2 for j in range(3))) for i in range(3)); d = det3(M)
    out = dict(transform=to_string(M), translation=[M[3][0], M[3][1], M[3][2]], scale=[sx, sy, sz], determinant=d, mirrored=d < 0)
    if min(sx, sy, sz) > 1e-12 and d != 0 and abs(sx - sy) < 1e-9 and abs(sy - sz) < 1e-9:
        R = [[M[i][j] / sx for j in range(3)] for i in range(3)]   # row-vector rotation matrix; for a Z rotation R[0][1] = sin, R[0][0] = cos
        if abs(R[2][2] - 1) < 1e-9 and abs(R[0][2]) < 1e-9 and abs(R[1][2]) < 1e-9:
            out["rotation_about_z_deg_ccw"] = math.degrees(math.atan2(R[0][1], R[0][0]))
    return out

# ---- baking
def _local(tag): return tag.rsplit("}", 1)[-1]
def _model_parts(z):
    rels = ET.fromstring(z.read("_rels/.rels")); main = "3D/3dmodel.model"
    for r in rels:
        if r.get("Type", "").endswith("/3dmodel"): main = r.get("Target").lstrip("/")
    return main

def apply_3mf_transform(transform, points):
    """Library entry point: transform = 12-number string/list (or None for identity); points = [(x,y,z), ...] -> [[x',y',z'], ...] (JSON-serialisable)."""
    M = parse_transform(transform) if isinstance(transform, str) or transform is None else from12(transform)
    return [list(p) for p in apply_points(M, points)]

def world_meshes(path):
    """-> list of dict(build_index, object_id, vertices[(x,y,z)] in MILLIMETRES world space, triangles[(a,b,c)], attrs[dict of triangle attrs]) for each build item.
    Mirrored transforms (negative determinant) get their triangle winding flipped so normals stay outward."""
    z = zipfile.ZipFile(path); main = _model_parts(z); root = ET.fromstring(z.read(main))
    unit = {"micron": 0.001, "millimeter": 1.0, "centimeter": 10.0, "inch": 25.4, "foot": 304.8, "meter": 1000.0}.get(root.get("unit", "millimeter"))
    if unit is None: raise TransformError("unknown unit " + str(root.get("unit")))
    objs = {o.get("id"): o for r in root if _local(r.tag) == "resources" for o in r if _local(o.tag) == "object"}
    build = next((c for c in root if _local(c.tag) == "build"), None); out = []
    def emit(oid, M, depth, acc):
        if depth > 32: raise TransformError("component recursion too deep")
        o = objs.get(oid)
        if o is None: raise TransformError(f"object {oid} not found")
        for ch in o:
            if _local(ch.tag) == "mesh":
                vs = [tuple(float(v.get(a)) for a in "xyz") for v in next(c for c in ch if _local(c.tag) == "vertices")]
                tris = [dict(t.attrib) for t in next(c for c in ch if _local(c.tag) == "triangles")]
                W = apply_points(M, vs); flip = det3(M) < 0; base = len(acc["v"]); acc["v"] += [tuple(x * unit for x in p) for p in W]
                for t in tris:
                    a, b, c = int(t["v1"]) + base, int(t["v2"]) + base, int(t["v3"]) + base
                    t2 = dict(t)
                    if flip: a, b, c = a, c, b; t2["p2"], t2["p3"] = t.get("p3"), t.get("p2"); t2 = {k: v for k, v in t2.items() if v is not None}
                    acc["t"].append((a, b, c)); acc["a"].append(t2)
            elif _local(ch.tag) == "components":
                for c in ch:
                    if any(_local(k) == "path" for k in c.attrib): raise TransformError("external component paths (production extension) are not supported")
                    emit(c.get("objectid"), compose(parse_transform(c.get("transform")), M), depth + 1, acc)
    for i, it in enumerate(build if build is not None else []):
        acc = dict(v=[], t=[], a=[]); emit(it.get("objectid"), parse_transform(it.get("transform")), 0, acc)
        out.append(dict(build_index=i, object_id=it.get("objectid"), vertices=acc["v"], triangles=acc["t"], attrs=acc["a"]))
    return out

def write_stl_binary(path, meshes):
    tris = [(m["vertices"][a], m["vertices"][b], m["vertices"][c]) for m in meshes for a, b, c in m["triangles"]]
    with open(path, "wb") as f:
        f.write(b"baked world-space (apply_3mf_transform.py)".ljust(80, b"\0")); f.write(struct.pack("<I", len(tris)))
        for p, q, r in tris:
            u = [q[i] - p[i] for i in range(3)]; v = [r[i] - p[i] for i in range(3)]; n = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]]
            l = math.sqrt(sum(x * x for x in n)) or 1.0; f.write(struct.pack("<12fH", *[x / l for x in n], *p, *q, *r, 0))
    return len(tris)

def bake_3mf(src, dst):
    """Rewrite the main model part: one mesh object per build item with world-space vertices (in the file's own unit), identity build transforms,
    resources other than objects (materials, textures) kept. Object ids are renumbered above the highest existing id so they stay unique."""
    z = zipfile.ZipFile(src); main = _model_parts(z); root = ET.fromstring(z.read(main)); ns = root.tag[:root.tag.index("}") + 1] if root.tag.startswith("{") else ""
    unit_scale = {"micron": 0.001, "millimeter": 1.0, "centimeter": 10.0, "inch": 25.4, "foot": 304.8, "meter": 1000.0}[root.get("unit", "millimeter")]
    meshes = world_meshes(src); resources = next(r for r in root if _local(r.tag) == "resources"); build = next(c for c in root if _local(c.tag) == "build")
    ids = [int(e.get("id")) for e in resources if e.get("id") and e.get("id").isdigit()]; nxt = max(ids or [0]) + 1
    for o in [e for e in resources if _local(e.tag) == "object"]: resources.remove(o)
    old_items = list(build)
    for it in old_items: build.remove(it)
    for m in meshes:
        o = ET.SubElement(resources, ns + "object", id=str(nxt), type="model"); mesh = ET.SubElement(o, ns + "mesh"); vs = ET.SubElement(mesh, ns + "vertices")
        for x, y, zz in m["vertices"]: ET.SubElement(vs, ns + "vertex", x=repr(x / unit_scale), y=repr(y / unit_scale), z=repr(zz / unit_scale))
        ts = ET.SubElement(mesh, ns + "triangles")
        for (a, b, c), at in zip(m["triangles"], m["attrs"]):
            at = {k: v for k, v in at.items() if k not in ("v1", "v2", "v3")}; ET.SubElement(ts, ns + "triangle", v1=str(a), v2=str(b), v3=str(c), **at)
        ET.SubElement(build, ns + "item", objectid=str(nxt)); nxt += 1
    data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as out:
        for n in z.namelist(): out.writestr(n, data if n == main else z.read(n))
    return len(meshes)

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter); sub = ap.add_subparsers(dest="cmd", required=True)
    class Op(argparse.Action):   # keep command-line order: operations are applied left to right
        def __call__(self, parser, ns, values, option_string=None): ns.ops = list(getattr(ns, "ops", None) or []) + [(self.dest, values)]
    mk = sub.add_parser("make"); mk.set_defaults(ops=[])
    mk.add_argument("--scale", type=float, nargs=3, action=Op, metavar=("SX", "SY", "SZ")); mk.add_argument("--rotate-x", type=float, action=Op, dest="rotate_x"); mk.add_argument("--rotate-y", type=float, action=Op, dest="rotate_y")
    mk.add_argument("--rotate-z", type=float, action=Op, dest="rotate_z"); mk.add_argument("--translate", type=float, nargs=3, action=Op, metavar=("X", "Y", "Z"))
    ds = sub.add_parser("describe"); ds.add_argument("matrix")
    bk = sub.add_parser("bake"); bk.add_argument("src"); bk.add_argument("dst"); bk.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "make":
        fn = {"scale": lambda v: scaling(*v), "rotate_x": rotation_x, "rotate_y": rotation_y, "rotate_z": rotation_z, "translate": lambda v: translation(*v)}
        print(to_string(compose(*[fn[k](v) for k, v in a.ops]) if a.ops else identity())); return 0
    if a.cmd == "describe": print(json.dumps(describe(parse_transform(a.matrix)), indent=1)); return 0
    if a.cmd == "bake":
        if a.dst.lower().endswith(".stl"): ms = world_meshes(a.src); n = write_stl_binary(a.dst, ms); res = dict(output=a.dst, format="stl", triangles=n, build_items=len(ms))
        else: n = bake_3mf(a.src, a.dst); res = dict(output=a.dst, format="3mf", build_items=n)
        print(json.dumps(res) if a.json else f"wrote {a.dst}: {res}"); return 0
if __name__ == "__main__": sys.exit(main())
````
