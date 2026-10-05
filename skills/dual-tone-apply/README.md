# dual-tone-apply (source folder `skills/color-3d-model`)

Fast path for putting a black-and-white texture (image, QR code, text, logo, pattern) on an STL or 3MF part: **no feature recognition**. The texture is box-projected over the whole part and the interactive 3D editor opens; the user places it there (clear the texture, paint or flood-select triangles, move the projector, switch projection, download the adjusted 3MF). Grayscale or colour images are prepared first by the `halftone-image` skill.

```
dual-tone-apply/
├── SKILL.md                       the whole workflow (3 steps) and rules
├── references/                    3mf-conventions · texture-coordinate-conventions · transform-conventions · image-preprocessing · validation-checklist (reply template) · viewer
├── scripts/
│   ├── apply_texture.py           model + texture -> box-projected 3MF + 3D editor (the one command ChatGPT runs)
│   ├── make_viewer.py             the 3D editor (self-contained Three.js HTML, uses assets/)
│   ├── make_qr.py                 offline QR code generator (stdlib only)
│   ├── preflight_3mf.py           structural 3MF checker (run by apply_texture.py)
│   ├── apply_3mf_transform.py     3MF transform math + bake to world space
│   └── preprocess_image.py        optional image inspect / clean-up
├── assets/                        viewer template, Three.js bundle, licences
└── tests/
```
```bash
python scripts/apply_texture.py part.stl pattern.png -o part_textured.3mf     # writes the 3MF and part_textured_viewer.html
python scripts/apply_texture.py part.3mf logo.png --tile-mm 30                 # tile size in mm (default: largest dimension)
python scripts/make_qr.py "https://example.com" -o qr.png
python -m pytest tests
```
Requirements: Python 3.9+. Pillow and NumPy only for optional helpers (non-PNG textures, `preprocess_image.py`).
