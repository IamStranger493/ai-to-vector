from collections import defaultdict
import numpy as np
from skimage.measure import label as sk_label
from skimage.color import rgb2lab
from app.schemas import RegionsParams


class DisjointSet:
    def __init__(self, n: int):
        self.parent = np.arange(n, dtype=np.int32)
        self.rank = np.zeros(n, dtype=np.int8)

    def find(self, i: int) -> int:
        root = i
        while root != self.parent[root]:
            root = self.parent[root]
        # Path compression
        curr = i
        while curr != root:
            nxt = self.parent[curr]
            self.parent[curr] = root
            curr = nxt
        return root

    def union(self, i: int, j: int) -> int:
        root_i = self.find(i)
        root_j = self.find(j)
        if root_i == root_j:
            return root_i
        # Keep root_i as master or root_j based on rank
        if self.rank[root_i] < self.rank[root_j]:
            self.parent[root_i] = root_j
            return root_j
        elif self.rank[root_i] > self.rank[root_j]:
            self.parent[root_j] = root_i
            return root_i
        else:
            self.parent[root_j] = root_i
            self.rank[root_i] += 1
            return root_i


def build_regions(
    labels0: np.ndarray,
    denoised_rgb: np.ndarray,
    params: RegionsParams,
) -> tuple[np.ndarray, dict]:
    """
    Constructs a planar partition of connected components and merges small regions
    according to adjacency and color difference while protecting fine details.
    Returns:
        final_labels: (H, W) int32 contiguous region IDs [0..N-1]
        stats: dict containing region areas, colors, count, warnings
    """
    h, w = labels0.shape
    lab_img = rgb2lab(denoised_rgb).astype(np.float32)

    # 1. Connected components per palette label (4-connectivity)
    # 4-connectivity structure element
    struct = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], dtype=bool)
    initial_labels = np.zeros((h, w), dtype=np.int32)
    current_id = 0

    from scipy.ndimage import label as ndi_label

    for pal_idx in np.unique(labels0):
        mask = (labels0 == pal_idx)
        comp, count = ndi_label(mask, structure=struct)
        initial_labels[mask] = (comp[mask] - 1) + current_id
        current_id += count

    num_initial = current_id

    # 2. Compute initial stats: area, sum Lab
    areas = np.bincount(initial_labels.ravel(), minlength=num_initial).astype(np.int64)

    # Sum Lab per component
    L_flat = lab_img[:, :, 0].ravel()
    a_flat = lab_img[:, :, 1].ravel()
    b_flat = lab_img[:, :, 2].ravel()
    labels_flat = initial_labels.ravel()

    sum_L = np.bincount(labels_flat, weights=L_flat, minlength=num_initial)
    sum_a = np.bincount(labels_flat, weights=a_flat, minlength=num_initial)
    sum_b = np.bincount(labels_flat, weights=b_flat, minlength=num_initial)

    mean_labs = np.zeros((num_initial, 3), dtype=np.float32)
    valid_mask = areas > 0
    mean_labs[valid_mask, 0] = sum_L[valid_mask] / areas[valid_mask]
    mean_labs[valid_mask, 1] = sum_a[valid_mask] / areas[valid_mask]
    mean_labs[valid_mask, 2] = sum_b[valid_mask] / areas[valid_mask]

    # 3. Build adjacency graph (right and bottom neighbor comparison)
    # Horizontal edges (x and x+1)
    diff_h = initial_labels[:, :-1] != initial_labels[:, 1:]
    u_h = initial_labels[:, :-1][diff_h]
    v_h = initial_labels[:, 1:][diff_h]

    # Vertical edges (y and y+1)
    diff_v = initial_labels[:-1, :] != initial_labels[1:, :]
    u_v = initial_labels[:-1, :][diff_v]
    v_v = initial_labels[1:, :][diff_v]

    all_u = np.concatenate([u_h, u_v])
    all_v = np.concatenate([v_h, v_v])

    min_nodes = np.minimum(all_u, all_v).astype(np.int64)
    max_nodes = np.maximum(all_u, all_v).astype(np.int64)

    # Encode pairs as min * num_initial + max
    pair_keys = min_nodes * num_initial + max_nodes
    unique_pairs, pair_counts = np.unique(pair_keys, return_counts=True)

    # Build adjacency dict: node -> {neighbor: shared_length}
    adj: dict[int, dict[int, int]] = defaultdict(dict)
    for key, count in zip(unique_pairs, pair_counts):
        u = int(key // num_initial)
        v = int(key % num_initial)
        adj[u][v] = int(count)
        adj[v][u] = int(count)

    # 4. Merge small regions using DisjointSet
    ds = DisjointSet(num_initial)
    current_areas = areas.copy()
    current_labs = mean_labs.copy()

    # Sort region IDs by initial area ascending
    sorted_regions = np.argsort(areas)

    for r in sorted_regions:
        root_r = ds.find(r)
        curr_area = current_areas[root_r]

        # Stop if already large enough
        if curr_area >= 4 * params.min_area_px:
            continue

        # Gather active neighbors
        nbr_dict = adj[root_r]
        if not nbr_dict:
            continue

        # Compress neighbors to their current roots
        active_nbrs: dict[int, int] = defaultdict(int)
        for nbr, length in list(nbr_dict.items()):
            root_nbr = ds.find(nbr)
            if root_nbr != root_r:
                active_nbrs[root_nbr] += length

        if not active_nbrs:
            continue

        # Update root_r's adj to active compressed neighbors
        adj[root_r] = active_nbrs

        # Evaluate color differences
        r_lab = current_labs[root_r]
        nbr_list = list(active_nbrs.keys())
        nbr_labs = current_labs[nbr_list]

        # ΔE76 Euclidean distance in Lab
        delta_e = np.linalg.norm(nbr_labs - r_lab[None, :], axis=1)
        max_delta_e = float(np.max(delta_e))

        # Detail protection rule:
        # If max neighbor ΔE > protect_delta_e and area < protect_max_area_px,
        # protect unless tiny (< 3 px).
        if (
            max_delta_e > params.protect_delta_e
            and curr_area < params.protect_max_area_px
            and curr_area >= 3
        ):
            continue

        should_merge = False
        target_nbr = -1

        if curr_area < params.min_area_px:
            # Must merge: pick neighbor with smallest ΔE, tie-break by longest boundary
            # Sort keys: (delta_e, -boundary_length)
            best_idx = int(np.lexsort((
                -np.array([active_nbrs[n] for n in nbr_list]),
                delta_e,
            ))[0])
            target_nbr = nbr_list[best_idx]
            should_merge = True
        elif curr_area < 4 * params.min_area_px:
            min_delta_idx = int(np.argmin(delta_e))
            if delta_e[min_delta_idx] < params.merge_delta_e:
                target_nbr = nbr_list[min_delta_idx]
                should_merge = True

        if should_merge and target_nbr >= 0:
            target_root = ds.find(target_nbr)
            if target_root == root_r:
                continue

            # Merge root_r and target_root
            new_root = ds.union(root_r, target_root)
            old_root = target_root if new_root == root_r else root_r

            new_area = current_areas[new_root] + current_areas[old_root]
            # Area-weighted mean Lab
            new_lab = (
                current_labs[new_root] * current_areas[new_root]
                + current_labs[old_root] * current_areas[old_root]
            ) / max(1, new_area)

            current_areas[new_root] = new_area
            current_labs[new_root] = new_lab

            # Merge adjacency lists
            for nbr, length in adj[old_root].items():
                r_nbr = ds.find(nbr)
                if r_nbr != new_root:
                    adj[new_root][r_nbr] = adj[new_root].get(r_nbr, 0) + length
                    adj[r_nbr][new_root] = adj[new_root][r_nbr]
                    if old_root in adj[r_nbr]:
                        del adj[r_nbr][old_root]

            if old_root in adj[new_root]:
                del adj[new_root][old_root]
            adj[old_root].clear()

    # 5. Flatten parent pointers and remap to contiguous 0..M-1 IDs
    all_roots = np.array([ds.find(i) for i in range(num_initial)], dtype=np.int32)
    unique_roots, remap_indices = np.unique(all_roots, return_inverse=True)
    num_final_regions = len(unique_roots)

    # Remap image pixels
    final_labels = remap_indices[initial_labels].astype(np.int32)

    # Final stats
    final_areas = np.bincount(final_labels.ravel(), minlength=num_final_regions)
    final_labs = current_labs[unique_roots]

    warnings = []
    if num_final_regions > 40000:
        warnings.append("high_region_count")

    stats = {
        "num_regions": num_final_regions,
        "areas": final_areas,
        "mean_labs": final_labs,
        "warnings": warnings,
    }

    return final_labels, stats
