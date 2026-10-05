# Delivery and reply

`apply_texture.py` already checks the 3MF it writes (structure, ids, texture relationship, UVs in range) and the viewer shows a warning banner only if a file has problems. These checks are for you, not for the chat.

## If `apply_texture.py` reports a problem
Look at `references/3mf-conventions.md` / `texture-coordinate-conventions.md`, repair deterministically (unique resource ids, texture relationship, UV range), re-run. Do not narrate the failure or the repair. Only if the file still cannot be made valid, tell the user plainly that it may not open correctly and suggest trying a different file.

## Reply template (no check results)
```
<One or two sentences: the texture was applied over the whole part with a box projection; where to refine it.>
Assumptions: <short list, only if any: e.g. STL treated as millimetres>
Files: <3MF link>, <3D editor link>
```
Do not include: preflight/validation/verification status, error or warning counts, triangle counts or bounding boxes, test or benchmark references, or a list of commands run. Never claim a check you did not run, and do not list the ones you did.
