# Hand-off to dual-tone-apply

## What the Apply button does (assets/halftone_template.html)
1. Builds the 1-bit PNG `<name>_halftone.png` and the prompt:
   `Apply the halftoned image <file> (attached; WxH px, pure black/white, 1-bit) to the 3D model. Use it exactly as is ... Original request: "<verbatim request>" ... Use the dual-tone-apply skill: run apply_texture.py with this PNG (box projection over the entire part), which writes the 3MF and opens the 3D editor. Halftone settings: <preset/method>.`
2. Sends it, trying in order: (a) `window.openai.uploadFile` + `window.openai.sendFollowUpMessage` (ChatGPT widget bridge), (b) MCP Apps `ui/message` over `window.parent.postMessage`, (c) fallback: downloads the PNG and opens a dialog with the prompt to copy and paste with the attached PNG.
   OpenAI documents (a) and (b) for components hosted by an MCP server inside ChatGPT (developers.openai.com/apps-sdk/reference, /plugins/build/chatgpt-ui, accessed 2026-10-02). A standalone HTML file produced by a Skill is not documented to receive that bridge, so (c) is the expected path there. UNVERIFIED in a live ChatGPT session.

## What the Skill does on return
- The PNG is already halftoned: do not run `detect_image.py` on it again (it will report binary) and never re-threshold or resize it.
- Reuse the original request exactly (sizes, face, position, colours, "twice as large", etc.). Continue `dual-tone-apply` at Step 2: `python scripts/apply_texture.py <model> <png> -o out.3mf` (box projection over the entire part, no feature recognition, no placement questions), then deliver `out_viewer.html` and `out.3mf`. Do not report check results in the reply.
- If only a preset name comes back ("use stucki"), run `scripts/halftone.py <image> out.png --preset stucki --width 800`.
