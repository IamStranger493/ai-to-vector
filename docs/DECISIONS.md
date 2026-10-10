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
