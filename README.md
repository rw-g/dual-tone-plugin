# Dual-Tone Apply (ChatGPT plugin)

Put a black-and-white image, logo, QR code or text on an STL / 3MF part, and edit where it goes in an offline 3D editor.

This repository contains only the plugin (built from the development repository): `plugin.json`, `skills/` and `dual-tone-studio.html`.

## Use
- **As a plugin:** zip the contents of this repository (or download it as a ZIP) and upload it as a ChatGPT plugin. `plugin.json` is at the root.
- **Without any install:** open `dual-tone-studio.html` in a browser (also served at https://rw-g.github.io/dual-tone-plugin/dual-tone-studio.html). Pick a model and a picture; block-colour images are made black/white automatically, photos open the halftone editor first, then the 3D editor.

## What is inside
| Path | What |
|---|---|
| `skills/halftone-image/` | prepares any image as black/white: automatic threshold or an interactive halftone editor |
| `skills/dual-tone-apply/` | box-projects the picture over the part, writes the 3MF and opens the 3D editor (paint / flood-select triangles, projector gimbal, swap / add / remove textures) |
| `dual-tone-studio.html` | one offline page with all of the above, no Python needed |

Colours are black (#000000) and white (#FFFFFF) only. Version: see `plugin.json`.
