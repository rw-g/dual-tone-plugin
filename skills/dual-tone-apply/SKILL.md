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

## If the scripts are not on disk (the web app may show only SKILL.md and references/)
Work down this list and stop at the first step that works. Where things live: plugin repository https://github.com/rw-g/dual-tone-plugin · Studio page https://rw-g.github.io/dual-tone-plugin/dual-tone-studio.html · repository zip https://codeload.github.com/rw-g/dual-tone-plugin/zip/refs/heads/main
1. **Look for them:** `find / -name apply_texture.py 2>/dev/null | head -1` (Windows PowerShell: `Get-ChildItem -Recurse -Filter apply_texture.py C:\ -ErrorAction SilentlyContinue | select -First 1`). Found: use that folder.
2. **Download the plugin from GitHub** (this brings the scripts AND the 3D / halftone viewer files, so the real editor can be built): `curl -fsSL https://codeload.github.com/rw-g/dual-tone-plugin/zip/refs/heads/main -o /mnt/data/dtp.zip && unzip -oq /mnt/data/dtp.zip -d /mnt/data` (no curl: Python `urllib.request.urlretrieve` + `zipfile.ZipFile(...).extractall`; PowerShell `Invoke-WebRequest` + `Expand-Archive`). The skills are then in `/mnt/data/dual-tone-plugin-main/skills/dual-tone-apply/` and `.../halftone-image/`: run the same commands as above from there and deliver the generated `*_viewer.html` / `halftone_viewer.html` and the 3MF in the chat, as usual.
3. **No internet:** recreate the small scripts instead of rewriting them. Read `references/source/<name>.py.md` with your file reader and write each ```` block UNCHANGED to `<work>/dual-tone-apply/scripts/<name>.py` (`apply_texture`, `apply_3mf_transform`, `make_qr` only for a QR). For images do the same with the halftone-image skill's `references/source/` (`prepare_image`, `detect_image`, `halftone` into `<work>/halftone-image/scripts/`, `presets.json` into `<work>/halftone-image/assets/`). `apply_texture.py` then writes just the 3MF (the viewer files are too large to recreate): deliver it and end the reply with the one Studio sentence from step 4, so the user can place or refine the texture in the 3D editor.
4. **Steps 2 and 3 both failed, or there is no editor / no way to run Python:** STOP. Do not write your own dithering, halftone, UV or 3MF code and do not hand-build a model file: that produces the wrong result and skips the editor. Deliver whatever 3MF you have and tell the user in one sentence to open **Dual-Tone Studio** at https://rw-g.github.io/dual-tone-plugin/dual-tone-studio.html (any browser, nothing to install: choose the model and the picture, or just a 3MF that already has the texture); the plugin source is at https://github.com/rw-g/dual-tone-plugin. For a photo or other continuous-tone image do not halftone it yourself: send the user to Studio with the model and the original image.
**Never try to rebuild the 3D editor or the halftone viewer** (they do not fit through `skills__read`; improvising one is what we are avoiding).
Python: try `python`, `py -3`, `python3`. A message like "Python was not found; run without arguments to install from the Microsoft Store" is the Windows Store stub, not Python: use the hosted code-interpreter/sandbox Python if you have one; otherwise tell the user to install Python 3 from python.org and run `pip install numpy pillow`, or use Studio (step 4).

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
