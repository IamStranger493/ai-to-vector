# Decisions & Architectural Deviations

Every deviation from `antigravity_build_spec.md`, along with the rationale and memory budget notes.

## Memory Budget
- Max working side: 2000px
- Peak memory budget: < 2 GB RAM (compatible with Render standard CPU instance)
- A 2000x1300 float32 Lab image is ~31 MB per copy.
- We maintain <= 3 full image buffers in memory simultaneously, explicitly calling `del` and `gc.collect()` between stages.

## Decisions Log
- **2026-10-10 M0**: Project directory created at `e:\Z\Coding\ai-to-vector`.
- Virtual environment setup using Python 3.12 managed via `uv`.
- QA rendering uses `cairosvg` when system Cairo is present (e.g. Linux Docker container per Dockerfile), and seamlessly falls back to `resvg-py` on Windows/systems without Cairo C libraries installed, ensuring QA runs everywhere without manual C DLL setup.
- Frontend scaffolded with Vite + TypeScript (`vanilla-ts`) in `web/`.

- **2026-10-10 Bug Fix: Upload Image Visibility, Scrollable Panels, and Error Reporting**:
  - **Root Cause 1 (Image pushed off-screen)**: `.viewport` used `display: flex; align-items: center; justify-content: center;` while `.canvas-transform` lacked `top: 0; left: 0;`. Flex centering pre-offset the canvas, and JS `translate(panX, panY)` doubled the vertical offset (pushing the image to $y \approx 951\text{px}$ off-screen). With `overflow: hidden;` on the viewport, the reference image became invisible.
    - *Fix*: Removed flex centering from `.viewport`, anchored `.canvas-transform` and `.ref-image` to `top: 0; left: 0;`, and set `.ref-image` to `width: 100%; height: 100%; object-fit: contain;`.
  - **Root Cause 2 (Panels and Mobile Page Not Scrolling)**: Default flex/grid `min-height: auto` on ancestors prevented `.sidebar-scrollable` from shrinking, and `#params-container` lacked explicit scrolling rules. On mobile, `body` had `overflow: hidden; height: 100vh;`.
    - *Fix*: Added `min-height: 0;` to `.app-workspace`, `.sidebar`, `.sidebar-scrollable`, and `.viewer-container`. Styled `#params-container` with `overflow-y: auto; max-height: 100%; min-height: 0;`. In `@media (max-width: 960px)`, set `body` and `.app-layout` to `overflow-y: auto; height: auto; min-height: 100vh;`, with `.viewer-container` at `height: 60vh; min-height: 400px;`.
  - **Root Cause 3 (Fit-to-Screen Scale Timing & Object URL Lifecycle)**: `refImageEl.src` was set prior to attaching `onload`, with no guards against zero or NaN dimensions, and blob URLs risked premature revocation.
    - *Fix*: Attached `onload` and `onerror` prior to setting `src`. Added synchronous completion check (`complete && naturalWidth > 0`). Guarded `fitToViewport()` against zero/NaN/infinite dimensions. Object URLs are tracked and only revoked inside `onload` after successful decode.
  - **Root Cause 4 (Event Handler Isolation)**: Wheel and touch listeners were generalized or unconstrained.
    - *Fix*: Confined `wheel` and touch listeners exclusively to `.viewport` with `{ passive: false }` and `touch-action: none;`. Replaced window drag listeners with Pointer Capture (`setPointerCapture`) on `.viewport`.
  - **Root Cause 5 (Silent Image Decode Failures & CSP)**: Corrupt uploads failed without UI feedback.
    - *Fix*: Added `#upload-error-banner` in UI with visible decode error messages. Added `Content-Security-Policy` with `img-src 'self' blob: data:` in `web/vercel.json`. Added SVG favicon link in `index.html` to eliminate 404 console errors. Wrapped API key input in `<form>` to satisfy browser DOM guidelines.
  - **Verification**: Created automated Playwright smoke test suite (`web/tests/smoke.spec.ts`) asserting non-zero image/canvas bounding boxes, params panel scrolling (`scrollHeight > clientHeight`), error banner activation on corrupt inputs, and 0 console errors. Verified on both dev and production preview builds (`npm run test:e2e`).

