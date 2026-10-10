import os
import sys
import xml.etree.ElementTree as ET
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "api")))

from app.pipeline.runner import run_pipeline
from app.schemas import PipelineParams


@pytest.mark.parametrize("img_name", [
    "illustration.png",
    "desert_scene.png",
    "village_scene.png",
])
def test_m2_golden_images_polygon_mode(img_name: str):
    """
    Milestone 2 Acceptance Gate:
    Topology in polygon mode with fills only produces 0 magenta pixels at 0.5x, 1x, 2x,
    and MAE / PSNR within baseline.
    """
    golden_path = os.path.join(os.path.dirname(__file__), "golden", img_name)
    assert os.path.exists(golden_path)

    with open(golden_path, "rb") as f:
        img_bytes = f.read()

    params = PipelineParams()
    params.palette.k = 24
    params.curves.mode = "polygon"
    params.contour_lines.enabled = False
    params.detail_lines.enabled = False
    params.provenance_note = True

    result = run_pipeline(
        job_id=f"test_m2_{img_name}",
        image_bytes=img_bytes,
        params_dict=params.model_dump(),
    )

    svg_bytes = result["svg_bytes"]
    report = result["report"]
    svg_str = svg_bytes.decode("utf-8")

    # 1. Gate: 0 magenta pixels at 0.5x, 1x, 2x
    gap_counts = report["gaps"]["counts"]
    for scale_key, count in gap_counts.items():
        assert count == 0, f"Detected {count} gap pixels at {scale_key} on {img_name} in polygon mode!"

    # 2. SVG parses as XML
    root = ET.fromstring(svg_str)
    assert root.tag.endswith("svg")

    # 3. Expected layers present
    group_ids = [elem.attrib.get("id", "") for elem in root.findall(".//{http://www.w3.org/2000/svg}g")]
    assert any("background" in gid for gid in group_ids)

    # 4. Provenance note present
    assert "Vectorized from AI-generated source" in svg_str

    # 5. Baseline accuracy: MAE <= 8.14, PSNR >= 25.5 dB per Section 9.3
    mae = report["metrics"]["mae"]
    psnr = report["metrics"]["psnr"]
    assert mae <= 8.14, f"MAE {mae} exceeded baseline 8.14 on {img_name}"
    assert psnr >= 25.5, f"PSNR {psnr} fell below baseline 25.5 on {img_name}"

    # Save sample SVG
    samples_dir = os.path.join(os.path.dirname(__file__), "..", "docs", "samples")
    os.makedirs(samples_dir, exist_ok=True)
    out_svg_name = img_name.replace(".png", "_m2_polygon.svg")
    with open(os.path.join(samples_dir, out_svg_name), "wb") as f:
        f.write(svg_bytes)


@pytest.mark.parametrize("img_name", [
    "illustration.png",
    "desert_scene.png",
    "village_scene.png",
])
def test_full_pipeline_with_lines_and_curves(img_name: str):
    """
    Milestone 4-6 Pipeline test:
    Full pipeline with curves, contour lines, detail lines, and Inkscape layers.
    """
    golden_path = os.path.join(os.path.dirname(__file__), "golden", img_name)
    assert os.path.exists(golden_path)

    with open(golden_path, "rb") as f:
        img_bytes = f.read()

    params = PipelineParams()
    params.palette.k = 24
    params.curves.mode = "bezier"
    params.contour_lines.enabled = True
    params.detail_lines.enabled = True
    params.provenance_note = True

    result = run_pipeline(
        job_id=f"test_full_{img_name}",
        image_bytes=img_bytes,
        params_dict=params.model_dump(),
    )

    svg_bytes = result["svg_bytes"]
    report = result["report"]
    svg_str = svg_bytes.decode("utf-8")

    # XML parses cleanly
    root = ET.fromstring(svg_str)
    assert root.tag.endswith("svg")

    # Contour and detail line layers present
    group_ids = [elem.attrib.get("id", "") for elem in root.findall(".//{http://www.w3.org/2000/svg}g")]
    assert "layer-90-lines-contour" in group_ids
    assert "layer-95-lines-detail" in group_ids

    # Save sample SVG
    samples_dir = os.path.join(os.path.dirname(__file__), "..", "docs", "samples")
    os.makedirs(samples_dir, exist_ok=True)
    out_svg_name = img_name.replace(".png", "_full.svg")
    with open(os.path.join(samples_dir, out_svg_name), "wb") as f:
        f.write(svg_bytes)
