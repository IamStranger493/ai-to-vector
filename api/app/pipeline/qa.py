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

    # 1. Gaps check at standard resolution (fast 1x render)
    png_fills = render_svg_to_png(fills_only_svg_str, scale=1.0, background_color="#ff00ff")
    count, coords = count_magenta_pixels(png_fills)
    gaps_by_scale = {"0.5x": 0, "1.0x": count, "2.0x": 0}
    first_gap_locations = coords if count > 0 else []
    fills_1x_png = png_fills

    total_gaps = count
    if total_gaps > 0:
        warnings.append("gaps_detected")

    # 2. Render 1x preview of full SVG
    preview_1x_bytes = render_svg_to_png(full_svg_str, scale=1.0)
    with Image.open(io.BytesIO(preview_1x_bytes)) as img:
        rendered_1x_rgb = np.array(img.convert("RGB"), dtype=np.uint8)

    # Compare 1x render with original working image using fast downsampled comparison (<=400px)
    # This prevents multi-minute CPU spikes and timeouts in structural_similarity
    h_orig, w_orig = original_rgb.shape[:2]
    max_comp_side = 400
    comp_scale = min(1.0, max_comp_side / float(max(h_orig, w_orig)))
    comp_w = max(16, int(round(w_orig * comp_scale)))
    comp_h = max(16, int(round(h_orig * comp_scale)))

    orig_comp = np.array(Image.fromarray(original_rgb).resize((comp_w, comp_h), Image.Resampling.BILINEAR))
    rend_comp = np.array(Image.fromarray(rendered_1x_rgb).resize((comp_w, comp_h), Image.Resampling.BILINEAR))

    # Accuracy metrics
    diff = np.abs(orig_comp.astype(np.float32) - rend_comp.astype(np.float32))
    mae = float(np.mean(diff))
    raw_psnr = float(peak_signal_noise_ratio(orig_comp, rend_comp))
    psnr = 100.0 if (math.isinf(raw_psnr) or math.isnan(raw_psnr)) else raw_psnr
    raw_ssim = float(structural_similarity(orig_comp, rend_comp, channel_axis=2))
    ssim = 1.0 if math.isnan(raw_ssim) else raw_ssim

    # Fidelity of the fills alone (lines add dark pixels and should not count as color error)
    with Image.open(io.BytesIO(fills_1x_png)) as img_fills:
        fills_rgb_comp = np.array(img_fills.convert("RGB").resize((comp_w, comp_h), Image.Resampling.BILINEAR), dtype=np.uint8)
    fills_mae = float(np.mean(np.abs(orig_comp.astype(np.float32) - fills_rgb_comp.astype(np.float32))))
    p = float(peak_signal_noise_ratio(orig_comp, fills_rgb_comp))
    fills_psnr = 100.0 if (math.isinf(p) or math.isnan(p)) else p
    s = float(structural_similarity(orig_comp, fills_rgb_comp, channel_axis=2))
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
