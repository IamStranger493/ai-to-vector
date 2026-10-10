import sys
import os
import math
import numpy as np
import pytest
from shapely.geometry import Polygon, MultiPolygon
from shapely.ops import unary_union

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "api")))

from app.pipeline.topology import extract_topology, TopologyResult


def rings_to_shapely(result: TopologyResult, region_id: int):
    """Converts the rings of a region into a Shapely geometry."""
    rings_drefs = result.region_rings.get(region_id, [])
    if not rings_drefs:
        return None

    ring_polys = []
    for ring in rings_drefs:
        pts = []
        for dref in ring:
            arc = result.arcs[dref.arc_id]
            arc_pts = arc.vertices[::-1] if dref.reversed else arc.vertices
            # Add points (omit first point if continuing from previous arc)
            if not pts:
                pts.extend(arc_pts)
            else:
                pts.extend(arc_pts[1:])
        if len(pts) >= 4:
            ring_polys.append(Polygon(pts))

    if not ring_polys:
        return None

    # Sort by area descending: largest is outer boundary, smaller can be holes
    ring_polys.sort(key=lambda p: p.area, reverse=True)
    # Using symmetric difference / evenodd to build polygon with holes
    geom = ring_polys[0]
    for p in ring_polys[1:]:
        geom = geom.symmetric_difference(p)
    return geom


def test_two_rectangles_side_by_side():
    # 10x20 image: left 10x10 is region 0, right 10x10 is region 1
    labels = np.zeros((10, 20), dtype=np.int32)
    labels[:, 10:] = 1

    topo = extract_topology(labels)

    # Check shared arc between region 0 and region 1
    shared_arcs = [
        arc for arc in topo.arcs
        if (arc.left_label == 0 and arc.right_label == 1) or (arc.left_label == 1 and arc.right_label == 0)
    ]
    assert len(shared_arcs) == 1, "There should be exactly 1 shared arc between regions"
    shared = shared_arcs[0]
    assert not shared.is_border

    # Both regions reference this arc
    r0_arcs = {dref.arc_id for ring in topo.region_rings[0] for dref in ring}
    r1_arcs = {dref.arc_id for ring in topo.region_rings[1] for dref in ring}
    assert shared.arc_id in r0_arcs
    assert shared.arc_id in r1_arcs

    # Shapely areas
    geom0 = rings_to_shapely(topo, 0)
    geom1 = rings_to_shapely(topo, 1)
    assert abs(geom0.area - 100.0) < 1e-4
    assert abs(geom1.area - 100.0) < 1e-4

    union_geom = unary_union([geom0, geom1])
    assert abs(union_geom.area - 200.0) < 1e-4


def test_checkerboard_2x2():
    # 2x2 checkerboard:
    # [[0, 1],
    #  [1, 0]]
    labels = np.array([[0, 1], [1, 0]], dtype=np.int32)
    topo = extract_topology(labels)

    geom0 = rings_to_shapely(topo, 0)
    geom1 = rings_to_shapely(topo, 1)

    assert geom0.is_valid
    assert geom1.is_valid
    assert abs(geom0.area - 2.0) < 1e-4
    assert abs(geom1.area - 2.0) < 1e-4

    union_geom = unary_union([geom0, geom1])
    assert abs(union_geom.area - 4.0) < 1e-4


def test_island_hole():
    # 10x10 image: outer is 0, center 4x4 (from (3,3) to (7,7)) is 1
    labels = np.zeros((10, 10), dtype=np.int32)
    labels[3:7, 3:7] = 1

    topo = extract_topology(labels)

    # Region 0 should have 2 rings (exterior + hole)
    assert len(topo.region_rings[0]) == 2
    # Region 1 should have 1 ring
    assert len(topo.region_rings[1]) == 1

    geom0 = rings_to_shapely(topo, 0)
    geom1 = rings_to_shapely(topo, 1)

    assert geom0.is_valid
    assert geom1.is_valid
    assert abs(geom1.area - 16.0) < 1e-4
    assert abs(geom0.area - (100.0 - 16.0)) < 1e-4


def test_border_arcs_flag():
    labels = np.zeros((6, 6), dtype=np.int32)
    labels[:3, :] = 0
    labels[3:, :] = 1

    topo = extract_topology(labels)

    border_arcs = [arc for arc in topo.arcs if arc.is_border]
    assert len(border_arcs) > 0
    for arc in border_arcs:
        assert arc.left_label == -1 or arc.right_label == -1


def test_random_fuzz_label_maps():
    # Seeded fuzz test on random label maps
    rng = np.random.RandomState(12345)
    for trial in range(15):
        w = rng.randint(10, 25)
        h = rng.randint(10, 25)
        num_classes = rng.randint(2, 5)
        labels = rng.randint(0, num_classes, size=(h, w), dtype=np.int32)

        topo = extract_topology(labels)

        geoms = []
        for r_id in range(num_classes):
            if np.any(labels == r_id):
                geom = rings_to_shapely(topo, r_id)
                assert geom is not None
                assert geom.is_valid
                expected_px = int(np.sum(labels == r_id))
                assert abs(geom.area - expected_px) < 1e-3, f"Trial {trial}: Area mismatch for class {r_id}"
                geoms.append(geom)

        total_poly_area = sum(geom.area for geom in geoms)
        assert abs(total_poly_area - (w * h)) < 1e-3, f"Trial {trial}: Gaps or overlap in partition! Area was {total_poly_area}"
