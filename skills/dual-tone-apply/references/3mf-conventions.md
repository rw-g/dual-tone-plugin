# 3MF conventions (what a valid, slicer-friendly file looks like)

Sources: 3MF Core spec and Materials Extension (`github.com/3MFConsortium`), checked 2026-10-01; Phase 0 benchmark failures.

## Package layout
```
[Content_Types].xml
_rels/.rels                         -> relationship of Type .../2013/01/3dmodel to /3D/3dmodel.model
3D/3dmodel.model                    -> the XML below
3D/_rels/3dmodel.model.rels         -> ONLY if textures: one 3D Texture relationship per texture part
3D/Textures/<name>.png              -> texture images
```
Relationship types (exact strings):
- model: `http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel` (a made-up variant such as `.../3d/2013/01/3dmodel` leaves slicers unable to find the model)
- texture: `http://schemas.microsoft.com/3dmanufacturing/2013/01/3dtexture`

`[Content_Types].xml` needs Defaults for `rels` (`application/vnd.openxmlformats-package.relationships+xml`), `model` (`application/vnd.ms-package.3dmanufacturing-3dmodel+xml`) and the texture extension (`png` -> `image/png`).

## Resource IDs (Phase 0 failure #1)
One id space per model part: `basematerials`, `colorgroup`, `texture2d`, `texture2dgroup`, `multiproperties`, `object` ... all need **distinct** ids. Number them sequentially, e.g. materials=1, texture=2, texture group=3, first object=4. Triangle/vertex indices are separate (0-based) and unrelated to resource ids.

## Structure rules
- `<resources>` contains every resource; `<object>` is never a direct child of `<model>` (Phase 0: a sphere file did this).
- `<m:tex2coord>` lives only inside `<m:texture2dgroup>`; `<base>` only inside `<basematerials>`; `<color>` only inside `<colorgroup>`.
- `<build>` lists the objects to print; `objectid` must be an existing object.
- `unit="millimeter"` unless the source file says otherwise (keep the source unit; do not rescale silently). Units: micron, millimeter, centimeter, inch, foot, meter.
- Vertex coordinates are finite numbers; triangle `v1 v2 v3` are 0-based indices into that mesh's vertices; counter-clockwise winding seen from outside (normals outward).

## Solid colour (per-triangle)
```xml
<model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">
 <resources>
  <basematerials id="1"><base name="White" displaycolor="#FFFFFF"/><base name="Black" displaycolor="#000000"/></basematerials>
  <object id="2" type="model" pid="1" pindex="0">          <!-- default colour for triangles without their own -->
   <mesh><vertices>...</vertices>
    <triangles><triangle v1="0" v2="1" v3="2" pid="1" p1="1"/> ... </triangles></mesh>
  </object>
 </resources>
 <build><item objectid="2"/></build>
</model>
```
`pid` may be omitted on a triangle (it defaults to the object's `pid`); `p1` (and optionally p2/p3 for gradients) index into that group. Use `p1` only (flat colour). Colours are `#RRGGBB` or `#RRGGBBAA`.

## Image texture
```xml
<model unit="millimeter" xml:lang="en-US"
       xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
       xmlns:m="http://schemas.microsoft.com/3dmanufacturing/material/2015/02">
 <resources>
  <basematerials id="1"><base name="White" displaycolor="#FFFFFF"/></basematerials>
  <m:texture2d id="2" path="/3D/Textures/face.png" contenttype="image/png" filter="nearest" tilestyleu="clamp" tilestylev="clamp"/>
  <m:texture2dgroup id="3" texid="2">
    <m:tex2coord u="0" v="0"/> <m:tex2coord u="1" v="0"/> ...   <!-- implicit 0-based index -->
  </m:texture2dgroup>
  <object id="4" type="model" pid="1" pindex="0">
   <mesh><vertices>...</vertices><triangles>
     <triangle v1="0" v2="1" v3="2" pid="3" p1="0" p2="1" p3="2"/>   <!-- textured: pid = texture2dgroup, p1..p3 = its tex2coord indices -->
     <triangle v1="3" v2="4" v3="5" pid="1" p1="0"/>                 <!-- plain white -->
   </triangles></mesh>
  </object>
 </resources>
 <build><item objectid="4"/></build>
</model>
```
- Every textured triangle needs all of `pid p1 p2 p3`. A vertex shared by textured triangles with different UVs must be **duplicated** (UVs are per triangle corner via the group index, but keep one tex2coord per (triangle,corner) when island seams are involved).
- `texture2d` attributes: `path` (absolute part name starting `/`), `contenttype` (`image/png` or `image/jpeg`), `tilestyleu/v` (`wrap` default, `mirror`, `clamp`, `none`), `filter` (`auto`, `linear`, `nearest`). Use `nearest` + `clamp` for crisp logos/QR; `wrap` for repeating patterns.
- Texture alpha: spec says alpha is assumed opaque for a base-layer texture. Do not rely on a transparent PNG background; composite over the surface base colour.

## STL vs 3MF
STL = triangles only. No colour, no texture, no units, no object structure. Any request involving colour/logo/QR/sticker/pattern -> 3MF. If the user insists on STL, say that the appearance cannot be stored and offer 3MF (or geometry-based relief if they want physical features).

## Transforms
Build-item and component transforms are 12 numbers, **row-vector convention**: `x' = m00 x + m10 y + m20 z + m30` (translation = last three). Counter-clockwise +theta about Z: `cos sin 0 -sin cos 0 0 0 1 0 0 0`. Phase 0 reversed this (+30 became -30). Use `scripts/apply_3mf_transform.py` instead of writing matrices by hand. Hierarchy: vertex -> component transform(s) -> build item transform. Mirroring matrices (negative determinant) require flipped triangle winding when baked.

## Editing an existing 3MF
Preserve unknown parts (slicer metadata, thumbnails, config) unless asked; keep existing ids and avoid collisions when adding resources (use max(id)+1); preserve existing colours/materials not mentioned in the request; re-run preflight.

## Known Phase 0 invalid-file causes (all caught by `preflight_3mf.py`)
duplicate resource id; `<object>` outside `<resources>`; `<tex2coord>` directly in `<resources>`; texture without the 3D Texture relationship; wrong model relationship Type; texture group with too few tex2coords; triangle indices >= vertex count; build item referencing a missing object.
