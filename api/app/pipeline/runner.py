import time
import gc
import logging
from typing import Callable, Optional, Dict, Any
import numpy as np
from skimage.color import rgb2lab

from app.schemas import PipelineParams
from app.pipeline.load import load_image
from app.pipeline.denoise import denoise_image
from app.pipeline.palette import generate_palette, hex_to_rgb
from app.pipeline.regions import build_regions
from app.pipeline.topology import extract_topology
from app.pipeline.curves import process_curves, validate_and_repair_regions
from app.pipeline.layers import assign_region_layers
from app.pipeline.lines_contour import generate_contour_lines
from app.pipeline.lines_detail import generate_detail_lines
from app.pipeline.svg_writer import write_svg
from app.pipeline.qa import run_qa

logger = logging.getLogger(__name__)


def run_pipeline(
    job_id: str,
    image_bytes: bytes,
    params_dict: dict,
    progress_callback: Optional[Callable[[str, float], None]] = None,
) -> dict:
    """Executes the complete vectorization pipeline from end to end."""
    params = PipelineParams.model_validate(params_dict)
    timings = {}

    def report_stage(stage_name: str, progress: float):
        if progress_callback:
            progress_callback(stage_name, progress)
        logger.info(f"Job {job_id} [{stage_name}] {progress * 100:.0f}%")

    # --- 1. Load ---
    t0 = time.time()
    report_stage("load", 0.05)
    loaded = load_image(image_bytes, working_max_side=params.working_max_side)
    timings["load"] = time.time() - t0

    # --- 2. Denoise ---
    t0 = time.time()
    report_stage("denoise", 0.15)
    denoised_rgb = denoise_image(loaded.original_rgb, params.denoise)
    timings["denoise"] = time.time() - t0

    # --- 3. Palette ---
    t0 = time.time()
    report_stage("palette", 0.25)
    labels0, centroids_lab = generate_palette(denoised_rgb, params.palette)
    timings["palette"] = time.time() - t0

    # --- 4. Regions ---
    t0 = time.time()
    report_stage("regions", 0.40)
    final_labels, reg_stats = build_regions(labels0, denoised_rgb, params.regions)
    num_regions = reg_stats["num_regions"]
    region_areas = reg_stats["areas"]
    mean_labs = reg_stats["mean_labs"]

    # Compute region fill colors as mean of UN-DENOISED sRGB source pixels
    # Using np.bincount for speed and exact color fidelity
    r_flat = loaded.original_rgb[:, :, 0].ravel()
    g_flat = loaded.original_rgb[:, :, 1].ravel()
    b_flat = loaded.original_rgb[:, :, 2].ravel()
    lbl_flat = final_labels.ravel()

    sum_r = np.bincount(lbl_flat, weights=r_flat, minlength=num_regions)
    sum_g = np.bincount(lbl_flat, weights=g_flat, minlength=num_regions)
    sum_b = np.bincount(lbl_flat, weights=b_flat, minlength=num_regions)
    denom = np.maximum(1, region_areas)

    region_colors = np.stack([sum_r / denom, sum_g / denom, sum_b / denom], axis=1)

    # Snap to user palette if requested
    if params.palette.user_palette:
        user_rgbs = np.array([hex_to_rgb(h) for h in params.palette.user_palette], dtype=np.uint8)
        user_labs = rgb2lab(user_rgbs.reshape(1, -1, 3)).reshape(-1, 3).astype(np.float32)
        reg_labs = rgb2lab(region_colors.reshape(1, -1, 3)).reshape(-1, 3).astype(np.float32)
        dists = np.linalg.norm(reg_labs[:, None, :] - user_labs[None, :, :], axis=2)
        nearest_u = np.argmin(dists, axis=1)
        region_colors = user_rgbs[nearest_u].astype(np.float32)

    # Count border touches for background detection
    border_pixels = np.concatenate([
        final_labels[0, :],
        final_labels[-1, :],
        final_labels[:, 0],
        final_labels[:, -1],
    ])
    border_touches = np.bincount(border_pixels, minlength=num_regions)

    timings["regions"] = time.time() - t0

    # Free labels0 and intermediate masks
    del labels0
    gc.collect()

    # --- 5. Topology ---
    t0 = time.time()
    report_stage("topology", 0.55)
    topo = extract_topology(final_labels)
    timings["topology"] = time.time() - t0

    # --- 6. Curves ---
    t0 = time.time()
    report_stage("curves", 0.70)
    arc_data = process_curves(topo, params.curves)
    fallbacks, repairs = validate_and_repair_regions(topo, arc_data, region_areas, params.curves)
    timings["curves"] = time.time() - t0

    # --- 7. Layers ---
    t0 = time.time()
    report_stage("layers", 0.75)
    region_layers = assign_region_layers(
        num_regions=num_regions,
        mean_labs=mean_labs,
        region_areas=region_areas,
        border_touch_counts=border_touches,
        params=params.layers,
    )
    timings["layers"] = time.time() - t0

    # --- 8. Contour Lines ---
    t0 = time.time()
    report_stage("contour_lines", 0.80)
    contour_strokes = generate_contour_lines(
        topo=topo,
        arc_data=arc_data,
        region_colors_rgb=region_colors,
        region_layers=region_layers,
        params=params.contour_lines,
        decimals=params.curves.decimals,
    )
    timings["contour_lines"] = time.time() - t0

    # --- 9. Detail Lines ---
    t0 = time.time()
    report_stage("detail_lines", 0.88)
    detail_paths = generate_detail_lines(
        original_rgb=loaded.original_rgb,
        params=params.detail_lines,
        decimals=params.curves.decimals,
    )
    timings["detail_lines"] = time.time() - t0

    # --- 10. SVG Writer ---
    t0 = time.time()
    report_stage("write", 0.93)
    full_svg = write_svg(
        topo=topo,
        arc_data=arc_data,
        region_colors_rgb=region_colors,
        region_layers=region_layers,
        contour_strokes=contour_strokes,
        detail_paths=detail_paths,
        orig_w=loaded.orig_width,
        orig_h=loaded.orig_height,
        params=params,
        fills_only=False,
    )
    fills_svg = write_svg(
        topo=topo,
        arc_data=arc_data,
        region_colors_rgb=region_colors,
        region_layers=region_layers,
        contour_strokes=[],
        detail_paths=[],
        orig_w=loaded.orig_width,
        orig_h=loaded.orig_height,
        params=params,
        fills_only=True,
    )
    timings["write"] = time.time() - t0

    # --- 11. QA ---
    t0 = time.time()
    report_stage("qa", 0.98)
    qa_res = run_qa(
        full_svg_str=full_svg,
        fills_only_svg_str=fills_svg,
        original_rgb=loaded.original_rgb,
        stage_timings=timings,
        regions_count=num_regions,
        arcs_count=len(topo.arcs),
        bezier_fallbacks=fallbacks,
        invalid_rings_repaired=repairs,
    )
    timings["qa"] = time.time() - t0
    report_stage("done", 1.0)

    return {
        "svg_bytes": full_svg.encode("utf-8"),
        "png_bytes": qa_res["preview_png"],
        "report": qa_res["report"],
    }
