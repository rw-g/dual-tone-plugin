#!/usr/bin/env python3
"""Deterministic 3MF preflight validator (standard library only; no LLM, no network). Run it on the SAVED file before telling the user it is valid.

  preflight_3mf.py model.3mf                      human-readable report, exit code 0 = valid, 1 = errors, 2 = cannot read
  preflight_3mf.py model.3mf --json               machine-readable JSON {"valid", "errors", "warnings", "summary"}
  preflight_3mf.py model.3mf --expect '{"expected_objects": 2, "expected_textures": 1, "expected_colors": 2}'
  preflight_3mf.py model.3mf --expect-file expectations.json

Expectation keys (all optional): expected_objects (mesh objects), expected_build_items, expected_textures, expected_colors (distinct colours used by
triangles/objects), expected_triangles (exact), min_triangles, allowed_colors (e.g. ["#000000","#FFFFFF"]; any other used colour is an error),
textures_binary (true => every texture must contain only black/white pixels; needs Pillow), require_textures (true => at least one texture must be used).
As a library:  from preflight_3mf import validate; report = validate(path, expectations_dict)
"""
import argparse, json, math, os, re, struct, sys, zipfile
from xml.etree import ElementTree as ET
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apply_3mf_transform import parse_transform, TransformError, det3, compose, apply_point, identity   # same dir

UNITS = {"micron": 0.001, "millimeter": 1.0, "centimeter": 10.0, "inch": 25.4, "foot": 304.8, "meter": 1000.0}
REL_3DMODEL = "http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"
REL_TEXTURE = "http://schemas.microsoft.com/3dmanufacturing/2013/01/3dtexture"
TEX_CT = {"image/png", "image/jpeg", "application/vnd.ms-package.3dmanufacturing-3dmodeltexture"}
HEX = re.compile(r"^#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$")
MISPLACED = {"tex2coord", "color", "base", "vertex", "triangle"}
def _ln(t): return t.rsplit("}", 1)[-1]

class Report:
    def __init__(self): self.errors, self.warnings, self.summary = [], [], {}
    def err(self, code, msg, **kw): self.errors.append(dict(code=code, message=msg, **kw))
    def warn(self, code, msg, **kw): self.warnings.append(dict(code=code, message=msg, **kw))
    def as_dict(self): return dict(valid=not self.errors, errors=self.errors, warnings=self.warnings, summary=self.summary)

def _image_info(data):
    """-> (kind, w, h) from PNG/JPEG magic without Pillow; kind None if unrecognised."""
    if data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR": return "png", *struct.unpack(">II", data[16:24])
    if data[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF: i += 1; continue
            m = data[i + 1]
            if m in (0xC0, 0xC1, 0xC2): return "jpeg", struct.unpack(">H", data[i + 7:i + 9])[0], struct.unpack(">H", data[i + 5:i + 7])[0]
            if m in (0xD8, 0x01) or 0xD0 <= m <= 0xD7: i += 2; continue
            i += 2 + struct.unpack(">H", data[i + 2:i + 4])[0]
        return "jpeg", None, None
    return None, None, None

def validate(path, expectations=None):
    R = Report(); expectations = expectations or {}
    try: z = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, FileNotFoundError, IsADirectoryError, OSError) as e:
        R.err("NOT_A_ZIP", f"cannot open as a ZIP/3MF container: {e}"); return R.as_dict()
    names = z.namelist()
    dups = sorted({n for n in names if names.count(n) > 1})
    for n in dups: R.err("DUPLICATE_ZIP_ENTRY", f"zip entry {n} appears more than once")
    try:
        bad = z.testzip()
        if bad: R.err("ZIP_CORRUPT", f"zip member {bad} fails its CRC check")
    except Exception as e: R.err("ZIP_CORRUPT", str(e))
    def xml(name):
        try: return ET.fromstring(z.read(name))
        except ET.ParseError as e: R.err("XML_PARSE_ERROR", f"{name}: {e}", part=name); return None
        except KeyError: return None
    ct = xml("[Content_Types].xml") if "[Content_Types].xml" in names else (R.err("MISSING_CONTENT_TYPES", "[Content_Types].xml is missing") or None)
    ctypes_default, ctypes_override = {}, {}
    if ct is not None:
        for e in ct:
            if _ln(e.tag) == "Default": ctypes_default[e.get("Extension", "").lower()] = e.get("ContentType")
            elif _ln(e.tag) == "Override": ctypes_override[e.get("PartName")] = e.get("ContentType")
    rels = xml("_rels/.rels") if "_rels/.rels" in names else (R.err("MISSING_RELS", "_rels/.rels is missing") or None)
    main = None
    if rels is not None:
        for r in rels:
            if r.get("Type") == REL_3DMODEL: main = (r.get("Target") or "").lstrip("/")
    if main is None and rels is not None: R.err("NO_MODEL_RELATIONSHIP", "_rels/.rels has no 3D model relationship")
    if main and main not in names: R.err("NO_MODEL_PART", f"model part {main} named by _rels/.rels is not in the package"); main = None
    if main is None: return _finish(R, expectations)
    root = xml(main)
    if root is None: return _finish(R, expectations)
    unit = root.get("unit", "millimeter")
    if unit not in UNITS: R.err("UNKNOWN_UNIT", f"unit='{unit}' is not a valid 3MF unit", part=main)
    scale = UNITS.get(unit, 1.0)
    for c in root:
        if _ln(c.tag) in ("object", "basematerials", "colorgroup", "texture2d", "texture2dgroup", "multiproperties", "compositematerials"):
            R.err("RESOURCE_OUTSIDE_RESOURCES", f"<{_ln(c.tag)}> id='{c.get('id')}' is a direct child of <model>; resources must be inside <resources>", id=c.get("id"))
    resources = next((c for c in root if _ln(c.tag) == "resources"), None); build = next((c for c in root if _ln(c.tag) == "build"), None)
    if resources is None: R.err("NO_RESOURCES", "model has no <resources>", part=main); return _finish(R, expectations)
    if build is None or not len(build): R.warn("NO_BUILD_ITEMS", "model has no <build> items: nothing will print", part=main)
    # ---- resource id space (ONE namespace for basematerials, colorgroups, textures, texture groups, objects, ...)
    seen, objects, groups, textures, tex_groups, colorgroups, basemats = {}, {}, {}, {}, {}, {}, {}; misplaced = {}
    for r in resources:
        t = _ln(r.tag); rid = r.get("id")
        if t in MISPLACED: misplaced[t] = misplaced.get(t, 0) + 1; continue
        if rid is None: R.err("MISSING_RESOURCE_ID", f"<{t}> resource has no id"); continue
        if not re.fullmatch(r"[1-9][0-9]*|0", rid): R.err("BAD_RESOURCE_ID", f"<{t}> id='{rid}' is not a non-negative integer")
        if rid in seen: R.err("DUPLICATE_RESOURCE_ID", f"Resource ID {rid} is used by both <{seen[rid]}> and <{t}>; every resource needs its own id", id=rid)
        else: seen[rid] = t
        if t == "object": objects[rid] = r
        elif t == "basematerials": basemats[rid] = r
        elif t == "colorgroup": colorgroups[rid] = r
        elif t == "texture2d": textures[rid] = r
        elif t == "texture2dgroup": tex_groups[rid] = r
    for t, n in misplaced.items(): R.err("MISPLACED_ELEMENT", f"{n} <{t}> element(s) sit directly under <resources>; they belong inside their group/mesh", element=t, count=n)
    # ---- colours
    group_colors, used_colors = {}, {}
    for rid, g in basemats.items():
        bases = [b for b in g if _ln(b.tag) == "base"]
        if not bases: R.err("EMPTY_BASEMATERIALS", f"basematerials {rid} has no <base>")
        cols = []
        for b in bases:
            c = b.get("displaycolor")
            if c is None or not HEX.match(c): R.err("INVALID_COLOR", f"basematerials {rid}: displaycolor '{c}' is not #RRGGBB or #RRGGBBAA"); cols.append(None)
            else: cols.append(c[:7].upper())
        group_colors[rid] = cols
    for rid, g in colorgroups.items():
        cols = []
        for c in [c for c in g if _ln(c.tag) == "color"]:
            v = c.get("color")
            if v is None or not HEX.match(v): R.err("INVALID_COLOR", f"colorgroup {rid}: color '{v}' is not #RRGGBB or #RRGGBBAA"); cols.append(None)
            else: cols.append(v[:7].upper())
        group_colors[rid] = cols
    # ---- textures: file, relationship, content type, decodability
    model_rels_name = os.path.join(os.path.dirname(main), "_rels", os.path.basename(main) + ".rels").replace(os.sep, "/")
    texrel_targets = set()
    if model_rels_name in names:
        mr = xml(model_rels_name)
        if mr is not None: texrel_targets = {(r.get("Target") or "").lstrip("/") for r in mr if r.get("Type") == REL_TEXTURE}
    tex_info = {}
    for rid, t in textures.items():
        p = t.get("path") or ""; ctype = t.get("contenttype")
        if not p.startswith("/") or ".." in p.split("/"): R.err("TEXTURE_PATH_INVALID", f"texture2d {rid}: path '{p}' must be an absolute part name such as /3D/Textures/logo.png"); 
        part = p.lstrip("/")
        if part not in names: R.err("TEXTURE_FILE_MISSING", f"texture2d {rid}: '{p}' is not in the package", id=rid); continue
        if ctype not in ("image/png", "image/jpeg"): R.err("TEXTURE_CONTENTTYPE_INVALID", f"texture2d {rid}: contenttype='{ctype}' must be image/png or image/jpeg")
        kind, w, h = _image_info(z.read(part))
        if kind is None: R.err("TEXTURE_UNDECODABLE", f"texture2d {rid}: '{p}' is not a recognisable PNG/JPEG", id=rid)
        elif ctype and ctype.split("/")[-1] != kind: R.err("TEXTURE_CONTENTTYPE_MISMATCH", f"texture2d {rid}: declared {ctype} but file is {kind}")
        if part not in texrel_targets: R.err("TEXTURE_RELATIONSHIP_MISSING", f"texture '{p}' needs a 3D Texture relationship ({REL_TEXTURE}) from the model part in {model_rels_name}", id=rid)
        ext = os.path.splitext(part)[1].lstrip(".").lower(); eff = ctypes_override.get("/" + part) or ctypes_default.get(ext)
        if eff not in TEX_CT: R.warn("TEXTURE_PART_CONTENT_TYPE", f"texture part '{p}' has package content type '{eff}' (expected image/png, image/jpeg or the 3dmodeltexture type) in [Content_Types].xml")
        tex_info[rid] = dict(part=part, kind=kind, w=w, h=h)
    for rid, g in tex_groups.items():
        if g.get("texid") not in textures: R.err("TEXTURE_GROUP_TEXID_UNRESOLVED", f"texture2dgroup {rid}: texid='{g.get('texid')}' is not a texture2d resource", id=rid)
    # ---- UVs
    group_len, uv_issue_cap = {}, 0
    for rid, g in tex_groups.items():
        n = 0
        for c in g:
            if _ln(c.tag) != "tex2coord": R.err("UNEXPECTED_ELEMENT", f"texture2dgroup {rid} contains <{_ln(c.tag)}> (only <tex2coord> allowed)"); continue
            n += 1
            try: u, v = float(c.get("u")), float(c.get("v"))
            except (TypeError, ValueError): R.err("UV_NOT_NUMERIC", f"texture2dgroup {rid}: tex2coord #{n-1} has non-numeric u/v ('{c.get('u')}', '{c.get('v')}')"); continue
            if not (math.isfinite(u) and math.isfinite(v)): R.err("UV_NOT_NUMERIC", f"texture2dgroup {rid}: tex2coord #{n-1} is not finite")
            elif (u < -1e-6 or u > 1 + 1e-6 or v < -1e-6 or v > 1 + 1e-6) and uv_issue_cap < 5:
                uv_issue_cap += 1; R.warn("UV_OUT_OF_BOUNDS", f"texture2dgroup {rid}: tex2coord #{n-1} = ({u:g},{v:g}) is outside 0..1 (tiling/wrap relies on tilestyle; slicers may clamp)")
        group_len[rid] = n
    # ---- objects / meshes
    n_mesh_obj, n_tris, per_obj_world = 0, 0, {}
    def prop_group_len(pid):
        if pid in group_colors: return len(group_colors[pid])
        if pid in group_len: return group_len[pid]
        return None
    used_tex = set(); mesh_ids = set()
    for oid, o in objects.items():
        mesh = next((c for c in o if _ln(c.tag) == "mesh"), None); comps = next((c for c in o if _ln(c.tag) == "components"), None)
        if mesh is None and comps is None: R.err("OBJECT_EMPTY", f"object {oid} has neither <mesh> nor <components>", id=oid); continue
        opid, opi = o.get("pid"), o.get("pindex")
        if opid is not None and prop_group_len(opid) is None and opid not in seen: R.err("MATERIAL_REF_UNRESOLVED", f"object {oid}: pid='{opid}' does not match any property resource", id=oid)
        if opid in group_colors:
            try:
                if opi is not None and not (0 <= int(opi) < len(group_colors[opid])): R.err("PINDEX_OUT_OF_RANGE", f"object {oid}: pindex={opi} outside group {opid} (size {len(group_colors[opid])})")
                elif group_colors[opid][int(opi or 0)]: used_colors.setdefault(group_colors[opid][int(opi or 0)], set()).add(("object", oid))
            except (ValueError, IndexError): R.err("PINDEX_OUT_OF_RANGE", f"object {oid}: bad pindex '{opi}'")
        if mesh is None: continue
        verts = next((c for c in mesh if _ln(c.tag) == "vertices"), None); tris = next((c for c in mesh if _ln(c.tag) == "triangles"), None)
        if verts is None or tris is None or not len(verts) or not len(tris): R.err("EMPTY_MESH", f"object {oid}: mesh needs <vertices> and <triangles> with at least one entry each", id=oid); continue
        mesh_ids.add(oid); n_mesh_obj += 1; nv = len(verts); bad_v = 0; P = []
        for i, v in enumerate(verts):
            try:
                p = tuple(float(v.get(k)) for k in "xyz")
                if not all(math.isfinite(x) for x in p): raise ValueError
                P.append(p)
            except (TypeError, ValueError): bad_v += 1; P.append((0.0, 0.0, 0.0))
        if bad_v: R.err("BAD_VERTEX", f"object {oid}: {bad_v} vertices have missing/non-numeric/non-finite coordinates", id=oid)
        oob, degenerate, badref, badidx, nopid = 0, 0, 0, 0, 0
        for i, t in enumerate(tris):
            try: a, b, c = (int(t.get(k)) for k in ("v1", "v2", "v3"))
            except (TypeError, ValueError): oob += 1; continue
            if not all(0 <= x < nv for x in (a, b, c)): oob += 1; continue
            if len({a, b, c}) < 3: degenerate += 1
            n_tris += 1; pid = t.get("pid") or opid
            if pid is None:
                if t.get("p1") is not None: nopid += 1
                continue
            if pid not in seen: badref += 1; continue
            if pid in tex_groups:
                tid = tex_groups[pid].get("texid"); used_tex.add(tid)
                for k in ("p1", "p2", "p3"):
                    if t.get(k) is None: badidx += 1; break
            plen = prop_group_len(pid)
            if plen is None: continue
            try: idx = [int(t.get(k)) for k in ("p1", "p2", "p3") if t.get(k) is not None] or [int(opi or 0)]
            except ValueError: badidx += 1; continue
            if any(not (0 <= j < plen) for j in idx): badidx += 1
            elif pid in group_colors:
                cs = {group_colors[pid][j] for j in idx}
                for cc in cs:
                    if cc: used_colors.setdefault(cc, set()).add(("triangle", oid))
        if oob: R.err("TRIANGLE_INDEX_OUT_OF_RANGE", f"object {oid}: {oob} triangles reference vertex indices outside 0..{nv-1} (or are non-integer)", id=oid)
        if degenerate: R.warn("DEGENERATE_TRIANGLE", f"object {oid}: {degenerate} triangles repeat a vertex index", id=oid)
        if nopid: R.err("MATERIAL_REF_UNRESOLVED", f"object {oid}: {nopid} triangles give p1 but there is no pid on the triangle or the object", id=oid)
        if badref: R.err("MATERIAL_REF_UNRESOLVED", f"object {oid}: {badref} triangles have a pid that is not a resource id", id=oid)
        if badidx: R.err("PINDEX_OUT_OF_RANGE", f"object {oid}: {badidx} triangles have p1/p2/p3 missing or outside the property group", id=oid)
        per_obj_world[oid] = P
    # ---- components, build, transforms, world bbox
    def check_t(s, where):
        try:
            M = parse_transform(s)
        except TransformError as e: R.err("BAD_TRANSFORM", f"{where}: {e} (transform='{s}')"); return identity()
        d = det3(M)
        if abs(d) < 1e-12: R.warn("SINGULAR_TRANSFORM", f"{where}: transform has zero determinant (flattens the object)")
        elif d < 0: R.warn("MIRRORED_TRANSFORM", f"{where}: transform mirrors the object (negative determinant); triangle winding must be flipped by the consumer")
        return M
    color_children = {}
    for oid, o in objects.items():
        comps = next((c for c in o if _ln(c.tag) == "components"), None)
        if comps is None: continue
        refs = []
        for c in comps:
            if any(_ln(k) == "path" for k in c.attrib): continue   # external part (production extension): not followed
            cid = c.get("objectid"); check_t(c.get("transform"), f"object {oid} component")
            if cid not in objects: R.err("COMPONENT_REF_MISSING", f"object {oid}: component objectid='{cid}' does not exist", id=oid)
            else: refs.append(cid)
        color_children[oid] = refs
    state = {}
    def dfs(n, path):
        state[n] = 1
        for m in color_children.get(n, []):
            if state.get(m) == 1: R.err("COMPONENT_CYCLE", f"components form a cycle: {' -> '.join(path + [n, m])}"); continue
            if m not in state: dfs(m, path + [n])
        state[n] = 2
    for n in list(color_children): 
        if n not in state: dfs(n, [])
    items = list(build) if build is not None else []
    bb_min, bb_max = [math.inf] * 3, [-math.inf] * 3
    def walk(oid, M, depth=0):
        if depth > 16 or oid not in objects: return
        o = objects[oid]
        if oid in per_obj_world:
            for p in per_obj_world[oid]:
                q = apply_point(M, p)
                for k in range(3): bb_min[k] = min(bb_min[k], q[k] * scale); bb_max[k] = max(bb_max[k], q[k] * scale)
        comps = next((c for c in o if _ln(c.tag) == "components"), None)
        for c in (comps if comps is not None else []):
            if any(_ln(k) == "path" for k in c.attrib): continue
            try: walk(c.get("objectid"), compose(parse_transform(c.get("transform")), M), depth + 1)
            except TransformError: pass
    for i, it in enumerate(items):
        oid = it.get("objectid")
        if oid not in objects: R.err("BUILD_REF_MISSING", f"build item {i}: objectid='{oid}' is not an object resource"); continue
        M = check_t(it.get("transform"), f"build item {i}")
        if objects[oid].get("type") in ("support", "solidsupport", "surface"): R.warn("BUILD_OBJECT_TYPE", f"build item {i} references an object of type '{objects[oid].get('type')}'")
        walk(oid, M)
    # ---- unused / expectations
    for rid, t in textures.items():
        if rid not in {g.get("texid") for g in tex_groups.values()}: R.warn("TEXTURE_UNUSED", f"texture2d {rid} is not referenced by any texture2dgroup")
    for rid, g in tex_groups.items():
        if g.get("texid") in textures and g.get("texid") not in used_tex and rid not in [t.get("pid") for o in objects.values() for t in o.iter() if _ln(t.tag) == "triangle"]: R.warn("TEXTURE_GROUP_UNUSED", f"texture2dgroup {rid} is not used by any triangle")
    tex_used_n = len({tid for tid in used_tex if tid in textures})
    R.summary = dict(unit=unit, objects=len(objects), mesh_objects=n_mesh_obj, build_items=len(items), triangles=n_tris, textures=len(textures), textures_used=tex_used_n,
                     colors_used=sorted(used_colors), distinct_colors=len(used_colors), world_bbox_mm=None if bb_min[0] == math.inf else [[round(x, 4) for x in bb_min], [round(x, 4) for x in bb_max]],
                     resource_ids=len(seen))
    ex = expectations
    def expect(key, actual, cmp="eq"):
        if key not in ex: return
        want = ex[key]; ok = actual == want if cmp == "eq" else actual >= want
        if not ok: R.err("EXPECTATION_FAILED", f"{key}: expected {'at least ' if cmp == 'min' else ''}{want}, found {actual}", expectation=key, expected=want, actual=actual)
    expect("expected_objects", n_mesh_obj); expect("expected_build_items", len(items)); expect("expected_textures", len(textures)); expect("expected_colors", len(used_colors))
    expect("expected_triangles", n_tris); expect("min_triangles", n_tris, "min")
    if ex.get("require_textures") and not tex_used_n: R.err("EXPECTATION_FAILED", "require_textures: no texture is used by any triangle", expectation="require_textures")
    if "allowed_colors" in ex:
        allowed = {c.upper() for c in ex["allowed_colors"]}
        for c in sorted(used_colors):
            if c not in allowed: R.err("COLOR_NOT_ALLOWED", f"colour {c} is used but only {sorted(allowed)} are allowed", color=c)
    if ex.get("textures_binary"):
        try:
            from PIL import Image; import io
            for rid, info in tex_info.items():
                im = Image.open(io.BytesIO(z.read(info["part"]))).convert("RGBA"); raw = im.tobytes(); odd = sum(1 for i in range(0, len(raw), 4) if raw[i + 3] > 0 and (raw[i], raw[i + 1], raw[i + 2]) not in ((0, 0, 0), (255, 255, 255)))
                if odd: R.err("TEXTURE_NOT_BINARY", f"texture {info['part']}: {odd} visible pixels are neither pure black nor pure white (anti-aliasing/greys)", texture=info["part"])
        except ImportError: R.warn("CHECK_SKIPPED", "textures_binary requested but Pillow is not available; not verified")
    return _finish(R, ex)

def _finish(R, ex): return R.as_dict()

def preflight_3mf(path, expectations=None):
    """Library entry point (stable interface for future tool wrappers): path + optional expectations dict -> JSON-serialisable report."""
    return validate(path, expectations)

def format_human(rep, path):
    L = [f"preflight_3mf: {path}", f"RESULT: {'VALID' if rep['valid'] else 'INVALID'}  ({len(rep['errors'])} errors, {len(rep['warnings'])} warnings)"]
    s = rep.get("summary") or {}
    if s: L.append("summary: " + ", ".join(f"{k}={v}" for k, v in s.items()))
    for e in rep["errors"]: L.append(f"  ERROR   {e['code']}: {e['message']}")
    for w in rep["warnings"]: L.append(f"  warning {w['code']}: {w['message']}")
    return "\n".join(L)

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter); ap.add_argument("path"); ap.add_argument("--json", action="store_true")
    ap.add_argument("--expect"); ap.add_argument("--expect-file"); ap.add_argument("--strict", action="store_true", help="treat warnings as errors for the exit code"); a = ap.parse_args(argv)
    ex = {}
    try:
        if a.expect_file: ex = json.load(open(a.expect_file))
        if a.expect: ex.update(json.loads(a.expect))
    except (OSError, json.JSONDecodeError) as e: print(f"bad expectations: {e}", file=sys.stderr); return 2
    rep = validate(a.path, ex); print(json.dumps(rep, indent=2) if a.json else format_human(rep, a.path))
    if rep["errors"] and rep["errors"][0]["code"] in ("NOT_A_ZIP",): return 2
    return 0 if rep["valid"] and not (a.strict and rep["warnings"]) else 1
if __name__ == "__main__": sys.exit(main())
