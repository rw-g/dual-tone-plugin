# 3MF transform conventions

Implemented and tested in `scripts/apply_3mf_transform.py` (Phase 0 regression M06: +30 degrees was applied as -30 degrees in 6 of 6 runs).

## Format
A transform is 12 numbers: `m00 m01 m02 m10 m11 m12 m20 m21 m22 m30 m31 m32`.
It is the 4x3 part of a 4x4 matrix used with **row vectors**:
```
[x' y' z' 1] = [x y z 1] * | m00 m01 m02 0 |
                            | m10 m11 m12 0 |
                            | m20 m21 m22 0 |
                            | m30 m31 m32 1 |
x' = m00*x + m10*y + m20*z + m30
y' = m01*x + m11*y + m21*z + m31
z' = m02*x + m12*y + m22*z + m32
```
So `m30 m31 m32` is the translation, and reading the numbers as a column-vector matrix (x' = m00 x + m01 y + ...) **reverses every rotation**.

## Canonical matrices (angle theta, counter-clockwise when looking down the positive axis toward the origin)
| Operation | 12 numbers |
|---|---|
| identity | `1 0 0 0 1 0 0 0 1 0 0 0` |
| translate (tx,ty,tz) | `1 0 0 0 1 0 0 0 1 tx ty tz` |
| scale (sx,sy,sz) | `sx 0 0 0 sy 0 0 0 sz 0 0 0` |
| rotate about Z by +theta | `cos sin 0 -sin cos 0 0 0 1 0 0 0` |
| rotate about X by +theta | `1 0 0 0 cos sin 0 -sin cos 0 0 0` |
| rotate about Y by +theta | `cos 0 -sin 0 1 0 sin 0 cos 0 0 0` |
Worked check: +30 deg about Z is `0.866025404 0.5 0 -0.5 0.866025404 0 0 0 1 0 0 0`; the point (1,0,0) maps to (0.866, 0.5, 0). If you get (0.866, -0.5, 0) the matrix was read column-wise.

## Composition and hierarchy
- "Apply A first, then B" = row-vector product `A * B` (`compose(A, B)` in the helper).
- Position in the printed world = vertex x component transform(s) (innermost first) x build item transform.
- `make --scale 2 1 1 --rotate-z 90 --translate 10 0 0` applies left to right and prints `0 2 0 -1 0 0 0 0 1 10 0 0`.

## Units, mirroring, baking
- Vertices and translations are in the model's `unit`; the helper reports world coordinates in millimetres.
- A negative determinant mirrors the object: flip each triangle's winding (swap two indices) when baking so normals stay outward (the helper does).
- Baking for STL export: `python scripts/apply_3mf_transform.py bake plate.3mf plate_world.stl`. Baking to 3MF flattens each build item to one mesh object with fresh unique ids and identity transforms; textures/materials are kept.
- External component files (production extension `p:path`) are not supported by `bake` (clear error).

## Verification
After baking, compare bounding boxes and the position of an asymmetric landmark vertex with `describe`/`world_meshes`; for STL exports reload the STL and check the same landmark. Never infer the rotation direction from the bounding box (a +30 and a -30 rotation of a square have identical boxes).
