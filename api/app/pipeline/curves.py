import math
from typing import List, Tuple, Optional
import numpy as np
from scipy.ndimage import gaussian_filter1d
from shapely.geometry import Polygon

from app.pipeline.topology import Arc, TopologyResult, DirectedArcRef
from app.schemas import CurvesParams


def format_coord(v: float, decimals: int = 1) -> str:
    """Formats coordinate with given decimals, stripping trailing .0."""
    s = f"{v:.{decimals}f}"
    if s.endswith(".0") and decimals == 1:
        return s[:-2]
    return s


def rdp_simplify(points: np.ndarray, epsilon: float) -> np.ndarray:
    """Ramer-Douglas-Peucker polyline simplification with endpoints fixed."""
    if len(points) <= 2:
        return points

    p_start = points[0]
    p_end = points[-1]
    line_vec = p_end - p_start
    line_len = np.linalg.norm(line_vec)

    if line_len < 1e-7:
        dists = np.linalg.norm(points[1:-1] - p_start, axis=1)
    else:
        # Distance of point to line segment
        u = line_vec / line_len
        diffs = points[1:-1] - p_start
        projs = np.dot(diffs, u)
        perp_vecs = diffs - projs[:, None] * u[None, :]
        dists = np.linalg.norm(perp_vecs, axis=1)

    max_idx = int(np.argmax(dists)) + 1
    max_dist = dists[max_idx - 1]

    if max_dist > epsilon:
        left = rdp_simplify(points[:max_idx + 1], epsilon)
        right = rdp_simplify(points[max_idx:], epsilon)
        return np.vstack([left[:-1], right])
    else:
        return np.array([p_start, p_end])


def detect_corners(points: np.ndarray, corner_angle_deg: float, window: int = 3) -> List[int]:
    """Detects corner indices along an unsmoothed arc where turning angle > corner_angle_deg."""
    n = len(points)
    if n <= window * 2:
        return []

    corners = []
    thresh_rad = math.radians(corner_angle_deg)

    for i in range(window, n - window):
        v1 = points[i] - points[i - window]
        v2 = points[i + window] - points[i]
        len1 = np.linalg.norm(v1)
        len2 = np.linalg.norm(v2)
        if len1 < 1e-6 or len2 < 1e-6:
            continue
        cos_ang = np.dot(v1, v2) / (len1 * len2)
        cos_ang = np.clip(cos_ang, -1.0, 1.0)
        ang = math.acos(cos_ang)
        if ang >= thresh_rad:
            corners.append(i)

    return corners


def smooth_arc_points(points: np.ndarray, sigma: float, is_closed: bool) -> np.ndarray:
    """Gaussian smoothing along arc length while keeping endpoints fixed."""
    if sigma <= 0 or len(points) <= 2:
        return points.copy()

    if is_closed:
        smoothed_x = gaussian_filter1d(points[:, 0], sigma=sigma, mode="wrap")
        smoothed_y = gaussian_filter1d(points[:, 1], sigma=sigma, mode="wrap")
        return np.column_stack([smoothed_x, smoothed_y])
    else:
        # Endpoints fixed: smooth interior only
        res = points.copy()
        if len(points) > 4:
            smoothed_x = gaussian_filter1d(points[:, 0], sigma=sigma, mode="nearest")
            smoothed_y = gaussian_filter1d(points[:, 1], sigma=sigma, mode="nearest")
            res[1:-1, 0] = smoothed_x[1:-1]
            res[1:-1, 1] = smoothed_y[1:-1]
        return res


# --- Schneider's Bezier Curve Fitting Algorithm ---

def fit_cubic_bezier_segment(points: np.ndarray, t_hat1: np.ndarray, t_hat2: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Computes cubic bezier control points c1, c2 given endpoint tangents using least squares."""
    n = len(points)
    p0 = points[0]
    p3 = points[-1]

    # Chord length parameterization
    dists = np.linalg.norm(np.diff(points, axis=0), axis=1)
    tot = np.sum(dists)
    if tot < 1e-7:
        u = np.linspace(0, 1, n)
    else:
        u = np.concatenate([[0], np.cumsum(dists) / tot])

    # Bernstein polynomials
    b0 = (1 - u) ** 3
    b1 = 3 * u * (1 - u) ** 2
    b2 = 3 * (u ** 2) * (1 - u)
    b3 = u ** 3

    # A1 = b1 * t_hat1, A2 = b2 * t_hat2
    a1 = b1[:, None] * t_hat1[None, :]
    a2 = b2[:, None] * t_hat2[None, :]

    c_matrix = np.zeros((2, 2))
    c_matrix[0, 0] = np.sum(np.sum(a1 * a1, axis=1))
    c_matrix[0, 1] = np.sum(np.sum(a1 * a2, axis=1))
    c_matrix[1, 0] = c_matrix[0, 1]
    c_matrix[1, 1] = np.sum(np.sum(a2 * a2, axis=1))

    rhs = points - (b0[:, None] * p0[None, :] + (b1[:, None] + b2[:, None]) * p0[None, :] * 0 + b3[:, None] * p3[None, :])
    # RHS for least squares
    v1 = np.sum(np.sum(rhs * a1, axis=1))
    v2 = np.sum(np.sum(rhs * a2, axis=1))

    det = c_matrix[0, 0] * c_matrix[1, 1] - c_matrix[0, 1] * c_matrix[1, 0]
    if abs(det) < 1e-7:
        dist = np.linalg.norm(p3 - p0) / 3.0
        return p0 + t_hat1 * dist, p3 + t_hat2 * dist

    alpha_l = (v1 * c_matrix[1, 1] - v2 * c_matrix[0, 1]) / det
    alpha_r = (c_matrix[0, 0] * v2 - c_matrix[1, 0] * v1) / det

    if alpha_l <= 0 or alpha_r <= 0:
        dist = np.linalg.norm(p3 - p0) / 3.0
        return p0 + t_hat1 * dist, p3 + t_hat2 * dist

    c1 = p0 + t_hat1 * alpha_l
    c2 = p3 + t_hat2 * alpha_r
    return c1, c2


def eval_bezier(p0: np.ndarray, c1: np.ndarray, c2: np.ndarray, p3: np.ndarray, t: np.ndarray) -> np.ndarray:
    b0 = ((1 - t) ** 3)[:, None]
    b1 = (3 * t * ((1 - t) ** 2))[:, None]
    b2 = (3 * (t ** 2) * (1 - t))[:, None]
    b3 = (t ** 3)[:, None]
    return b0 * p0 + b1 * c1 + b2 * c2 + b3 * p3


def schneider_fit(points: np.ndarray, tolerance: float) -> List[Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]]:
    """Recursively fits cubic Bezier curves to points with error under tolerance."""
    if len(points) <= 2:
        p0 = points[0]
        p3 = points[-1]
        c1 = p0 + (p3 - p0) / 3.0
        c2 = p0 + 2 * (p3 - p0) / 3.0
        return [(p0, c1, c2, p3)]

    # Tangents at endpoints
    t1 = points[1] - points[0]
    l1 = np.linalg.norm(t1)
    t_hat1 = t1 / l1 if l1 > 1e-7 else np.array([1.0, 0.0])

    t2 = points[-2] - points[-1]
    l2 = np.linalg.norm(t2)
    t_hat2 = t2 / l2 if l2 > 1e-7 else np.array([-1.0, 0.0])

    c1, c2 = fit_cubic_bezier_segment(points, t_hat1, t_hat2)

    # Check max error
    dists = np.linalg.norm(np.diff(points, axis=0), axis=1)
    tot = np.sum(dists)
    u = np.concatenate([[0], np.cumsum(dists) / tot]) if tot > 1e-7 else np.linspace(0, 1, len(points))
    fitted_pts = eval_bezier(points[0], c1, c2, points[-1], u)
    errs = np.linalg.norm(points - fitted_pts, axis=1)

    max_idx = int(np.argmax(errs))
    max_err = float(errs[max_idx])

    if max_err <= tolerance or max_idx == 0 or max_idx == len(points) - 1:
        return [(points[0], c1, c2, points[-1])]
    else:
        left = schneider_fit(points[:max_idx + 1], tolerance)
        right = schneider_fit(points[max_idx:], tolerance)
        return left + right


class ArcCurveData:
    def __init__(self, arc_id: int):
        self.arc_id = arc_id
        # Polyline points for polygon mode: [ [x, y], ... ]
        self.poly_points: np.ndarray = np.empty((0, 2), dtype=np.float32)
        # Cubic bezier segments: [ (p0, c1, c2, p3), ... ]
        self.bezier_segments: List[Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = []
        self.is_polygon: bool = False


def process_curves(topo: TopologyResult, params: CurvesParams) -> dict[int, ArcCurveData]:
    """
    Smoothes, simplifies (RDP), and fits cubic Beziers (Schneider) on each arc.
    Operates at arc-level so shared boundaries are perfectly consistent.
    """
    arc_data: dict[int, ArcCurveData] = {}

    for arc in topo.arcs:
        data = ArcCurveData(arc.arc_id)
        pts = arc.vertices
        is_closed = (arc.node_start == arc.node_end)

        # 1. Corner detection
        corners = detect_corners(pts, params.corner_angle_deg, window=3)

        # 2. De-staircase Gaussian smoothing
        smoothed = smooth_arc_points(pts, params.smooth_sigma_px, is_closed=is_closed)

        if arc.is_border:
            # Canvas boundaries are straight edges and must never bow inward into the canvas
            on_top = (pts[:, 1] == 0)
            on_bottom = (pts[:, 1] == topo.height)
            on_left = (pts[:, 0] == 0)
            on_right = (pts[:, 0] == topo.width)
            smoothed[on_top, 1] = 0.0
            smoothed[on_bottom, 1] = float(topo.height)
            smoothed[on_left, 0] = 0.0
            smoothed[on_right, 0] = float(topo.width)

        # Split arc at corners and process each piece
        split_indices = [0] + corners + [len(pts)]
        all_poly_pts = []
        all_beziers = []

        for i in range(len(split_indices) - 1):
            s_idx = split_indices[i]
            e_idx = split_indices[i + 1]
            piece = smoothed[s_idx:e_idx]
            if len(piece) < 2:
                continue

            # 3. RDP simplify
            simp = rdp_simplify(piece, params.rdp_epsilon_px)
            if not all_poly_pts:
                all_poly_pts.extend(simp)
            else:
                all_poly_pts.extend(simp[1:])

            # 4. Schneider Bezier fit
            # If the piece lies entirely along a canvas border, keep it linear (straight line)
            is_canvas_edge = arc.is_border and (
                np.all(piece[:, 1] == 0) or np.all(piece[:, 1] == topo.height) or
                np.all(piece[:, 0] == 0) or np.all(piece[:, 0] == topo.width)
            )

            if params.mode == "bezier" and not is_canvas_edge:
                bez = schneider_fit(piece, params.fit_tolerance_px)
                all_beziers.extend(bez)
            elif params.mode == "bezier" and is_canvas_edge:
                # Flat straight border segment: fit as straight line bezier
                p0 = simp[0]
                p3 = simp[-1]
                c1 = p0 + (p3 - p0) / 3.0
                c2 = p0 + 2.0 * (p3 - p0) / 3.0
                all_beziers.append((p0, c1, c2, p3))

        data.poly_points = np.array(all_poly_pts, dtype=np.float32)
        data.bezier_segments = all_beziers
        data.is_polygon = (params.mode == "polygon")
        arc_data[arc.arc_id] = data

    return arc_data


def render_region_path_d(
    topo: TopologyResult,
    arc_data: dict[int, ArcCurveData],
    region_id: int,
    decimals: int = 1,
) -> str:
    """Generates the SVG path 'd' attribute for a region from its rings."""
    rings_drefs = topo.region_rings.get(region_id, [])
    if not rings_drefs:
        return ""

    path_commands = []

    for ring in rings_drefs:
        first_point = True

        for dref in ring:
            data = arc_data[dref.arc_id]
            is_rev = dref.reversed

            if data.is_polygon or not data.bezier_segments:
                # Polygon mode (L commands)
                pts = data.poly_points[::-1] if is_rev else data.poly_points
                for i, pt in enumerate(pts):
                    x_str = format_coord(pt[0], decimals)
                    y_str = format_coord(pt[1], decimals)
                    if first_point and i == 0:
                        path_commands.append(f"M{x_str} {y_str}")
                        first_point = False
                    elif not (first_point and i == 0) and i > 0:
                        path_commands.append(f"L{x_str} {y_str}")
            else:
                # Bezier mode (C commands)
                segs = data.bezier_segments
                if is_rev:
                    # Reversal rule: reverse segment order and swap c1 and c2
                    rev_segs = []
                    for p0, c1, c2, p3 in reversed(segs):
                        rev_segs.append((p3, c2, c1, p0))
                    curr_segs = rev_segs
                else:
                    curr_segs = segs

                for i, (p0, c1, c2, p3) in enumerate(curr_segs):
                    if first_point and i == 0:
                        path_commands.append(f"M{format_coord(p0[0], decimals)} {format_coord(p0[1], decimals)}")
                        first_point = False

                    c1x = format_coord(c1[0], decimals)
                    c1y = format_coord(c1[1], decimals)
                    c2x = format_coord(c2[0], decimals)
                    c2y = format_coord(c2[1], decimals)
                    p3x = format_coord(p3[0], decimals)
                    p3y = format_coord(p3[1], decimals)
                    path_commands.append(f"C{c1x} {c1y} {c2x} {c2y} {p3x} {p3y}")

        path_commands.append("Z")

    return "".join(path_commands)


def validate_and_repair_regions(
    topo: TopologyResult,
    arc_data: dict[int, ArcCurveData],
    region_areas: np.ndarray,
    params: CurvesParams,
) -> tuple[int, int]:
    """
    Mandatory validation per spec: Checks each region polygon area against raster area.
    If area error > 2%, falls back region's shared arcs to polygon mode and repairs.
    Returns:
        (bezier_fallbacks_count, invalid_rings_repaired)
    """
    bezier_fallbacks = 0
    invalid_repaired = 0

    if params.mode != "bezier":
        return 0, 0

    for r_id, rings in topo.region_rings.items():
        if not rings:
            continue

        raster_area = float(region_areas[r_id])
        # Sample Bezier curve points to build shapely Polygon
        sample_polys = []
        for ring in rings:
            sampled_pts = []
            for dref in ring:
                data = arc_data[dref.arc_id]
                if data.is_polygon or not data.bezier_segments:
                    pts = data.poly_points[::-1] if dref.reversed else data.poly_points
                    sampled_pts.extend(pts[1:] if sampled_pts else pts)
                else:
                    segs = data.bezier_segments
                    curr_segs = [(p3, c2, c1, p0) for p0, c1, c2, p3 in reversed(segs)] if dref.reversed else segs
                    for p0, c1, c2, p3 in curr_segs:
                        # Sample 8 points along Bezier
                        ts = np.linspace(0, 1, 8)
                        b_pts = eval_bezier(p0, c1, c2, p3, ts)
                        sampled_pts.extend(b_pts[1:] if sampled_pts else b_pts)

            if len(sampled_pts) >= 4:
                sample_polys.append(Polygon(sampled_pts))

        if not sample_polys:
            continue

        sample_polys.sort(key=lambda p: p.area, reverse=True)
        geom = sample_polys[0]
        for p in sample_polys[1:]:
            geom = geom.symmetric_difference(p)

        poly_area = float(geom.area)
        is_valid = geom.is_valid

        # Tolerance checks: error < 2% or < 3px for small regions
        area_error = abs(poly_area - raster_area)
        rel_error = area_error / max(1.0, raster_area)

        fails = (not is_valid) or (rel_error >= 0.02 and area_error >= 3.0)

        if fails:
            # Fall back ALL arcs of this region to polygon mode!
            bezier_fallbacks += 1
            if not is_valid:
                invalid_repaired += 1
            for ring in rings:
                for dref in ring:
                    arc_data[dref.arc_id].is_polygon = True

    return bezier_fallbacks, invalid_repaired
