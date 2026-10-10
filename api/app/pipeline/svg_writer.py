import hashlib
import json
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional
import numpy as np

from app.pipeline.curves import ArcCurveData, render_region_path_d
from app.pipeline.topology import TopologyResult
from app.schemas import PipelineParams


def rgb_to_hex(rgb: np.ndarray) -> str:
    r, g, b = [int(np.clip(round(c), 0, 255)) for c in rgb]
    return f"#{r:02x}{g:02x}{b:02x}"


def write_svg(
    topo: TopologyResult,
    arc_data: dict[int, ArcCurveData],
    region_colors_rgb: np.ndarray,
    region_layers: dict[int, str],
    contour_strokes: List[dict],
    detail_paths: List[dict],
    orig_w: int,
    orig_h: int,
    params: PipelineParams,
    fills_only: bool = False,
) -> str:
    """
    Assembles layered SVG with Inkscape layers, seam safety strokes,
    zero-gap shared arc fills, contour and detail lines, and optional provenance.
    """
    w = topo.width
    h = topo.height
    decimals = params.curves.decimals

    # Group regions by layer name
    layer_regions: Dict[str, List[int]] = {}
    for r_id, layer_name in region_layers.items():
        layer_regions.setdefault(layer_name, []).append(r_id)

    sorted_layer_names = sorted(layer_regions.keys())

    # Build XML string parts
    parts = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
        f'viewBox="0 0 {w} {h}" width="{orig_w}" height="{orig_h}" '
        f'shape-rendering="geometricPrecision">'
    )

    # Provenance metadata
    if params.provenance_note and not fills_only:
        params_hash = hashlib.sha256(json.dumps(params.model_dump(), sort_keys=True).encode()).hexdigest()[:12]
        parts.append('  <title>Vector illustration (traced)</title>')
        parts.append('  <desc>Vectorized from AI-generated source</desc>')
        parts.append(
            f'  <metadata>generator="ai-to-vector" version="1.0" params_hash="{params_hash}"</metadata>'
        )

    # 1. Fill Layers
    for layer_name in sorted_layer_names:
        layer_id = f"layer-{layer_name}"
        parts.append(
            f'  <g id="{layer_id}" inkscape:groupmode="layer" inkscape:label="{layer_name}" fill-rule="evenodd">'
        )
        for r_id in layer_regions[layer_name]:
            d = render_region_path_d(topo, arc_data, r_id, decimals=decimals)
            if not d:
                continue
            color_hex = rgb_to_hex(region_colors_rgb[r_id])
            # Seam safety: same-color stroke of 0.4px hides browser AA hairlines per spec 4.7
            parts.append(
                f'    <path id="region-{r_id}" d="{d}" fill="{color_hex}" stroke="{color_hex}" '
                f'stroke-width="0.4" stroke-linejoin="round"/>'
            )
        parts.append('  </g>')

    if not fills_only:
        # 2. Contour Lines Layer
        if contour_strokes:
            parts.append('  <g id="layer-90-lines-contour" inkscape:groupmode="layer" inkscape:label="90-lines-contour">')
            for stroke in contour_strokes:
                d = stroke["d"]
                stroke_c = stroke["stroke"]
                width = stroke["stroke_width"]
                parts.append(
                    f'    <path d="{d}" fill="none" stroke="{stroke_c}" stroke-width="{width}" '
                    f'stroke-linecap="round" stroke-linejoin="round"/>'
                )
            parts.append('  </g>')

        # 3. Detail Lines Layer
        if detail_paths:
            parts.append('  <g id="layer-95-lines-detail" inkscape:groupmode="layer" inkscape:label="95-lines-detail">')
            for item in detail_paths:
                d = item["d"]
                if item.get("type") == "stroke":
                    parts.append(
                        f'    <path d="{d}" fill="none" stroke="{item["stroke"]}" stroke-width="{item["stroke_width"]}" '
                        f'stroke-linecap="round" stroke-linejoin="round"/>'
                    )
                else:
                    parts.append(f'    <path d="{d}" fill="{item["fill"]}"/>')
            parts.append('  </g>')

    parts.append('</svg>')
    svg_str = "\n".join(parts)

    # Validate well-formed XML
    ET.fromstring(svg_str)
    return svg_str
