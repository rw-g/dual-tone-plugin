# Source of `assets/presets.json` (halftone-image)

Verbatim copy. If `assets/presets.json` is not on disk, write the block below UNCHANGED to `halftone-image/assets/presets.json` (keep the folder layout) and run it from there.

````json
[
  {"id": "newsprint", "name": "Newsprint", "group": "Print screens", "method": "am", "params": {"cell": 6, "angle": 45, "shape": "round", "centre": true}, "tone": {"contrast": 10}},
  {"id": "comic", "name": "Comic dots", "group": "Print screens", "method": "am", "params": {"cell": 10, "angle": 45, "shape": "round", "centre": true}, "tone": {"contrast": 25, "gamma": 1.1}},
  {"id": "fine-photo", "name": "Fine screen", "group": "Print screens", "method": "am", "params": {"cell": 4, "angle": 45, "shape": "round", "centre": true}, "tone": {}},
  {"id": "hex-dots", "name": "Hex dots", "group": "Print screens", "method": "am", "params": {"cell": 7, "angle": 0, "shape": "round", "centre": true, "grid": "hex"}, "tone": {"contrast": 10}},
  {"id": "diamond", "name": "Diamond screen", "group": "Print screens", "method": "am", "params": {"cell": 7, "angle": 45, "shape": "diamond", "centre": true}, "tone": {}},
  {"id": "square-dots", "name": "Square dots", "group": "Print screens", "method": "am", "params": {"cell": 7, "angle": 0, "shape": "square", "centre": true}, "tone": {}},
  {"id": "engraving", "name": "Engraving lines", "group": "Lines & rings", "method": "am", "params": {"cell": 6, "angle": 45, "shape": "line", "centre": true}, "tone": {"contrast": 15}},
  {"id": "horizontal", "name": "Horizontal lines", "group": "Lines & rings", "method": "am", "params": {"cell": 6, "angle": 0, "shape": "line", "centre": true}, "tone": {}},
  {"id": "wavy", "name": "Wavy lines", "group": "Lines & rings", "method": "am", "params": {"cell": 8, "angle": 0, "shape": "line", "centre": true, "warp": 0.6, "warpScale": 3}, "tone": {"contrast": 10}},
  {"id": "crosshatch", "name": "Cross-hatch", "group": "Lines & rings", "method": "am", "params": {"cell": 8, "angle": 45, "shape": "cross", "centre": true}, "tone": {}},
  {"id": "rings", "name": "Concentric rings", "group": "Lines & rings", "method": "am", "params": {"cell": 10, "angle": 0, "shape": "ring", "centre": true}, "tone": {}},
  {"id": "target", "name": "Target", "group": "Lines & rings", "method": "am", "params": {"cell": 8, "angle": 0, "shape": "round", "centre": true, "grid": "ring"}, "tone": {"contrast": 10}},
  {"id": "sunburst", "name": "Sunburst", "group": "Lines & rings", "method": "am", "params": {"cell": 8, "angle": 0, "shape": "round", "centre": true, "grid": "radial"}, "tone": {"contrast": 10}},
  {"id": "stipple", "name": "Stipple fine", "group": "Stipple", "method": "stipple", "params": {"spacingMin": 3, "spacingMax": 10, "dot": 1, "sizeByTone": true, "relax": 2, "seed": 1}, "tone": {"contrast": 10}},
  {"id": "stipple-bold", "name": "Stipple bold", "group": "Stipple", "method": "stipple", "params": {"spacingMin": 5, "spacingMax": 14, "dot": 1.2, "sizeByTone": false, "relax": 2, "seed": 1}, "tone": {"contrast": 20}},
  {"id": "blue-noise", "name": "Blue-noise grain", "group": "Stipple", "method": "blue", "params": {}, "tone": {}},
  {"id": "floyd", "name": "Floyd–Steinberg", "group": "Error diffusion", "method": "diffusion", "params": {"kernel": "floyd", "serpentine": true, "amount": 1, "threshold": 0.5}, "tone": {}},
  {"id": "atkinson", "name": "Atkinson (classic Mac)", "group": "Error diffusion", "method": "diffusion", "params": {"kernel": "atkinson", "serpentine": false, "amount": 1, "threshold": 0.5}, "tone": {"contrast": 10}},
  {"id": "stucki", "name": "Stucki (smooth)", "group": "Error diffusion", "method": "diffusion", "params": {"kernel": "stucki", "serpentine": true, "amount": 1, "threshold": 0.5}, "tone": {}},
  {"id": "jarvis", "name": "Jarvis–Judice–Ninke", "group": "Error diffusion", "method": "diffusion", "params": {"kernel": "jarvis", "serpentine": true, "amount": 1, "threshold": 0.5}, "tone": {}},
  {"id": "sierra-lite", "name": "Sierra Lite (fast)", "group": "Error diffusion", "method": "diffusion", "params": {"kernel": "sierraLite", "serpentine": true, "amount": 1, "threshold": 0.5}, "tone": {}},
  {"id": "riemersma", "name": "Riemersma (Hilbert)", "group": "Error diffusion", "method": "riemersma", "params": {"history": 16, "amount": 1, "threshold": 0.5}, "tone": {}},
  {"id": "bayer4", "name": "Bayer 4×4 (retro)", "group": "Ordered & noise", "method": "bayer", "params": {"size": 4}, "tone": {}},
  {"id": "bayer8", "name": "Bayer 8×8", "group": "Ordered & noise", "method": "bayer", "params": {"size": 8}, "tone": {}},
  {"id": "ign", "name": "Gradient noise", "group": "Ordered & noise", "method": "ign", "params": {}, "tone": {}},
  {"id": "threshold", "name": "Hard threshold", "group": "Logo / line art", "method": "threshold", "params": {"threshold": 0.5}, "tone": {"contrast": 20}}
]
````
