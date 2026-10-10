import math
from typing import List, Dict, Tuple
import numpy as np
from app.pipeline.topology import TopologyResult, Arc
from app.pipeline.curves import ArcCurveData, format_coord
from app.schemas import ContourLinesParams


def rgb_to_hex(rgb: np.ndarray) -> str:
    r, g, b = [int(np.clip(round(c), 0, 255)) for c in rgb]
    return f"#{r:02x}{g:02x}{b:02x}"


def generate_contour_lines(
    topo: TopologyResult,
    arc_data: dict[int, ArcCurveData],
    region_colors_rgb: np.ndarray,
    region_layers: dict[int, str],
    params: ContourLinesParams,
    decimals: int = 1,
) -> List[dict]:
    """
    Generates continuous ink contour strokes along shared boundary arcs between regions.
    Returns list of stroke path dicts with 'd', 'stroke', 'stroke_width'.
    """
    if not params.enabled:
        return []

    strokes = []

    for arc in topo.arcs:
        if arc.is_border:
            continue  # Border arcs never get contour stroke per spec

        u = arc.left_label
        v = arc.right_label
        if u < 0 or v < 0:
            continue

        color_u = region_colors_rgb[u].astype(np.float32)
        color_v = region_colors_rgb[v].astype(np.float32)

        # Delta E approximation (RGB Euclidean or CIE Lab)
        # Using Euclidean difference of colors
        delta = float(np.linalg.norm(color_u - color_v))

        diff_layer = (region_layers.get(u) != region_layers.get(v))

        # Draw if delta >= min_delta_e OR arcs separate different layer groups
        if not (delta >= params.min_delta_e or diff_layer):
            continue

        # Stroke width lerp
        factor = float(np.clip((delta - params.min_delta_e) / 40.0, 0.0, 1.0))
        width = params.width_min + factor * (params.width_max - params.width_min)

        # Stroke color
        if params.color_mode == "ink":
            stroke_hex = "#111111"
        else:
            # Darker neighbor multiplied by darken factor
            lum_u = 0.299 * color_u[0] + 0.587 * color_u[1] + 0.114 * color_u[2]
            lum_v = 0.299 * color_v[0] + 0.587 * color_v[1] + 0.114 * color_v[2]
            darker_rgb = color_u if lum_u <= lum_v else color_v
            ink_rgb = darker_rgb * params.darken
            stroke_hex = rgb_to_hex(ink_rgb)

        # Generate path d for arc
        data = arc_data[arc.arc_id]
        path_cmds = []

        if data.is_polygon or not data.bezier_segments:
            pts = data.poly_points
            if len(pts) < 2:
                continue
            path_cmds.append(f"M{format_coord(pts[0, 0], decimals)} {format_coord(pts[0, 1], decimals)}")
            for pt in pts[1:]:
                path_cmds.append(f"L{format_coord(pt[0], decimals)} {format_coord(pt[1], decimals)}")
        else:
            segs = data.bezier_segments
            if not segs:
                continue
            p0 = segs[0][0]
            path_cmds.append(f"M{format_coord(p0[0], decimals)} {format_coord(p0[1], decimals)}")
            for _, c1, c2, p3 in segs:
                path_cmds.append(
                    f"C{format_coord(c1[0], decimals)} {format_coord(c1[1], decimals)} "
                    f"{format_coord(c2[0], decimals)} {format_coord(c2[1], decimals)} "
                    f"{format_coord(p3[0], decimals)} {format_coord(p3[1], decimals)}"
                )

        d_str = "".join(path_cmds)
        if d_str:
            strokes.append({
                "d": d_str,
                "stroke": stroke_hex,
                "stroke_width": round(width, 2),
            })

    return strokes
