import io
import math
import logging
from typing import Dict, Any, Tuple, List, Optional
import numpy as np
from PIL import Image
from skimage.metrics import peak_signal_noise_ratio, structural_similarity

logger = logging.getLogger(__name__)


def render_svg_to_png(
    svg_str: str,
    scale: float = 1.0,
    background_color: Optional[str] = None,
) -> bytes:
    """
    Renders SVG string to PNG bytes. Prefers CairoSVG if system cairo is present;
    otherwise falls back smoothly to resvg-py.
    """
    try:
        import cairosvg
        return cairosvg.svg2png(
            bytestring=svg_str.encode("utf-8"),
            scale=scale,
            background_color=background_color,
        )
    except Exception as e:
        logger.debug(f"cairosvg unavailable or failed ({e}), using resvg-py")
        import resvg_py
        return resvg_py.svg_to_bytes(
            svg_string=svg_str,
            zoom=scale,
            background=background_color,
        )


def count_magenta_pixels(png_bytes: bytes) -> Tuple[int, List[Tuple[int, int]]]:
    """Decodes PNG and counts pure-magenta (#ff00ff) pixels indicating transparent gaps."""
    with Image.open(io.BytesIO(png_bytes)) as img:
        rgb = np.array(img.convert("RGB"), dtype=np.uint8)

    # Pure magenta: R=255, G=0, B=255
    magenta_mask = (rgb[:, :, 0] == 255) & (rgb[:, :, 1] == 0) & (rgb[:, :, 2] == 255)
    gap_count = int(np.sum(magenta_mask))

    gap_coords = []
    if gap_count > 0:
        ys, xs = np.nonzero(magenta_mask)
        for y, x in zip(ys[:10], xs[:10]):
            gap_coords.append((int(x), int(y)))

    return gap_count, gap_coords


def run_qa(
    full_svg_str: str,
    fills_only_svg_str: str,
    original_rgb: np.ndarray,
    stage_timings: Dict[str, float],
    regions_count: int,
    arcs_count: int,
    bezier_fallbacks: int = 0,
    invalid_rings_repaired: int = 0,
    gap_repair: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Executes mandatory QA checks:
    1. Zero magenta gap pixels on fills-only SVG at 0.5x, 1x, 2x
    2. Accuracy metrics vs working-resolution original (MAE, PSNR, SSIM)
    3. Structural stats (paths, nodes, file size, timings)
    """
    warnings = []

    # 1. Zero gaps test across 0.5x, 1x, 2x scales
    gaps_by_scale = {}
    first_gap_locations = []
    fills_1x_png = None

    for scale in (0.5, 1.0, 2.0):
        png_fills = render_svg_to_png(fills_only_svg_str, scale=scale, background_color="#ff00ff")
        count, coords = count_magenta_pixels(png_fills)
        gaps_by_scale[f"{scale}x"] = count
        if scale == 1.0:
            fills_1x_png = png_fills
        if count > 0 and not first_gap_locations:
            first_gap_locations = coords

    total_gaps = sum(gaps_by_scale.values())
    if total_gaps > 0:
        warnings.append("gaps_detected")

    # 2. Render 1x preview of fills-only and full SVG
    preview_1x_bytes = render_svg_to_png(full_svg_str, scale=1.0)
    with Image.open(io.BytesIO(preview_1x_bytes)) as img:
        rendered_1x_rgb = np.array(img.convert("RGB"), dtype=np.uint8)

    # Compare 1x render with original working image
    h_orig, w_orig = original_rgb.shape[:2]
    h_rend, w_rend = rendered_1x_rgb.shape[:2]

    if (h_orig, w_orig) != (h_rend, w_rend):
        # Resize rendered to original size if subtle dimension difference
        rendered_pil = Image.fromarray(rendered_1x_rgb).resize((w_orig, h_orig), Image.Resampling.BILINEAR)
        comp_rendered = np.array(rendered_pil, dtype=np.uint8)
    else:
        comp_rendered = rendered_1x_rgb

    # Accuracy metrics
    diff = np.abs(original_rgb.astype(np.float32) - comp_rendered.astype(np.float32))
    mae = float(np.mean(diff))
    raw_psnr = float(peak_signal_noise_ratio(original_rgb, comp_rendered))
    psnr = 100.0 if (math.isinf(raw_psnr) or math.isnan(raw_psnr)) else raw_psnr
    raw_ssim = float(structural_similarity(original_rgb, comp_rendered, channel_axis=2))
    ssim = 1.0 if math.isnan(raw_ssim) else raw_ssim

    # Fidelity of the fills alone (lines add dark pixels and should not count as color error)
    fills_mae = fills_psnr = fills_ssim = None
    if fills_1x_png is not None:
        with Image.open(io.BytesIO(fills_1x_png)) as img:
            fills_rgb = np.array(img.convert("RGB"), dtype=np.uint8)
        if fills_rgb.shape[:2] != (h_orig, w_orig):
            fills_rgb = np.array(
                Image.fromarray(fills_rgb).resize((w_orig, h_orig), Image.Resampling.BILINEAR), dtype=np.uint8
            )
        fills_mae = float(np.mean(np.abs(original_rgb.astype(np.float32) - fills_rgb.astype(np.float32))))
        p = float(peak_signal_noise_ratio(original_rgb, fills_rgb))
        fills_psnr = 100.0 if (math.isinf(p) or math.isnan(p)) else p
        s = float(structural_similarity(original_rgb, fills_rgb, channel_axis=2))
        fills_ssim = 1.0 if math.isnan(s) else s

    # Path and node counts in full SVG
    path_count = full_svg_str.count("<path")
    node_count = sum(full_svg_str.count(cmd) for cmd in ("M", "L", "C", "Z", "m", "l", "c", "z"))
    svg_size_bytes = len(full_svg_str.encode("utf-8"))

    report = {
        # Primary metrics = fills only (the color/shape fidelity). Lines are an artistic layer on top.
        "metrics": {
            "mae": round(fills_mae if fills_mae is not None else mae, 2),
            "psnr": round(fills_psnr if fills_psnr is not None else psnr, 2),
            "ssim": round(fills_ssim if fills_ssim is not None else ssim, 4),
        },
        "metrics_with_lines": {
            "mae": round(mae, 2),
            "psnr": round(psnr, 2),
            "ssim": round(ssim, 4),
        },
        "gap_repair": gap_repair,
        "gaps": {
            "counts": gaps_by_scale,
            "total": total_gaps,
            "locations": first_gap_locations,
        },
        "stats": {
            "paths": path_count,
            "nodes": node_count,
            "size_bytes": svg_size_bytes,
            "size_mb": round(svg_size_bytes / (1024 * 1024), 2),
            "regions": regions_count,
            "arcs": arcs_count,
            "bezier_fallbacks": bezier_fallbacks,
            "invalid_rings_repaired": invalid_rings_repaired,
        },
        "timings_ms": {k: round(v * 1000.0, 1) for k, v in stage_timings.items()},
        "warnings": warnings,
    }

    return {
        "report": report,
        "preview_png": preview_1x_bytes,
    }
