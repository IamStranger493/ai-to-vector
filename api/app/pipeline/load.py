import io
from dataclasses import dataclass
from typing import Tuple
import numpy as np
from PIL import Image, ImageOps


@dataclass
class LoadedImage:
    original_rgb: np.ndarray        # H x W x 3 uint8 (working resolution)
    orig_width: int                 # Original image width in pixels
    orig_height: int                # Original image height in pixels
    working_width: int              # Working resolution width
    working_height: int             # Working resolution height
    scale: float                    # original_side / working_side


def load_image(image_bytes: bytes, working_max_side: int = 2000) -> LoadedImage:
    """Decodes image bytes, handles orientation, alpha compositing, and lanczos downscaling."""
    with Image.open(io.BytesIO(image_bytes)) as pil_img:
        # 1. Apply EXIF orientation
        pil_img = ImageOps.exif_transpose(pil_img)

        orig_w, orig_h = pil_img.size

        # 2. Composite onto white if alpha
        if pil_img.mode in ("RGBA", "LA") or (pil_img.mode == "P" and "transparency" in pil_img.info):
            rgba = pil_img.convert("RGBA")
            bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
            composite = Image.alpha_composite(bg, rgba)
            rgb_img = composite.convert("RGB")
        else:
            rgb_img = pil_img.convert("RGB")

        # 3. Resize if largest side exceeds working_max_side (never upscale)
        longest_side = max(orig_w, orig_h)
        if longest_side > working_max_side:
            scale_factor = working_max_side / float(longest_side)
            new_w = max(1, int(round(orig_w * scale_factor)))
            new_h = max(1, int(round(orig_h * scale_factor)))
            resized_img = rgb_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        else:
            resized_img = rgb_img

        working_w, working_h = resized_img.size
        scale = float(longest_side) / float(max(working_w, working_h))
        rgb_arr = np.array(resized_img, dtype=np.uint8)

        return LoadedImage(
            original_rgb=rgb_arr,
            orig_width=orig_w,
            orig_height=orig_h,
            working_width=working_w,
            working_height=working_h,
            scale=scale,
        )
