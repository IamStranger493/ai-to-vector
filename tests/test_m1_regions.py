import io
import os
import sys
import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "api")))

from app.pipeline.load import load_image
from app.pipeline.denoise import denoise_image
from app.pipeline.palette import generate_palette
from app.pipeline.regions import build_regions
from app.schemas import PipelineParams


def test_m1_pipeline_stages():
    # 1. Create a test image: 200x200 with 3 color blocks and a tiny vivid red spot (rare high-chroma)
    w, h = 200, 200
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    arr[:100, :] = [100, 150, 220]      # Soft blue sky
    arr[100:, :] = [210, 180, 140]      # Sandy desert ground
    arr[80:120, 80:120] = [80, 120, 80]  # Green shrub

    # Vivid rare color spot (10x10 vivid red: chroma > 50)
    arr[95:105, 95:105] = [240, 20, 20]

    # Encode to PNG bytes
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG")
    img_bytes = buf.getvalue()

    params = PipelineParams()
    params.palette.k = 8
    params.regions.min_area_px = 10
    params.regions.protect_delta_e = 20.0

    # Test load
    loaded = load_image(img_bytes, working_max_side=params.working_max_side)
    assert loaded.working_width == 200
    assert loaded.working_height == 200

    # Test denoise
    denoised = denoise_image(loaded.original_rgb, params.denoise)
    assert denoised.shape == (200, 200, 3)

    # Test palette
    labels0, centroids_lab = generate_palette(denoised, params.palette)
    assert labels0.shape == (200, 200)
    assert len(centroids_lab) <= params.palette.k

    # Test regions
    final_labels, stats = build_regions(labels0, denoised, params.regions)
    assert final_labels.shape == (200, 200)

    # Gate check 1: Every pixel in exactly one region (0 to num_regions - 1)
    num_regions = stats["num_regions"]
    assert num_regions >= 4  # Sky, ground, shrub, red spot
    assert final_labels.min() == 0
    assert final_labels.max() == num_regions - 1
    assert len(np.unique(final_labels)) == num_regions

    # Gate check 2: Rare vivid color preserved
    # Check that the vivid red area (center 100, 100) has its own region
    red_region_id = final_labels[100, 100]
    # Check that the region color is vivid (mean Lab has high chroma)
    red_lab = stats["mean_labs"][red_region_id]
    chroma = np.sqrt(red_lab[1] ** 2 + red_lab[2] ** 2)
    assert chroma > 30.0, f"Rare vivid color was not preserved! Chroma was {chroma}"

    # Gate check 3: Write debug PNG of the region map
    # Assign distinct colors to regions for visualization
    rng = np.random.RandomState(42)
    palette_vis = rng.randint(0, 255, size=(num_regions, 3), dtype=np.uint8)
    debug_vis = palette_vis[final_labels]

    os.makedirs(os.path.join(os.path.dirname(__file__), "debug"), exist_ok=True)
    debug_path = os.path.join(os.path.dirname(__file__), "debug", "m1_regions_debug.png")
    Image.fromarray(debug_vis).save(debug_path)
    assert os.path.exists(debug_path)
    assert os.path.getsize(debug_path) > 0
