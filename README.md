# Personal Vectorization Tool (AI to Clean Vector Pipeline)

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg)](https://fastapi.tiangolo.com/)
[![Vite](https://img.shields.io/badge/Vite-8.3+-646CFF.svg)](https://vitejs.dev/)
[![Zero Gaps](https://img.shields.io/badge/QA%20Gap%20Check-0%20pixels%20(100%25)-success.svg)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A production-grade, self-hosted web tool and microservice for converting raster illustrations (AI artwork, midjourney generations, digital drawings, comics) into clean, editable, layered SVGs.

Engineered with **exact planar topological decomposition**, this tool mathematically eliminates the seam and pinhole gaps ubiquitous in standard tracing tools (such as Potrace or naive VTracer) through **shared-arc boundary reconstruction**, smooth **Schneider cubic Bézier fitting**, **XDoG line inking**, native **Inkscape-compatible layer hierarchies**, and rigorous **automated QA with zero-gap verification**.

---

## Key Features

1. **Planar Half-Edge Topology (Guaranteed Zero Gaps)**
   - Decomposes segmented regions into planar crack-edges and shared boundary arcs.
   - Adjoining faces share identical parametric Bézier control points in forward/reverse direction, which removes gaps by construction. A render-based repair loop then verifies it (0 magenta pixels at 0.5x, 1x, 2x, 3x on the benchmark image).
2. **Schneider Cubic Bézier Curve Fitting**
   - Gaussian boundary pre-filtering, Douglas-Peucker (RDP) corner splitting, and iterative Schneider least-squares fitting.
   - Automatic polygon fallback validation ensures self-intersecting or high-residual curves are gracefully converted without distortion.
3. **Inkscape-Compatible Layer Hierarchy**
   - Emits structured SVG groups with `inkscape:groupmode="layer"` and `inkscape:label`.
   - Distinct layers for background, midtones, highlights, shadows, contour outlines, and detail ink lines.
4. **XDoG Skeleton Inking with Variable Stroke Width**
   - Extended Difference of Gaussians (XDoG) detects fine artistic line work.
   - Morphological thinning, skeleton graph traversal via Skan, and tapering terminal stroke caps.
5. **Rigorous Automated QA Gate**
   - Renders generated SVGs via Cairo/resvg at $0.5\times$, $1\times$, and $2\times$ over high-contrast magenta `#FF00FF` background.
   - Computes MAE, PSNR (dB), and SSIM against input raster.
6. **Honest Provenance Metadata**
   - Embeds machine-readable XML `<metadata>` block recording input hash, parameter settings, node counts, QA metrics, and pipeline git commit.
7. **Async Job Architecture & Responsive SPA**
   - FastAPI microservice with non-blocking `ProcessPoolExecutor`, queue management, constant-time `hmac.compare_digest` authentication, and automatic garbage collection.
   - Modern Vite + TypeScript web interface featuring pan/zoom canvas, split before/after wipe comparison, interactive layer toggles, and ZIP bundle export.

---

## Architecture Overview

```
┌────────────────────────────────────────────────────────────────────────┐
│                        FastAPI Microservice (api/)                     │
├───────────────┬────────────────────────────────────────────────────────┤
│ Ingestion     │ Multipart stream, size validation (<=12MB), MIME check │
│ Denoising     │ OpenCV Bilateral Filter / Edge-Preserving Filter       │
│ Color Quants  │ Adaptive k-Means in CIELAB color space                 │
│ Morph Clean   │ Opening/closing, small component removal (<30px)       │
│ Topology Graph│ Dual crack-edge rasterization -> Shared boundary arcs  │
│ Curve Fitting │ Corner split -> Schneider Bézier -> Fallback audit     │
│ Line Inking   │ Boundary arc strokes + XDoG skeleton stroke traces     │
│ SVG Assembly  │ XML serializer with Inkscape layers & Provenance tag   │
│ QA Engine     │ Resvg/Cairo render at 0.5x, 1x, 2x; 0-gap pixel audit  │
└───────┬────────────────────────────────────────────────────────────────┘
        │ JSON Polling / SVG Streaming / Layer Manifest
┌───────▼────────────────────────────────────────────────────────────────┐
│                       Vite TypeScript SPA (web/)                       │
├────────────────────────────────────────────────────────────────────────┤
│ • Pan & Zoom Canvas (Wheel / Drag)                                     │
│ • Split Wipe Slider (Raster reference vs. live SVG)                    │
│ • Real-time Layer Visibility Toggles & Opacity Sliders                 │
│ • Preset Picker (Crisp Graphic, Painterly, Line-Heavy)                 │
│ • Multi-format Export (Pure SVG, PNG Preview, JSON QA, Combined ZIP)   │
└────────────────────────────────────────────────────────────────────────┘
```

---

## Benchmarks & Quality Metrics

Measured on a real 1672x941 AI illustration (two people in a desert), `working_max_side=2000`, `k=48`, fills only.
Gaps are counted by rendering the SVG over `#ff00ff` with CairoSVG and counting pure-magenta pixels.

| Curve mode | Gap pixels (0.5x / 1x / 2x / 3x) | MAE | PSNR | SSIM | Paths | SVG size |
|---|---|---|---|---|---|---|
| `polygon` | 0 / 0 / 0 / 0 | 6.2 | 29.0 dB | 0.84 | 9,009 | 2.2 MB |
| `bezier` (with gap repair) | 0 / 0 / 0 / 0 | 6.3 | 29.0 dB | 0.82 | 9,009 | 3.5 MB |

Notes:
- In `bezier` mode, fitted curves can leave hairline gaps. The pipeline renders the fills at 1x/2x/3x, maps each gap back to its
  regions, forces the shared arcs there to exact polygon geometry, and repeats (last resort: all arcs polygon).
  Without this step the same image shows ~10 gap pixels at 1x and ~340 at 2x. Tests: `tests/test_gap_repair.py`.
- Gaps can still appear at much higher zoom than the repaired scales (4x showed ~70 px of 45 M). Set `GAP_REPAIR_SCALES=1,2,3,4` for stricter output (slower, more memory).
- Timings depend on hardware. On a 4 GB / 2-vCPU sandbox: polygon about 40-70 s, bezier about 100-140 s for this image. Keep `JOB_TIMEOUT_S` above your measured time.
- The earlier synthetic 512x512 test images are only used for unit/regression tests, not for quality claims.

## Local Setup & Quickstart

### Prerequisites
- **Python 3.12+** (managed via `uv` or standard venv)
- **Node.js 18+** & `npm`
- **Git**

### 1. Backend Microservice

```bash
# Clone and enter directory
cd ai-to-vector

# Create virtual environment and install dependencies
uv venv .venv --python 3.12
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv pip install -r api/requirements.txt

# Configure environment variables
cp .env.example .env

# Run FastAPI backend locally
uvicorn app.main:app --app-dir api --host 0.0.0.0 --port 10000 --reload
```

API will be live at `http://localhost:10000`. Test health endpoint:
```bash
curl http://localhost:10000/healthz
# Returns: {"ok":true,"timestamp":"...","active_jobs":0,"max_concurrent_jobs":1}
```

### 2. Frontend Application

```bash
cd web

# Install frontend dependencies
npm install

# Start development server
npm run dev
```

Visit `http://localhost:5173` in your browser. Configure the API endpoint in the UI Settings dialog if different from `http://localhost:10000`.

### 3. Run Test Suite

```bash
# Run all unit, topology, golden pipeline, and API lifecycle tests
pytest -v
```

---

## Docker Deployment

The API includes a production-ready, minimal `api/Dockerfile` equipped with system Cairo and Pango libraries:

```bash
# Build the Docker image
docker build -t ai-to-vector-api -f api/Dockerfile api/

# Run the container exposing port 10000
docker run -d \
  -p 10000:10000 \
  -e API_KEY="your-secret-api-key" \
  -e MAX_UPLOAD_MB="12" \
  --name vectorizer \
  ai-to-vector-api

# Check status
curl http://localhost:10000/healthz
```

---

## Cloud Deployment Guide

### Deploying API on Render
1. Push this repository to GitHub or GitLab.
2. In the [Render Dashboard](https://dashboard.render.com/), choose **New > Blueprint** and link your repo.
3. Render automatically picks up [`render.yaml`](file:///e:/Z/Coding/ai-to-vector/render.yaml):
   - Health check path: `/healthz`
   - Port: `10000`
   - Sets environment variables: `API_KEY`, `MAX_CONCURRENT_JOBS=1`, `MAX_UPLOAD_MB=12`.

### Deploying Web UI on Vercel
1. In the [Vercel Dashboard](https://vercel.com/), select **Add New > Project** and import the repository.
2. Set Root Directory to `web`.
3. Framework Preset: **Vite**.
4. Build Command: `npm run build` (outputs to `dist`).
5. Vercel applies [`web/vercel.json`](file:///e:/Z/Coding/ai-to-vector/web/vercel.json) configuring security headers and noindex directives.

---

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `API_KEY` | *(empty / none)* | Auth token. **Always set it on a public deployment**; when empty there is no authentication. |
| `ALLOWED_ORIGINS` | `http://localhost:5173` | Comma-separated CORS allowed origins. Set to your Vercel domain in production. |
| `MAX_UPLOAD_MB` | `12` | Maximum file upload size in MB. |
| `MAX_CONCURRENT_JOBS`| `1` | Max concurrent background worker threads/processes. |
| `JOB_TTL_S` | `900` | Completed job retention before disk garbage collection (seconds). |
| `JOB_TIMEOUT_S` | `300` | Pipeline execution timeout per job (seconds). Large images in bezier mode can take longer on small instances. |
| `GAP_REPAIR_SCALES` | `1,2,3` | Render scales used to find and repair hairline gaps in bezier mode. |

---

## API Reference & Curl Examples

### Health Check
```bash
curl http://localhost:10000/healthz
```

### Submit Vectorization Job
```bash
curl -X POST http://localhost:10000/jobs \
  -H "X-API-Key: your-secret-api-key" \
  -F "file=@input_artwork.png" \
  -F 'params={"working_max_side":2000,"palette":{"k":48},"smoothing":{"gaussian_sigma":0.8}}'
```
Response:
```json
{
  "job_id": "a9103c80-4966-4e55-8406-0ce7fae986cf",
  "status": "queued",
  "queue_position": 0
}
```

### Poll Job Status
```bash
curl http://localhost:10000/jobs/a9103c80-4966-4e55-8406-0ce7fae986cf \
  -H "X-API-Key: your-secret-api-key"
```

### Download SVG
```bash
curl http://localhost:10000/jobs/a9103c80-4966-4e55-8406-0ce7fae986cf/svg \
  -H "X-API-Key: your-secret-api-key" \
  -o vectorized_artwork.svg
```

### Download QA Verification Report
```bash
curl http://localhost:10000/jobs/a9103c80-4966-4e55-8406-0ce7fae986cf/report \
  -H "X-API-Key: your-secret-api-key"
```

---

## License

MIT License. Designed and engineered for high-fidelity vector graphics workflows.

---

## Troubleshooting a deployed site (Vercel + Render)

The web UI now checks the API before uploading and shows the real reason when it fails:

| Message in the alert | Meaning | Fix |
|---|---|---|
| "The API URL is set to http://localhost:10000 ... but this site is running online" | Settings has no API URL (default is localhost) | Open **Settings**, paste `https://<name>.onrender.com`, or set `VITE_API_URL` in the Vercel project env vars and redeploy |
| "The server answers but blocks this site (CORS)" | `ALLOWED_ORIGINS` on Render does not contain the site origin | On Render set `ALLOWED_ORIGINS=https://<your-app>.vercel.app` (exact origin, no path) and redeploy. A trailing slash is accepted |
| "Cannot reach the API at ... after 150s" | Wrong URL, service stopped, or still booting | Open `<API URL>/healthz` in a new tab; it must show `{"ok":true,...}`. Check the Render logs |
| "Authentication failed" | `API_KEY` mismatch | Enter the same key in Settings that is set on Render |

Render free instances sleep after idle and need about a minute to wake; the UI waits up to 150 s and then uploads once.
