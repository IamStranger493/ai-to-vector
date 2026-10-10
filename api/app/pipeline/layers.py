import math
from typing import Dict, List, Tuple
import numpy as np
from app.schemas import LayersParams


def classify_hue_family(L: float, a: float, b: float) -> str:
    """Classifies a CIE Lab color into an artist-friendly hue family."""
    chroma = math.sqrt(a * a + b * b)
    if chroma < 8.0:
        return "neutral"

    # Hue angle in degrees [0, 360)
    hue = math.degrees(math.atan2(b, a)) % 360.0

    # CIE Lab hue angle boundaries:
    # a+ is red/magenta, b+ is yellow, a- is green, b- is blue
    if 20 <= hue < 55:
        return "orange" if chroma > 15 and L > 45 else "brown"
    elif 55 <= hue < 100:
        return "yellow"
    elif 100 <= hue < 170:
        return "green"
    elif 170 <= hue < 260:
        return "cyan-blue"
    elif 260 <= hue < 330:
        return "purple-magenta"
    else:  # 330..360 or 0..20
        return "red"


def assign_region_layers(
    num_regions: int,
    mean_labs: np.ndarray,
    region_areas: np.ndarray,
    border_touch_counts: np.ndarray,
    params: LayersParams,
) -> dict[int, str]:
    """
    Assigns each region to an artist layer:
    00-background: largest region by area or touching most border
    10..80-fill-<hue>-<tone>: grouped by hue family and tone quantile
    99-highlights: top luminance band (optional)
    """
    region_layers = {}

    # 1. Background region: region with highest border touch count or largest area
    bg_candidate = int(np.argmax(border_touch_counts))
    if border_touch_counts[bg_candidate] == 0:
        bg_candidate = int(np.argmax(region_areas))

    region_layers[bg_candidate] = "00-background"

    # 2. Group other regions by hue family
    family_regions: dict[str, list[int]] = {}
    for r_id in range(num_regions):
        if r_id == bg_candidate:
            continue
        L, a, b = mean_labs[r_id]
        fam = classify_hue_family(float(L), float(a), float(b))
        family_regions.setdefault(fam, []).append(r_id)

    # 3. Tone quantization per hue family
    tone_names = ["dark", "mid", "light"]
    if params.tone_bands == 1:
        tone_names = ["all"]
    elif params.tone_bands == 2:
        tone_names = ["dark", "light"]
    elif params.tone_bands == 4:
        tone_names = ["deep", "dark", "mid", "light"]

    layer_num = 10
    sorted_families = sorted(family_regions.keys())

    for fam in sorted_families:
        r_ids = family_regions[fam]
        L_values = np.array([mean_labs[r, 0] for r in r_ids])

        # Quantile thresholds
        quantiles = np.linspace(0, 100, params.tone_bands + 1)
        threshs = np.percentile(L_values, quantiles)

        for r_id, L in zip(r_ids, L_values):
            # Find tone band index
            band_idx = 0
            for t_idx in range(params.tone_bands):
                if L <= threshs[t_idx + 1] or t_idx == params.tone_bands - 1:
                    band_idx = t_idx
                    break
            tone_str = tone_names[min(band_idx, len(tone_names) - 1)]
            layer_name = f"{layer_num:02d}-fill-{fam}-{tone_str}"
            region_layers[r_id] = layer_name

        layer_num += 5

    return region_layers
