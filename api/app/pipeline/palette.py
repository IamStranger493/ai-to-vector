import numpy as np
from skimage.color import rgb2lab
from sklearn.cluster import KMeans
from app.schemas import PaletteParams


def hex_to_rgb(hex_str: str) -> np.ndarray:
    hex_str = hex_str.lstrip("#")
    if len(hex_str) == 3:
        hex_str = "".join([c * 2 for c in hex_str])
    return np.array([int(hex_str[i:i+2], 16) for i in (0, 2, 4)], dtype=np.uint8)


def generate_palette(denoised_rgb: np.ndarray, params: PaletteParams) -> tuple[np.ndarray, np.ndarray]:
    """
    Extracts a CIE Lab palette using chroma-weighted k-means, and labels
    the image via a 5-bit RGB -> Lab LUT.
    Returns:
        labels0: (H, W) int32
        centroids_lab: (k, 3) float32
    """
    h, w, _ = denoised_rgb.shape
    total_pixels = h * w

    # 1. Convert denoised image to CIE Lab (float32)
    # rgb2lab expects values in [0, 1] or uint8 [0, 255]
    lab_img = rgb2lab(denoised_rgb).astype(np.float32)
    L = lab_img[:, :, 0].reshape(-1)
    a = lab_img[:, :, 1].reshape(-1)
    b = lab_img[:, :, 2].reshape(-1)

    # Chroma = sqrt(a^2 + b^2)
    chroma = np.sqrt(a * a + b * b)

    # 2. Build sample set: uniform grid of sample_size pixels, plus high-chroma pixels
    step = max(1, int(np.sqrt(total_pixels / max(1, params.sample_size))))
    grid_mask = np.zeros(total_pixels, dtype=bool)
    grid_indices = np.arange(0, total_pixels, step)
    grid_mask[grid_indices] = True

    # High chroma mask (> 18)
    high_chroma_mask = chroma > 18.0

    sample_mask = grid_mask | high_chroma_mask
    sample_indices = np.nonzero(sample_mask)[0]

    # Limit sample size if excessive
    max_samples = max(params.sample_size * 2, 100000)
    if len(sample_indices) > max_samples:
        rng = np.random.RandomState(0)
        sample_indices = rng.choice(sample_indices, size=max_samples, replace=False)

    sampled_L = L[sample_indices]
    sampled_a = a[sample_indices]
    sampled_b = b[sample_indices]
    sampled_chroma = chroma[sample_indices]
    X_samples = np.stack([sampled_L, sampled_a, sampled_b], axis=-1)

    # 3. Sample weights w = 1 + chroma / chroma_weight
    weights = 1.0 + (sampled_chroma / params.chroma_weight)

    # 4. Run k-means in Lab with k-means++ init and fixed random state
    k = min(params.k, len(X_samples))
    kmeans = KMeans(
        n_clusters=k,
        init="k-means++",
        n_init=4,
        random_state=0,
    )
    kmeans.fit(X_samples, sample_weight=weights)
    centroids_lab = kmeans.cluster_centers_.astype(np.float32)

    # 5. Handle user_palette if provided
    if params.user_palette and len(params.user_palette) > 0:
        user_rgbs = np.array([hex_to_rgb(h_str) for h_str in params.user_palette], dtype=np.uint8)
        user_labs = rgb2lab(user_rgbs.reshape(1, -1, 3)).reshape(-1, 3).astype(np.float32)
        # Remap each centroid to nearest user color
        dists = np.linalg.norm(centroids_lab[:, None, :] - user_labs[None, :, :], axis=2)
        nearest_idx = np.argmin(dists, axis=1)
        centroids_lab = user_labs[nearest_idx]

    # 6. Build 5-bit RGB -> Lab LUT (32,768 bins)
    # Bin indices 0..31 for each channel
    indices_5 = np.arange(32, dtype=np.uint8)
    r_5, g_5, b_5 = np.meshgrid(indices_5, indices_5, indices_5, indexing="ij")
    # Bin center in [0..255] RGB: (v_5 * 8) + 4
    lut_rgb = np.stack([(r_5 * 8 + 4), (g_5 * 8 + 4), (b_5 * 8 + 4)], axis=-1).reshape(-1, 3)
    lut_lab = rgb2lab(lut_rgb.reshape(1, -1, 3)).reshape(-1, 3).astype(np.float32)

    # Nearest centroid for each of the 32768 LUT entries
    # Compute dists: (32768, k)
    diff = lut_lab[:, None, :] - centroids_lab[None, :, :]
    lut_nearest = np.argmin(np.sum(diff * diff, axis=2), axis=1).astype(np.int32)

    # 7. Label every pixel with one table lookup
    r_img_5 = (denoised_rgb[:, :, 0] >> 3).astype(np.int32)
    g_img_5 = (denoised_rgb[:, :, 1] >> 3).astype(np.int32)
    b_img_5 = (denoised_rgb[:, :, 2] >> 3).astype(np.int32)
    lut_idx = (r_img_5 << 10) | (g_img_5 << 5) | b_img_5
    labels0 = lut_nearest[lut_idx]

    return labels0, centroids_lab
