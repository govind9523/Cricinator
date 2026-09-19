# Original stadium experience

`web/stadium.js` constructs Scout and the floodlit stadium from geometric meshes. No downloaded character art, textures, fonts, paid assets, external CDN, or sound is required. Three.js **0.180.0** is pinned in `web/vendor/three.module.min.js` and `three.core.min.js`; its MIT license is included in `THREE-LICENSE.txt`. These files were extracted from the npm registry package `three@0.180.0` (tarball SHA1 `b930cabfb524f6d36bf63e874b4d866888b50487`). There is no production Node build step.

HTML owns every game control. Keyboard answers 1–5, visible focus, native modal and mode select, live request status, mobile layout, CSS fallback when WebGL fails, and no autoplay audio are provided. Render scheduling pauses while hidden, caps DPR at 1.6 and animation around 30fps; reduced-motion users get static renders updated on game state/resize. WebGL context loss returns to the CSS scene. The host responds to thinking, guess, completion and miss states.

## Verification

- `node --check web/game.js`
- `node --check web/stadium.js`
- `node web/frontend-check.cjs`: API revision, mode, idempotency header, stale-state refresh, and HTML bindings.
- Live in-app browser at isolated localhost port 7874: desktop WebGL render; start, answer, undo, reload persistence, and restart; phone 390×844 question layout and landing composition.

Catalog count represents international source records, not distinct people. Enriched Classic profiles and World beta records are labeled separately. Feedback is described as submitted for review. No measured human-accuracy claim is made.

Browser verification did not exercise a complete guessed-player round, reduced-motion OS setting, or physical GPU context loss. Coverage/catalog routes were still being added to the backend during this pass; verify them against the final backend before release.
