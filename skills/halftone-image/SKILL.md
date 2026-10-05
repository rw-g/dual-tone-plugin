---
name: halftone-image
description: Prepare any grayscale or colour image for a dual-tone 3D model. Use FIRST, before dual-tone-apply, whenever the user supplies an image that is not already pure black/white; run `scripts/prepare_image.py <image> --prompt "<request>"` (never write your own halftone code or viewer). Block-colour images (logos, silhouettes, line art, near two-colour patterns, even with soft anti-aliased edges) are simply thresholded to black/white with no viewer; continuous-tone images (photos, shading, gradients) open an interactive halftone viewer (presets, dot/line/hex/radial screens, real stipple, error diffusion, Bayer, blue noise, tone and crop controls, 1-bit PNG download) and its Apply button continues into the 3D texture skill with the original request.
---

# Halftone an image for 3D texturing

3D prints and dual-tone textures can only hold black and white. This Skill thresholds block-colour images automatically and turns continuous-tone images into black/white halftones the user chooses by eye, then hands the result to `dual-tone-apply` together with the **original request**.

## Workflow
**Fast path - one command:** `python scripts/prepare_image.py <image> --prompt "<the user's request, verbatim>" -o prepared` runs Steps 1-2 below and prints one JSON line. Exit 0: use `texture` (a ready black/white PNG) and continue `dual-tone-apply` Step 2. Exit 10: give the user `viewer` (Step 2 wording) and wait for the PNG. **Never write your own classifier, halftone code or viewer, and never copy logic out of these scripts: run them.** If one errors, fix the invocation (path, working folder) or report the error.

**Step 1 - Detect.** `python scripts/detect_image.py <image> --json`. The `action` (also the exit code) decides:
- `as_is` (0): already pure black/white: skip this Skill.
- `threshold` (12): block colours, silhouettes, logos, line art, text or a near two-colour pattern (anti-aliased edge pixels do not matter): run `python scripts/halftone.py <image> bw.png --preset threshold` (keeps the native resolution up to 2048 px), use `bw.png`, and continue `dual-tone-apply` straight away. No viewer, no question, and do not call it halftoning.
- `qr` (11): QR code: never halftone (hard threshold, check it still decodes).
- `halftone` (10): continuous tone (photo, shading, gradients): continue with Step 2.

**Step 2 - Only for `halftone`: open the halftone viewer immediately** (do not threshold or ask first):
`python scripts/make_halftone_viewer.py <image> -o halftone_viewer.html --prompt "<the user's request, verbatim>"`
Deliver `halftone_viewer.html` to the user with one line: pick a look, then press **Apply to 3D model** (or Download PNG). Do not continue until the user returns the PNG or tells you to go ahead.

**Step 3 - Hand off.** When the black/white PNG comes back (Apply message, attachment, or "use preset X"): use it exactly as is (no re-threshold, smoothing or resampling), keep the original request, and continue `dual-tone-apply` Step 2 (`apply_texture.py`: box projection over the entire part, then the 3D editor). See `references/handoff.md`.

**Step 4 - No browser / no interaction.** If the user cannot open HTML or asks for a one-shot result, run `python scripts/halftone.py <image> out.png --preset <recommended> --width 800` (identical algorithms), show the result, and continue.

## If the scripts are not on disk
Some hosts show only SKILL.md and references/. Then read `references/source/<name>.py.md` (`prepare_image`, `detect_image`, `halftone`, `presets.json`), write each block UNCHANGED to `<work>/halftone-image/scripts/<name>.py` (`presets.json` to `<work>/halftone-image/assets/`), and run `prepare_image.py` as above (never rebuild the halftone viewer: it does not fit through `skills__read`; for a photo tell the user, once, to open Dual-Tone Studio (`dual-tone-studio.html`, offline, in the plugin download) and choose their model and the original image: it halftones interactively and opens the 3D editor). Python needs numpy and Pillow. Details and Windows notes: `dual-tone-apply` SKILL.md, section "If the scripts are not on disk".

## Rules
1. Output is pure black (#000000) and white (#FFFFFF), 1-bit. Colour is discarded by design.
2. Keep the user's request verbatim in `--prompt`; it travels with Apply.
3. Never halftone QR codes, barcodes, small text or crisp line logos you can threshold; for those use the `threshold` preset and check legibility.
4. Parts are printed in colour by inkjet (HP MJF, about 300 DPI), so there is no minimum feature size: choose the look and the output width (600-1200 px suits most textures) freely, and use the exact PNG that comes back.
5. The Apply button messages the chat only when the host exposes a bridge (ChatGPT widget / MCP Apps); otherwise it downloads the PNG and shows a ready-to-paste prompt. Say so if asked.
6. Keep the chat free of test, benchmark and validation output: tell the user what you did (image type, preset, link to the viewer), nothing about internal checks.
7. Presets and algorithm guidance: `references/presets.md`, `references/algorithms.md`.

## Helper scripts (deterministic, no network)
| Script | Purpose |
|---|---|
| `scripts/prepare_image.py` | ONE command: detect, then threshold to a PNG or build the halftone viewer (use this) |
| `scripts/detect_image.py` | binary / grayscale / colour, flat vs continuous, QR check, recommended preset; exit codes 0 / 10 / 11 |
| `scripts/make_halftone_viewer.py` | one offline HTML viewer for an image (needs `assets/`) |
| `scripts/halftone.py` | headless halftone to a 1-bit PNG, same engine and presets; `--list-presets` |
`python scripts/<name>.py --help`. Tests: `python -m pytest tests`.

## References
`algorithms` · `presets` · `handoff` (all in `references/`, `.md`)
