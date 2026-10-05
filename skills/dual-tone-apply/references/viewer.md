# UV viewer (`scripts/make_viewer.py`)

`python scripts/make_viewer.py out.3mf [-o out_viewer.html] [--title T] [--json]` writes ONE offline HTML file (Three.js r160, 3MF loader, fflate, the model and the UV maths are inlined; no network). Run it after preflight passes, for every generated 3MF. Untextured models still get a viewer; the UV panel is hidden. An invalid 3MF still gets a page that shows the preflight errors (exit code 1).

## Controls (per texture; the dropdown selects the texture, each keeps its own values)
| Slider | Range | Meaning |
|---|---|---|
| Rotate | -180..180 deg | positive turns the picture counter-clockwise on the model, seen from outside, about the texture centre (0.5, 0.5) |
| Translate u / v | -0.5..0.5 | moves the picture toward +u (right) / +v (up) in texture space |
| Scale | 0..3 on the slider; larger values can be typed | size of the picture on the surface (2 = twice as large; UV divided by scale). 0 is treated as 0.01 |

The preview updates live (texture matrix, no geometry rewrite). **Download adjusted 3MF** writes `<name>_uv.3mf` with the same transform baked into every `tex2coord` of that texture's `texture2dgroup`s; all other parts are copied unchanged, and `tilestyleu/v` of the texture is set to `wrap` so UVs outside 0..1 tile.

## Interface
Tools (Orbit / Paint / Flood, Undo / Redo) and view buttons (Iso / Front / Top / Right, frame, wireframe) float over the model; the side panel has collapsible sections (Texture, Triangles, Projection, Transform, UV preview, Model checks) and a footer with the download. Explanations are hover tooltips. Light/dark theme and the panel can be toggled. Slider: double-click resets. Shortcuts: `O` `P` `F` tools, `X` Add/Remove, `[` `]` brush size, `Ctrl/Cmd+Z` undo (`+Shift` redo), `1`-`4` views, `W` wireframe, `H` panel. A dot on the download button means unsaved changes.

**Clear texture from all triangles** clears the selected texture only: its triangles become white (or their original non-texture material); they never fall back to another texture. Undo brings them back.

## Managing textures (Texture section dropdown)
Each texture in the dropdown has a swap icon and a red x. **Swap** opens a file browser and replaces the picture (any browser image; converted to PNG on white, max 4096 px) while keeping the texture's triangles, projection and transform. The red **x** removes the texture and its triangle selection: those triangles go back to their original material, or white if the file textured them; the texture and its PNG leave the downloaded 3MF. **Add New** (last item) uploads another picture as a new texture (Box projection, no triangles yet; use Paint or Flood). Removing the last texture keeps the dropdown with Add New. All of this is undoable; Reset all restores removed, swapped and added textures. A picture with grey or colour areas gets a one-line warning (parts print black and white only).

## Choosing which triangles get the texture
Two selection tools (top bar; Orbit is the default). **Add / Remove** (side panel) says what a stroke does:
- **Paint**: drag a circle brush (size slider). It selects every triangle the circle touches at all (a corner inside the circle, an edge crossing it, or the centre inside the triangle), not just triangles whose centre is under it. By default only triangles facing the camera are hit; triangles hidden behind other parts are not filtered out.
- **Flood**: click a triangle; every connected triangle (edge-adjacent, vertices welded by position) whose normal is within the **Flood angle** slider (0-180 deg) of the *clicked* triangle's normal is added/removed.
- **Remove all** and **Reset selection** (back to the file's own assignment) are in the same panel.
Added triangles need UVs, so the texture switches to a Planar projection automatically (switching back to `Keep file UVs` reverts painted additions). Removed triangles (Remove mode, Clear) become a plain white `basematerials` entry that the download adds, or return to their original non-texture material; they never fall back to another texture. Selected triangles are drawn as an overlay on the loaded model, so the file is only changed by Download. A triangle painted onto one texture is taken from any other texture.

## Projection gimbal (optional)
The **Projection** dropdown re-maps every triangle in the texture's selection (all triangles using it, unless you changed the selection); the default `Keep file UVs` leaves the file's UVs alone. A Three.js gimbal (Move / Rotate / Scale, `Fit to model`) controls the projector; each texture keeps its own projector. The sliders above then act on top of the projected UVs.
| Type | Projector frame | UV |
|---|---|---|
| Planar (orthographic) | looks along local -Z; Scale X/Y = picture size | u = x/sx + 0.5, v = y/sy + 0.5 |
| Cylindrical | axis = local Z; Scale Z = height of one picture | u = angle/2pi + 0.5 (grows to the right seen from outside), v = z/sz + 0.5 |
| Spherical | poles = local Z | u as cylindrical, v = latitude/pi + 0.5 |
| Box | each triangle uses the face of the box its normal points at most; Scale = tile size | six upright, non-mirrored planar projections |
World positions come from the 3MF XML (build-item and component transforms, first instance of each object); a component with a `path` (other model file) is not resolved. Download appends one `tex2coord` per projected triangle corner and repoints those triangles. For cylindrical/spherical, a triangle across the seam is shifted by whole turns so it stays continuous (UVs outside 0..1, `wrap` tiling); sphere-pole triangles stay stretched. Box repeats the texture on every face. This is a placement aid with four analytic projections, not an unwrapping/packing engine.

## Maths (picture-centric, c = (0.5, 0.5), t = (du, dv), s = max(scale, 0.01))
`uv' = c + (1/s) * R(-theta) * (uv - c - t)`

Rotation, translation and scale are applied about the texture centre, not about the model. This is a convenience for tuning placement; it is not a geometry/UV engine. A localized logo on a face-sized atlas can be moved off its face by the sliders; the baked file will then show wrapped/clamped texture elsewhere.

## Limits
Preview follows the 3MF spec and Three.js; slicers may ignore or clamp textures. Re-run `scripts/preflight_3mf.py` on the downloaded file (UV out-of-bounds warnings are expected after scale > 1 or large offsets). Files above ~25 MB produce a warning. The bundle `assets/viewer_bundle.js` is a built artefact (`tools/build_viewer_bundle.sh`).
