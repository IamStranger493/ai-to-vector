"""
Bezier mode must never ship hairline gaps. Uses a photo-like synthetic image (smooth color fields,
organic boundaries, thin shapes) because the 3 KB golden images are too simple to trigger curve-fit gaps.
"""
import io
import os
import sys

import numpy as np
import pytest
from PIL import Image, ImageDraw
from scipy.ndimage import gaussian_filter

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "api")))

from app.pipeline.runner import run_pipeline
from app.schemas import PipelineParams


def make_photo_like(seed: int = 7, w: int = 900, h: int = 600) -> bytes:
    rng = np.random.default_rng(seed)
    fields = [gaussian_filter(rng.random((h, w)), sigma=s) for s in (45, 20, 8)]
    base = np.stack([(f - f.min()) / (f.max() - f.min() + 1e-9) for f in fields], axis=2)
    img = (base * 255).astype(np.uint8)
    pil = Image.fromarray(img)
    d = ImageDraw.Draw(pil)
    for _ in range(25):
        x, y = rng.integers(0, w), rng.integers(0, h)
        r = int(rng.integers(4, 30))
        d.ellipse([x - r, y - r, x + r, y + r], fill=tuple(int(v) for v in rng.integers(0, 255, 3)))
    for _ in range(18):
        x0, y0, x1, y1 = rng.integers(0, w), rng.integers(0, h), rng.integers(0, w), rng.integers(0, h)
        d.line([x0, y0, x1, y1], fill=tuple(int(v) for v in rng.integers(0, 255, 3)), width=int(rng.integers(1, 4)))
    buf = io.BytesIO()
    pil.save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.parametrize("seed", [7, 21])
def test_bezier_mode_has_no_gaps_after_repair(seed: int):
    params = PipelineParams()
    params.working_max_side = 800
    params.palette.k = 20
    params.curves.mode = "bezier"
    params.contour_lines.enabled = False
    params.detail_lines.enabled = False

    result = run_pipeline(job_id=f"gap_{seed}", image_bytes=make_photo_like(seed), params_dict=params.model_dump())
    report = result["report"]

    assert report["gaps"]["total"] == 0, report["gaps"]
    assert "gaps_detected" not in report["warnings"]
    assert report["gap_repair"] is not None
    assert report["gap_repair"]["remaining_gap_points"] == 0
    # Primary metrics are fills-only; the with-lines metrics are reported separately
    assert set(report["metrics"]) == {"mae", "psnr", "ssim"}
    assert set(report["metrics_with_lines"]) == {"mae", "psnr", "ssim"}


def test_polygon_mode_skips_gap_repair():
    params = PipelineParams()
    params.working_max_side = 800
    params.palette.k = 20
    params.curves.mode = "polygon"
    params.contour_lines.enabled = False
    params.detail_lines.enabled = False

    report = run_pipeline("gap_poly", make_photo_like(7), params.model_dump())["report"]
    assert report["gaps"]["total"] == 0
    assert report["gap_repair"] is None
