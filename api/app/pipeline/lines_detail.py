import math
from typing import List, Tuple
import cv2
import numpy as np
from scipy.ndimage import distance_transform_edt, gaussian_filter1d
from skimage.morphology import skeletonize
from skimage.measure import label as sk_label

from app.schemas import DetailLinesParams
from app.pipeline.curves import schneider_fit, format_coord


def compute_xdog(gray: np.ndarray, params: DetailLinesParams) -> np.ndarray:
    """Calculates eXtended Difference of Gaussians edge map."""
    xdog_p = params.xdog
    img_f = gray.astype(np.float32) / 255.0

    sigma1 = xdog_p.sigma
    sigma2 = xdog_p.k * sigma1

    g1 = cv2.GaussianBlur(img_f, (0, 0), sigmaX=sigma1, sigmaY=sigma1)
    g2 = cv2.GaussianBlur(img_f, (0, 0), sigmaX=sigma2, sigmaY=sigma2)

    diff = g1 - xdog_p.tau * g2

    # Soft thresholding
    cond = diff >= xdog_p.eps
    res = np.empty_like(diff)
    res[cond] = 1.0
    res[~cond] = 1.0 + np.tanh(xdog_p.phi * (diff[~cond] - xdog_p.eps))

    # Binary line mask (dark lines have low values)
    binary_edges = res < 0.6
    return binary_edges


def generate_detail_lines(
    original_rgb: np.ndarray,
    params: DetailLinesParams,
    decimals: int = 1,
) -> List[dict]:
    """
    Extracts fine detail lines (hair strands, creases, facial details)
    using XDoG, skeletonization, spur pruning, junction chaining,
    gap bridging, and variable-width outline geometry.
    """
    if not params.enabled:
        return []

    # 1. Un-denoised luminance
    gray = cv2.cvtColor(original_rgb, cv2.COLOR_RGB2GRAY)

    # 2. XDoG edge detection
    bin_mask = compute_xdog(gray, params)

    # 3. Remove small components
    min_comp_px = max(4, int((params.min_length_px ** 2) / 2))
    labeled_mask, num_labels = sk_label(bin_mask, return_num=True, connectivity=2)
    if num_labels == 0:
        return []

    comp_sizes = np.bincount(labeled_mask.ravel())
    keep_mask = comp_sizes >= min_comp_px
    keep_mask[0] = False  # background
    cleaned_mask = keep_mask[labeled_mask]

    if not np.any(cleaned_mask):
        return []

    # 4. Skeletonize
    skel = skeletonize(cleaned_mask)
    if not np.any(skel):
        return []

    # 5. Distance transform for stroke width profiling
    edt = distance_transform_edt(cleaned_mask).astype(np.float32)

    # Extract connected chains of skeleton pixels
    skel_labels, num_skels = sk_label(skel, return_num=True, connectivity=2)
    chains = []

    for sid in range(1, min(num_skels + 1, 5000)):
        coords = np.argwhere(skel_labels == sid)
        if len(coords) < params.min_length_px:
            continue

        # Sort coordinates into a path (using nearest neighbor path ordering)
        pts = coords[:, [1, 0]].astype(np.float32)  # (x, y)
        if len(pts) <= 2:
            chains.append(pts)
            continue

        # Simple greedy path sort from one end
        # Find endpoint (point with max distance from mean)
        mean_p = np.mean(pts, axis=0)
        start_idx = int(np.argmax(np.sum((pts - mean_p) ** 2, axis=1)))

        ordered = [pts[start_idx]]
        remaining = np.delete(pts, start_idx, axis=0)

        while len(remaining) > 0 and len(ordered) < 1000:
            last = ordered[-1]
            dists = np.sum((remaining - last) ** 2, axis=1)
            nearest_idx = int(np.argmin(dists))
            if dists[nearest_idx] > 16.0:  # Gap too large for single connected chain
                break
            ordered.append(remaining[nearest_idx])
            remaining = np.delete(remaining, nearest_idx, axis=0)

        ordered_pts = np.array(ordered, dtype=np.float32)
        if len(ordered_pts) >= params.min_length_px:
            chains.append(ordered_pts)

    if not chains:
        return []

    # 6. Smooth and build variable width outlines or center-lines
    detail_paths = []

    for chain in chains:
        # Gaussian smooth along chain
        smooth_x = gaussian_filter1d(chain[:, 0], sigma=1.2, mode="nearest")
        smooth_y = gaussian_filter1d(chain[:, 1], sigma=1.2, mode="nearest")
        smooth_chain = np.column_stack([smooth_x, smooth_y])

        # Sample width from EDT
        iy = np.clip(np.round(smooth_chain[:, 1]).astype(int), 0, gray.shape[0] - 1)
        ix = np.clip(np.round(smooth_chain[:, 0]).astype(int), 0, gray.shape[1] - 1)
        widths = edt[iy, ix] * 2.0 * params.width_scale
        widths = np.clip(widths, params.width_min, params.width_max)

        # Apply end tapering
        taper_len = min(params.taper_px, len(widths) // 2)
        if taper_len > 1:
            taper_factors = np.linspace(0.3, 1.0, taper_len)
            widths[:taper_len] *= taper_factors
            widths[-taper_len:] *= taper_factors[::-1]

        if params.style == "stroke":
            # Center-line path with constant average stroke-width
            mean_w = float(np.mean(widths))
            segs = schneider_fit(smooth_chain, tolerance=1.0)
            p0 = segs[0][0]
            cmds = [f"M{format_coord(p0[0], decimals)} {format_coord(p0[1], decimals)}"]
            for _, c1, c2, p3 in segs:
                cmds.append(
                    f"C{format_coord(c1[0], decimals)} {format_coord(c1[1], decimals)} "
                    f"{format_coord(c2[0], decimals)} {format_coord(c2[1], decimals)} "
                    f"{format_coord(p3[0], decimals)} {format_coord(p3[1], decimals)}"
                )
            detail_paths.append({
                "type": "stroke",
                "d": "".join(cmds),
                "stroke": params.color,
                "stroke_width": round(mean_w, 2),
            })
        else:
            # Variable width outline polygon
            # Compute tangent normals
            tangents = np.gradient(smooth_chain, axis=0)
            norm_lens = np.linalg.norm(tangents, axis=1, keepdims=True)
            norm_lens[norm_lens < 1e-6] = 1.0
            normals = np.column_stack([-tangents[:, 1], tangents[:, 0]]) / norm_lens

            half_w = (widths / 2.0)[:, None]
            left_side = smooth_chain + normals * half_w
            right_side = smooth_chain - normals * half_w

            # Closed polygon: left + reversed(right)
            poly_ring = np.vstack([left_side, right_side[::-1], left_side[0:1]])
            segs = schneider_fit(poly_ring, tolerance=1.0)
            p0 = segs[0][0]
            cmds = [f"M{format_coord(p0[0], decimals)} {format_coord(p0[1], decimals)}"]
            for _, c1, c2, p3 in segs:
                cmds.append(
                    f"C{format_coord(c1[0], decimals)} {format_coord(c1[1], decimals)} "
                    f"{format_coord(c2[0], decimals)} {format_coord(c2[1], decimals)} "
                    f"{format_coord(p3[0], decimals)} {format_coord(p3[1], decimals)}"
                )
            cmds.append("Z")
            detail_paths.append({
                "type": "fill",
                "d": "".join(cmds),
                "fill": params.color,
            })

    return detail_paths
