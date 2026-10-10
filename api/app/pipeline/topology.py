import math
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
import numpy as np


@dataclass
class Arc:
    arc_id: int
    vertices: np.ndarray  # (M, 2) float32 coordinates: [ [x, y], ... ]
    left_label: int       # lower region label ID
    right_label: int      # higher region label ID
    node_start: int       # vertex id of vertices[0]
    node_end: int         # vertex id of vertices[-1]
    is_border: bool       # True if left_label == -1 or right_label == -1
    is_polygon: bool = True  # True if polygon mode, False if cubic bezier


@dataclass
class DirectedArcRef:
    arc_id: int
    reversed: bool


@dataclass
class TopologyResult:
    arcs: List[Arc]
    region_rings: Dict[int, List[List[DirectedArcRef]]]
    width: int
    height: int


def extract_topology(labels: np.ndarray) -> TopologyResult:
    """
    Extracts crack-edge boundaries, junction nodes, shared boundary arcs,
    and region boundary rings using half-edge planar face traversal.
    Guarantees zero gaps between adjacent regions by construction.
    """
    h, w = labels.shape
    w_corners = w + 1
    h_corners = h + 1

    # Pad labels with -1 (outside canvas)
    pad = np.pad(labels, 1, mode="constant", constant_values=-1)

    # Step A: Horizontal boundary edges
    # Between (x, y) and (x+1, y)
    diff_h = pad[:-1, 1:-1] != pad[1:, 1:-1]
    y_h, x_h = np.nonzero(diff_h)

    lbl_above = pad[y_h, x_h + 1]
    lbl_below = pad[y_h + 1, x_h + 1]

    # Moving East (x -> x+1): Left is above, Right is below
    start_v_h = y_h * w_corners + x_h
    end_v_h = y_h * w_corners + (x_h + 1)

    # Vertical boundary edges
    # Between (x, y) and (x, y+1)
    diff_v = pad[1:-1, :-1] != pad[1:-1, 1:]
    y_v, x_v = np.nonzero(diff_v)

    lbl_left_px = pad[y_v + 1, x_v]
    lbl_right_px = pad[y_v + 1, x_v + 1]

    # Moving South (y -> y+1): Left is right_px, Right is left_px
    start_v_v = y_v * w_corners + x_v
    end_v_v = (y_v + 1) * w_corners + x_v

    all_start = np.concatenate([start_v_h, start_v_v])
    all_end = np.concatenate([end_v_h, end_v_v])
    all_left = np.concatenate([lbl_above, lbl_right_px])
    all_right = np.concatenate([lbl_below, lbl_left_px])

    # Canonical edge orientation: always left_label < right_label
    swap_mask = all_left > all_right
    starts = np.where(swap_mask, all_end, all_start)
    ends = np.where(swap_mask, all_start, all_end)
    lefts = np.where(swap_mask, all_right, all_left)
    rights = np.where(swap_mask, all_left, all_right)

    num_edges = len(starts)

    # Step B: Vertex to incident edges
    vertex_edges: Dict[int, List[int]] = {}
    for eid in range(num_edges):
        u = int(starts[eid])
        v = int(ends[eid])
        if u not in vertex_edges:
            vertex_edges[u] = []
        vertex_edges[u].append(eid)
        if v not in vertex_edges:
            vertex_edges[v] = []
        vertex_edges[v].append(eid)

    # Step C: Identify Nodes
    # A vertex is a node if degree != 2 OR its incident edges carry different label pairs
    nodes_set = set()
    for vid, eids in vertex_edges.items():
        if len(eids) != 2:
            nodes_set.add(vid)
        else:
            e1, e2 = eids[0], eids[1]
            pair1 = (lefts[e1], rights[e1])
            pair2 = (lefts[e2], rights[e2])
            if pair1 != pair2:
                nodes_set.add(vid)

    # Canvas 4 corners are always nodes to keep canvas boundaries perfectly orthogonal
    canvas_corners = [
        0,                  # (0, 0)
        w,                  # (w, 0)
        h * w_corners + w,  # (w, h)
        h * w_corners,      # (0, h)
    ]
    for cv in canvas_corners:
        if cv in vertex_edges:
            nodes_set.add(cv)

    # Step D: Extract Arcs
    visited_edges = np.zeros(num_edges, dtype=bool)
    arcs: List[Arc] = []
    arc_id_counter = 0

    def vid_to_coord(vid: int) -> Tuple[float, float]:
        return float(vid % w_corners), float(vid // w_corners)

    # 1. Trace arcs starting from nodes
    for node_vid in sorted(nodes_set):
        for eid in vertex_edges[node_vid]:
            if visited_edges[eid]:
                continue

            # Trace this arc
            arc_vids = [node_vid]
            curr_v = node_vid
            curr_e = eid
            target_pair = (lefts[eid], rights[eid])

            while True:
                visited_edges[curr_e] = True
                u = int(starts[curr_e])
                v = int(ends[curr_e])
                next_v = v if u == curr_v else u
                arc_vids.append(next_v)

                if next_v in nodes_set:
                    break  # Reached next node

                # Find next edge at pass-through vertex
                inc = vertex_edges[next_v]
                next_e = inc[1] if inc[0] == curr_e else inc[0]
                curr_v = next_v
                curr_e = next_e

            # Determine orientation along arc_vids
            # Check edge 0 direction
            first_e = eid
            u0 = int(starts[first_e])
            # If traversed from u0 to v0, left is lefts[first_e], right is rights[first_e]
            if arc_vids[0] == u0:
                l_lbl = int(lefts[first_e])
                r_lbl = int(rights[first_e])
            else:
                l_lbl = int(rights[first_e])
                r_lbl = int(lefts[first_e])

            # Ensure left_label < right_label
            if l_lbl > r_lbl:
                arc_vids.reverse()
                l_lbl, r_lbl = r_lbl, l_lbl

            coords = np.array([vid_to_coord(v) for v in arc_vids], dtype=np.float32)
            is_border = (l_lbl == -1 or r_lbl == -1)

            arc = Arc(
                arc_id=arc_id_counter,
                vertices=coords,
                left_label=l_lbl,
                right_label=r_lbl,
                node_start=arc_vids[0],
                node_end=arc_vids[-1],
                is_border=is_border,
            )
            arcs.append(arc)
            arc_id_counter += 1

    # 2. Closed loops with no nodes (islands)
    for eid in range(num_edges):
        if not visited_edges[eid]:
            start_vid = int(starts[eid])
            arc_vids = [start_vid]
            curr_v = start_vid
            curr_e = eid

            while True:
                visited_edges[curr_e] = True
                u = int(starts[curr_e])
                v = int(ends[curr_e])
                next_v = v if u == curr_v else u
                if next_v == start_vid:
                    arc_vids.append(next_v)
                    break
                arc_vids.append(next_v)
                inc = vertex_edges[next_v]
                next_e = inc[1] if inc[0] == curr_e else inc[0]
                curr_v = next_v
                curr_e = next_e

            l_lbl = int(lefts[eid])
            r_lbl = int(rights[eid])
            if l_lbl > r_lbl:
                arc_vids.reverse()
                l_lbl, r_lbl = r_lbl, l_lbl

            coords = np.array([vid_to_coord(v) for v in arc_vids], dtype=np.float32)
            is_border = (l_lbl == -1 or r_lbl == -1)

            arc = Arc(
                arc_id=arc_id_counter,
                vertices=coords,
                left_label=l_lbl,
                right_label=r_lbl,
                node_start=arc_vids[0],
                node_end=arc_vids[-1],
                is_border=is_border,
            )
            arcs.append(arc)
            arc_id_counter += 1

    # Step E: Region rings (half-edge face traversal)
    # Group directed arcs by region
    # For region R:
    # If arc.left_label == R: forward half-arc (start -> end), R is on the left
    # If arc.right_label == R: reversed half-arc (end -> start), R is on the left
    region_half_arcs: Dict[int, List[DirectedArcRef]] = {}
    for arc in arcs:
        if arc.left_label >= 0:
            region_half_arcs.setdefault(arc.left_label, []).append(DirectedArcRef(arc.arc_id, False))
        if arc.right_label >= 0:
            region_half_arcs.setdefault(arc.right_label, []).append(DirectedArcRef(arc.arc_id, True))

    region_rings: Dict[int, List[List[DirectedArcRef]]] = {}

    for r_id, drefs in region_half_arcs.items():
        if not drefs:
            continue

        # Map each node to its outgoing directed arcs for region R
        # Outgoing darc starts at: arc.node_end if reversed else arc.node_start
        # Incoming darc ends at: arc.node_start if reversed else arc.node_end
        outgoing_by_node: Dict[int, List[DirectedArcRef]] = {}
        for dref in drefs:
            arc = arcs[dref.arc_id]
            s_node = arc.node_end if dref.reversed else arc.node_start
            outgoing_by_node.setdefault(s_node, []).append(dref)

        used_drefs = set()
        rings_for_r: List[List[DirectedArcRef]] = []

        for dref in drefs:
            key = (dref.arc_id, dref.reversed)
            if key in used_drefs:
                continue

            # Start a new ring
            current_ring: List[DirectedArcRef] = []
            curr_dref = dref

            while True:
                used_drefs.add((curr_dref.arc_id, curr_dref.reversed))
                current_ring.append(curr_dref)

                curr_arc = arcs[curr_dref.arc_id]
                end_node = curr_arc.node_start if curr_dref.reversed else curr_arc.node_end

                # Check if ring is closed
                first_dref = current_ring[0]
                first_arc = arcs[first_dref.arc_id]
                start_node = first_arc.node_end if first_dref.reversed else first_arc.node_start
                if end_node == start_node and len(current_ring) > 0:
                    # Ring closed!
                    break

                # Choose next outgoing darc at end_node
                candidates = [
                    cand for cand in outgoing_by_node.get(end_node, [])
                    if (cand.arc_id, cand.reversed) not in used_drefs
                ]

                if not candidates:
                    # Should not happen on closed 2D manifold, but break safely
                    break

                if len(candidates) == 1:
                    curr_dref = candidates[0]
                else:
                    # Resolving junction / pinch point with angular sorting:
                    # Compute incoming direction vector at end_node
                    pts = curr_arc.vertices
                    if curr_dref.reversed:
                        v_in = pts[0] - pts[1]
                    else:
                        v_in = pts[-1] - pts[-2]

                    ang_in = math.atan2(float(v_in[1]), float(v_in[0]))

                    # In screen coordinates (where y increases downwards), a left turn
                    # rotates clockwise in Cartesian space, i.e., (ang_in - ang_out) % (2*pi).
                    # We pick the sharpest left turn to maintain the face boundary without figure-8 crossings.
                    def turn_score(cand: DirectedArcRef) -> float:
                        c_arc = arcs[cand.arc_id]
                        c_pts = c_arc.vertices
                        if cand.reversed:
                            v_out = c_pts[-2] - c_pts[-1]
                        else:
                            v_out = c_pts[1] - c_pts[0]
                        ang_out = math.atan2(float(v_out[1]), float(v_out[0]))
                        diff = (ang_in - ang_out) % (2 * math.pi)
                        return diff if diff > 1e-6 else (2 * math.pi)

                    candidates.sort(key=turn_score)
                    curr_dref = candidates[0]

            if current_ring:
                rings_for_r.append(current_ring)

        region_rings[r_id] = rings_for_r

    return TopologyResult(
        arcs=arcs,
        region_rings=region_rings,
        width=w,
        height=h,
    )
