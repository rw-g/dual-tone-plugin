---
name: dual-tone-apply
description: Put a black-and-white texture (any image, QR code, text, logo or pattern) on an STL or 3MF model. Use whenever the user wants an image, pattern, logo, QR code or text applied to a 3D part. Fast path with no feature recognition - the texture is box-projected over the entire part and the interactive 3D editor opens so the user can place it exactly (paint or flood-select triangles, move the projector, clear and start fresh). Grayscale or colour images are prepared first by the halftone-image skill.
---

# Dual-tone texture on STL / 3MF

Do not analyse the model or interpret where the texture "should" go. Load the texture, box-project it over the **entire part**, open the 3D editor. The user refines placement there.

## Workflow
**Step 1 - Get the texture image.**
- The user's image (any photo, painting, logo, pattern or screenshot): **INTERCEPT** - **always run this one command first** (the `halftone-image` skill is the sibling folder `../halftone-image/`; if the path is not found run `find / -name prepare_image.py -path '*halftone-image*' 2>/dev/null | head -1`):
  `python ../halftone-image/scripts/prepare_image.py <image> --prompt "<the user's request, verbatim>" -o prepared`
  It prints one JSON line. **Exit 0** = `texture` is a ready black/white PNG (already black/white, or block colours / logos / QR thresholded automatically, no viewer): go to Step 2 with it. **Exit 10** = continuous-tone image (photo, painting): give the user the `viewer` HTML it built (their Apply button comes back here with the black/white PNG and the original request), say one line to pick a look and press Apply, and stop until they return the PNG. Use the PNG that comes back exactly as is.
  **Never write your own image classifier, halftone code or HTML viewer, and never copy logic out of the scripts: run them.** If a script errors, fix the invocation (path, working folder) or report the error. Skip the command only for an image you already know is pure black/white or a halftone the user already supplied.
- A QR code: `python scripts/make_qr.py "<exact text>" -o qr.png --ecc Q` (offline, bundled; never look for, pip install or download a QR library). Never alter the text.
- Text: render it black on white with Pillow (any default font) into a PNG. Nothing else is needed.

**Step 2 - Apply it.** One command:
`python scripts/apply_texture.py <model.stl|model.3mf> <texture.png> -o out.3mf`
It box-projects the texture over every triangle (each triangle uses the box face it points at; one tile = the part's largest dimension, change with `--tile-mm N` only if the user gave a size), keeps the geometry unchanged, writes `out.3mf` (STL cannot hold a texture, so the result is always a 3MF) and `out_viewer.html`, the 3D editor.

If the part is a 3MF that **already has textures**, they are all kept: the file is copied unchanged and the new picture waits in the editor's texture list with no triangles (`apply_texture.py` prints that). Tell the user once: pick the new texture in the list, place it with Paint or Flood, download the 3MF, and upload that file again whenever they want to add another.

**Step 3 - Deliver.** Give the user `out_viewer.html` and `out.3mf`. Say in one line that the texture covers the whole part and that the viewer lets them clear it, then paint or flood-select the triangles they want, move or rotate the projector, switch projection, and download the adjusted 3MF.

## Rules
1. **Never** identify faces, features, regions or "the front"; never choose planar/cylindrical/spherical yourself; never ask where the texture should go. Box projection over the whole part, then the editor. If the user names a place, still do the same and mention they can place it in the editor (Clear texture, then Paint or Flood).
2. Only black (#000000) and white (#FFFFFF). The geometry is never changed. `apply_texture.py` exits 3 on a grey/colour texture and prints the `prepare_image.py` command: run that, do not improvise.
3. **Keep the chat free of checks.** `apply_texture.py` checks its own output silently; never mention preflight, validation, verification, test, benchmark or Phase 0 results, error/warning counts, triangle counts, checklists or command logs. The reply says what was applied, any assumption (e.g. STL treated as millimetres), and links the two files. Only if `apply_texture.py` reports a problem you cannot fix, say plainly that the file may not open correctly.
4. Speed matters: no extra research, no extra scripts, no per-feature reasoning. Steps 1-3 should take a couple of tool calls.

## If the scripts are not on disk (some hosts show only SKILL.md and references/)
1. Look once for them: `find / -name apply_texture.py 2>/dev/null | head -1` (Windows PowerShell: `Get-ChildItem -Recurse -Filter apply_texture.py C:\ -ErrorAction SilentlyContinue | select -First 1`). Found: use that folder.
2. Not found: **recreate them, do not rewrite them.** Read `references/source/<name>.py.md` with your file reader and write each ```` block UNCHANGED to `<work>/dual-tone-apply/scripts/<name>.py` (`apply_texture`, `apply_3mf_transform`, `make_qr` only if a QR is asked for). For images do the same with the halftone-image skill's `references/source/` (`prepare_image`, `detect_image`, `halftone` into `<work>/halftone-image/scripts/`, and `presets.json` into `<work>/halftone-image/assets/`). Then run the same commands as above. **Never try to rebuild the 3D editor or the halftone viewer** (about 1 MB of viewer files: they do not fit through `skills__read`, and improvising one is what we are avoiding). `apply_texture.py` then writes just the 3MF: deliver it with ONE sentence: "Open it in Dual-Tone Studio (`dual-tone-studio.html`, offline, from the plugin download) to place and edit the texture." For a photo or other continuous-tone image in this mode, do not halftone it yourself either: tell the user to open Dual-Tone Studio and choose their model and the original image, which halftones interactively and opens the 3D editor.
3. No way to run scripts at all (no Python anywhere)? Do not improvise. Tell the user to open **Dual-Tone Studio** (`dual-tone-studio.html`, one offline page, included in the plugin download and in the repository `app/` folder): they choose the model and the picture (or just a 3MF that already has the texture), it thresholds or halftones as needed, and opens the full 3D editor. One short sentence.
4. Python: try `python`, `py -3`, `python3`. A message like "Python was not found; run without arguments to install from the Microsoft Store" is the Windows Store stub, not Python: use the hosted code-interpreter/sandbox Python if you have one; otherwise tell the user to install Python 3 from python.org and run `pip install numpy pillow`, then stop. Never write your own halftone code or viewer.

## Helper scripts (deterministic, no network)
| Script | Purpose |
|---|---|
| `scripts/apply_texture.py` | model + texture -> box-projected 3MF + 3D editor HTML (stdlib; Pillow only to convert a non-PNG texture) |
| `scripts/make_qr.py` | OFFLINE QR generator (stdlib only): text -> pure B/W PNG with quiet zone, sizes in mm |
| `scripts/make_viewer.py` | the 3D editor for any 3MF (used by `apply_texture.py`; `--projection box`) |
| `scripts/preflight_3mf.py` | structural 3MF checker (run by `apply_texture.py`; its output is not for the user) |
| `scripts/apply_3mf_transform.py` | bake or compose 3MF transforms to world space (rarely needed) |
| `scripts/preprocess_image.py` | optional image inspect / clean-up (background removal, black/white) |
`python scripts/<name>.py --help`. Tests: `python -m pytest tests`.

## References
`3mf-conventions` · `texture-coordinate-conventions` · `transform-conventions` · `image-preprocessing` · `validation-checklist` · `viewer` (all in `references/`, `.md`; read only if something fails)
