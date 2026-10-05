# Texture coordinate conventions

## The 3MF rule (Materials Extension, verified 2026-10-01)
"The lower left corner of the texture is the u, v coordinate (0,0), and the upper right coordinate is (1,1)." u increases to the right, v increases **up**.

| Image pixel (col, row), row 0 = top | (u, v) |
|---|---|
| top-left | (0, 1) |
| top-right | (1, 1) |
| bottom-left | (0, 0) |
| bottom-right | (1, 0) |
Pixel centre -> `u = (col + 0.5) / W`, `v = 1 - (row + 0.5) / H`.

## The mistake to avoid (Phase 0)
Writing `v = row / H` (image convention, origin top-left) puts the picture **upside down**. Phase 0 files from several runs carried vertically flipped logos. After building UVs, test one landmark: the artwork's top-left feature must sit at the viewer's top-left of the face (v larger = higher on the face).

## Computing UVs from a face frame
Frame: origin O, right u, up v. For a point P on the face:
```
a = dot(P - O, u)        # mm to the viewer's right of O
b = dot(P - O, v)        # mm above O
```
- Face-sized atlas (whole face, width EU, height EV, graphic already positioned in the image): `U = a/EU + 0.5`, `V = b/EV + 0.5`.
- Decal rectangle (centre cx,cy; size w,h; rotation theta CCW): rotate by -theta: `a' = (a-cx)cos(theta) + (b-cy)sin(theta)`, `b' = -(a-cx)sin(theta) + (b-cy)cos(theta)`; `U = a'/w + 0.5`, `V = b'/h + 0.5`. Triangles whose corners fall outside 0..1 are not covered and must be plain-coloured (or the decal rectangle must be a separate piece of the face).
- Physical scale: 1 mm on the surface = `1/EU` (or `1/w`) in U.

## Tiling / sampling attributes
- Single graphics: `tilestyleu="clamp" tilestylev="clamp" filter="nearest"`; keep every UV inside 0..1 (small epsilon inside, so edge pixels do not bleed).
- Repeating patterns: `wrap` (or `mirror` if the tile is not seamless), UVs may exceed 1: `U = a / tile_width_mm`.
- UVs outside 0..1 are legal with tilestyle but slicers often clamp; preflight warns.

## Transparency
The spec treats a base-layer texture as fully opaque, and many slicers ignore alpha. Turn "transparent background" into reality by compositing the cleaned artwork onto the base colour of the surface it covers (usually white): the face-sized atlas is initialised with that colour and the artwork pasted in at its exact position. Keep a transparent RGBA copy only as an intermediate or if the user wants it.

## Resolution
10 px/mm is a good default for face-sized atlases (0.1 mm per pixel); keep QR modules >= 6 px wide and thin logo strokes >= 3 px. Keep textures under ~4096 px per side; larger faces: lower px/mm or split the face.

## Sanity checks after writing
1. `preflight_3mf.py` passes (UVs numeric, in range, indices valid).
2. Render the face orthographically (sample the texture at each pixel's UV or rasterise triangles) and compare with the intended placement.
3. Mirror test: the artwork reads correctly when the face is viewed from outside.
