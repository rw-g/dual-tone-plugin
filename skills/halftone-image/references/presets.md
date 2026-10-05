# Presets (assets/presets.json)

One list drives both the viewer gallery and `halftone.py --preset`.

| Group | Preset id | Look | Start here when |
|---|---|---|---|
| Print screens | `newsprint` | 45 deg round dots, cell 6 | default for photos |
| | `comic` | big dots, cell 10, punchy | bold comic / pop-art look; best for printing |
| | `fine-photo` | cell 4 | high resolution textures |
| | `diamond`, `square-dots` | diamond / square cells | stylised |
| Lines & rings | `engraving` | 45 deg lines | engraving / banknote look |
| | `horizontal`, `crosshatch`, `rings` | lines, crossed strokes, concentric rings | stylised |
| Error diffusion | `floyd`, `atkinson`, `stucki`, `jarvis`, `sierra-lite`, `riemersma` | 1-pixel stochastic dots | detail-heavy photos at >= 800 px |
| Ordered & noise | `stipple` (blue noise), `bayer4`, `bayer8`, `ign` | stippled / retro | grain, stipple, retro games |
| Logo / line art | `threshold` | hard black/white | flat colour logos, line art, text |

Defaults chosen by `detect_image.py`: `continuous` -> `newsprint` (viewer opens); block colours or near two-colour images -> `threshold` applied automatically with `halftone.py --preset threshold`, no viewer.
Tone adjustments stored with a preset (contrast, gamma...) are applied when it is selected.
