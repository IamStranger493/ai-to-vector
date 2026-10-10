# Review fixes (verified in headless Chromium + real image)

Test image: 1672x941 AI illustration (two people, desert). Working size 2000 (no upscale).

## Backend
1. **Crash fixed (curves.py, validate_and_repair_regions):** Bezier mode threw `shapely GEOSException: TopologyException` on a real image
   when a fitted ring self-intersected, failing the whole job. Invalid rings are now detected and their shared arcs fall back to polygon
   mode, with up to 4 re-validation passes.

## Frontend
2. Value labels (k, min area, ...) were hard-coded text and did not follow presets. Labels now read the real slider value.
3. Preset dropdown said "Accurate (polygon, k=64)" while real params were Bezier k=48 with lines on. Startup now loads "Accurate".
4. Desktop: params list scrolled inside its own small box. The whole left column now scrolls as one; grid row can no longer grow
   (`grid-template-rows: minmax(0, 1fr)`).
5. Mobile: header overflowed (Vectorize button off-screen, page 459px wide on a 390px phone); `100vw` widths removed, header wraps and is sticky.
6. Mobile: the viewer sits below ~1270px of controls, so an uploaded image looked missing. The page now scrolls to the viewer after the
   image loads and after vectorizing.

## Measured (independent render with cairosvg on #ff00ff, 0.5x / 1x / 2x, fills only)
| Mode | Magenta px | MAE | PSNR |
|---|---|---|---|
| polygon, k=48 | 0 / 0 / 0 | 6.24 | 29.0 dB |
| bezier, k=48 | 0 / 10 / 340 | 6.28 | 28.8 dB |

Bezier mode still leaves a few hairline gaps (5 clusters of 1-4 px at 1x). Not fixed here, see follow-up in the chat reply.

## Follow-up: bezier gap repair (implemented)
- New `api/app/pipeline/gap_repair.py`, stage `gap_repair` runs after curves in bezier mode.
- Real image, bezier k=48: gap pixels 0 / 0 / 0 at 0.5x, 1x, 2x (QA) and 0 at 3x (independent render). 4x: ~70 px.
- Report now has `metrics` (fills only), `metrics_with_lines`, and `gap_repair` (iterations, arcs forced to polygon, remaining).
- New tests: `tests/test_gap_repair.py` (without repair that image shows 5 px at 1x and 96 px at 2x, so the test is meaningful).
- Cost: about +18-30 s on a 1672x941 image; env `GAP_REPAIR_SCALES` controls it.
