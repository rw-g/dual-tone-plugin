# Image preprocessing

Use `scripts/preprocess_image.py`; fall back to your own analysis only for cases it refuses.

## 1. Inspect first
Record: dimensions, aspect ratio, colour mode, alpha channel present/used, unique colour count, grayscale or colour, border colour and how uniform it is, artwork (foreground) bounds and padding, likely role (logo/qr/pattern/ambiguous), seam score for patterns. Command: `preprocess_image.py inspect file`.

## 2. Role classification (heuristic - the user's words win)
- QR finder patterns / OpenCV decode -> **qr**.
- Bounded artwork on a uniform or transparent background -> **logo/sticker**.
- Content fills the canvas, no uniform border, textured or repeating -> **pattern**.
- Otherwise ambiguous: read the request ("apply this pattern", "cover the whole part" -> pattern; "put this logo/sticker/QR on" -> localized). Ask one question only if the choice changes the result materially.

## 3. Background removal (logo / sticker / QR)
- Already transparent -> keep it exactly.
- Otherwise the background is the dominant border colour **only if the border is >= 85 % that colour**; remove pixels within tolerance (default 24/255) that are **connected to the image border**. White inside letters, rings, holes and QR light modules stays.
- Non-uniform border (photo, gradient, busy scene): do not remove anything automatically; tell the user or use your own segmentation conservatively. Never erase intentional background elements (a badge's filled disc is artwork).
- Output: removed background = RGB white with alpha 0; artwork opaque.

## 4. Black/white conversion
Default for logo/sticker/pattern when the user did not ask to keep colour: luminance -> threshold (Otsu) -> pure black / pure white, no grey levels. Already pure black/white -> unchanged. Single-tone artwork (all ink same colour) -> that tone is ink. Light-on-dark art keeps polarity (use `--invert` to swap). Colour preservation requested -> `--keep-color`.
QR codes: if the input is already pure black/white, nothing is thresholded (module topology preserved). If it is grey/noisy, threshold and **verify by decoding before and after** (`--verify-qr`); if the decode differs, keep the original data and warn.

## 5. Bounds, padding and size tracking
The helper reports `canvas_px`, `artwork_bbox_px`, `padding_px`, `output_px`, `artwork_in_output_px`, `mm_per_px`, `artwork_size_mm`. A request "20 mm wide" binds to the artwork width: logo/sticker output is trimmed to the artwork by default; pass `--no-trim` to keep padding and the helper still computes `mm_per_px` from the artwork width.

## 6. QR specifics
Dark-module square is measured from the first finder pattern (7 modules) -> module size; quiet zone = 4 modules (`--qr-quiet-modules`) re-created if the source cropped it; output keeps light modules and quiet zone **opaque white** (so the code scans on any surface). `--qr-transparent-light` exists for light surfaces only. Report the dark-module square and the whole symbol in mm.

## 7. Patterns
No cut-out, no trimming; binarise only if colour is not requested. Report `seamless_likely` / `seam_ratio` (<= 2 behaves like an interior edge). If not seamless: use mirrored tiling or a single stretch, and say so. Decide the physical tile size (user's, else a reasonable default such as 10-20 mm for fine patterns) and state it.

## 8. Limits
No AI segmentation, no inpainting, no vectorisation. Anti-aliased edges are binarised at the threshold (staircase edges at low resolution: upscale the source with nearest/bicubic before binarising if the image is under ~300 px).
