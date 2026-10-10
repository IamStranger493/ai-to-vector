import cv2
import numpy as np
from app.schemas import DenoiseParams


def denoise_image(rgb_img: np.ndarray, params: DenoiseParams) -> np.ndarray:
    """Applies edge-preserving smoothing (MeanShift or Bilateral) to reduce texture noise."""
    if not params.enabled:
        return rgb_img.copy()

    # OpenCV operates in BGR format
    bgr = cv2.cvtColor(rgb_img, cv2.COLOR_RGB2BGR)

    if params.method == "bilateral":
        filtered_bgr = cv2.bilateralFilter(
            bgr,
            d=0,
            sigmaColor=float(params.sr * 2),
            sigmaSpace=float(params.sp),
        )
    else:  # default meanshift
        # Mean shift filtering
        filtered_bgr = cv2.pyrMeanShiftFiltering(
            bgr,
            sp=params.sp,
            sr=params.sr,
        )

    filtered_rgb = cv2.cvtColor(filtered_bgr, cv2.COLOR_BGR2RGB)
    return filtered_rgb
