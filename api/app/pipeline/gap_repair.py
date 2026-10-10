"""
Gap repair for bezier mode.

Shared arcs make the fill geometry gap-free by construction, but fitted Bezier curves can still leave
hairline gaps in rare places (self-touching fits, anti-aliasing at 2x). This module renders the
fills-only SVG over magenta, maps every gap pixel back to the label map, and forces the shared arcs
of the regions around each gap to exact polygon geometry. It repeats with a growing search radius and,
as the last resort, switches every arc to polygon mode (which is exact on the pixel lattice).
"""
import io
import logging
from typing import Callable, Dict, List, Set, Tuple

import numpy as np
from PIL import Image

from app.pipeline.qa import render_svg_to_png

logger = logging.getLogger(__name__)

import os

# Render scales checked/repaired. Add 3 for stricter zoom-in guarantees (slower, more memory).
REPAIR_SCALES = tuple(float(v) for v in os.environ.get("GAP_REPAIR_SCALES", "1,2,3").split(",") if v.strip())
RADIUS_SCHEDULE = (2, 5, 10)
MAX_GAP_POINTS = 5000


def find_gap_points(
    fills_svg: str,
    orig_w: int,
    orig_h: int,
    work_w: int,
    work_h: int,
    scales: Tuple[float, ...] = None,
) -> List[Tuple[int, int]]:
    """Return gap pixels (pure magenta) mapped into working-resolution label-map coordinates."""
    points: Set[Tuple[int, int]] = set()
    for scale in (scales or REPAIR_SCALES):
        png = render_svg_to_png(fills_svg, scale=scale, background_color="#ff00ff")
        with Image.open(io.BytesIO(png)) as img:
            rgb = np.array(img.convert("RGB"), dtype=np.uint8)
        mask = (rgb[:, :, 0] == 255) & (rgb[:, :, 1] == 0) & (rgb[:, :, 2] == 255)
        ys, xs = np.nonzero(mask)
        if len(ys) == 0:
            continue
        # render pixel -> svg width/height units -> viewBox (working) units
        fx = work_w / (orig_w * scale)
        fy = work_h / (orig_h * scale)
        for y, x in zip(ys, xs):
            wx = min(work_w - 1, int((x + 0.5) * fx))
            wy = min(work_h - 1, int((y + 0.5) * fy))
            points.add((wx, wy))
            if len(points) >= MAX_GAP_POINTS:
                return sorted(points)
    return sorted(points)


def _force_polygon(topo, arc_data, region_ids) -> int:
    forced = 0
    for r_id in region_ids:
        for ring in topo.region_rings.get(int(r_id), []):
            for dref in ring:
                data = arc_data[dref.arc_id]
                if not data.is_polygon:
                    data.is_polygon = True
                    forced += 1
    return forced


def repair_gaps(
    topo,
    arc_data: dict,
    final_labels: np.ndarray,
    build_fills_svg: Callable[[], str],
    orig_w: int,
    orig_h: int,
) -> Dict[str, object]:
    """Iteratively remove gaps. Returns a small report dict (stored in report.json)."""
    work_h, work_w = final_labels.shape[:2]
    info: Dict[str, object] = {
        "iterations": 0,
        "gap_points_found": [],
        "arcs_forced_polygon": 0,
        "global_polygon_fallback": False,
        "remaining_gap_points": 0,
    }

    for radius in RADIUS_SCHEDULE:
        pts = find_gap_points(build_fills_svg(), orig_w, orig_h, work_w, work_h)
        info["gap_points_found"].append(len(pts))
        if not pts:
            return info

        regions: Set[int] = set()
        for x, y in pts:
            y0, y1 = max(0, y - radius), min(work_h, y + radius + 1)
            x0, x1 = max(0, x - radius), min(work_w, x + radius + 1)
            regions.update(int(v) for v in np.unique(final_labels[y0:y1, x0:x1]))
        forced = _force_polygon(topo, arc_data, regions)
        info["arcs_forced_polygon"] += forced
        info["iterations"] += 1
        logger.info("gap repair: %d gap points, radius %d, %d regions, %d arcs forced", len(pts), radius, len(regions), forced)
        if forced == 0:
            break  # nothing left to change locally, go to the global fallback

    pts = find_gap_points(build_fills_svg(), orig_w, orig_h, work_w, work_h)
    info["gap_points_found"].append(len(pts))
    if pts:
        # Last resort: exact lattice geometry everywhere (measured gap-free)
        forced = _force_polygon(topo, arc_data, topo.region_rings.keys())
        info["arcs_forced_polygon"] += forced
        info["global_polygon_fallback"] = True
        info["iterations"] += 1
        pts = find_gap_points(build_fills_svg(), orig_w, orig_h, work_w, work_h)
        info["gap_points_found"].append(len(pts))
    info["remaining_gap_points"] = len(pts)
    return info
