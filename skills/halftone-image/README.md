# halftone-image (Skill)

Interception step in front of `dual-tone-apply`: any grayscale or colour image is detected. Block-colour images (logos, silhouettes, near two-colour patterns) are thresholded automatically; continuous-tone images open an offline halftone viewer. Either way the result is a pure black/white PNG that is applied to the 3D model with the original request.

```
halftone-image/
├── SKILL.md
├── references/ algorithms.md · presets.md · handoff.md
├── scripts/    detect_image.py · make_halftone_viewer.py · halftone.py     (numpy + Pillow; stdlib otherwise)
├── assets/     halftone_template.html · halftone_engine.js · presets.json  (no network, no libraries)
└── tests/
```
```bash
python scripts/detect_image.py photo.png --json
python scripts/make_halftone_viewer.py photo.png -o halftone_viewer.html --prompt "Put this on the front of the cube, 40 mm wide"
python scripts/halftone.py photo.png out.png --preset stucki --width 800
python -m pytest tests
```
The JavaScript engine (viewer) and `halftone.py` produce identical pixels for every method (stipple, hex / radial / ring screens and warp included); tests enforce this (< 1% tolerance for float rounding).
