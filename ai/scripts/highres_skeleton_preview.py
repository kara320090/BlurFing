from __future__ import annotations

from dataclasses import dataclass

import cv2

import numpy as np

from scipy.ndimage import binary_fill_holes

from skimage.filters import threshold_sauvola

from skimage.morphology import skeletonize

@dataclass(frozen=True)
class SkeletonConfig:
    clahe_clip: float = 2.0
    clahe_tiles: int = 8
    sauvola_window: int = 31
    sauvola_k: float = 0.15
    sauvola_r: float = 127.5  # Explicit 8-bit intensity scale.
    min_ridge_area: int = 8
    roi_window: int = 31
    roi_min_std: float = 5.0
    roi_max_mean: float = 250.0
    roi_close_size: int = 17
    roi_min_area: int = 512
    border_margin: int = 4

def validate_config(config: SkeletonConfig) -> None:
    for size in (config.sauvola_window, config.roi_window, config.roi_close_size):
        if size < 3 or size > 511 or size % 2 != 1:
            raise ValueError("Window/kernel sizes must be odd integers from 3 to 511.")
    values = (config.clahe_clip, config.sauvola_k, config.sauvola_r,
              config.roi_min_std, config.roi_max_mean)
    if not all(np.isfinite(value) for value in values):
        raise ValueError("Parameters must be finite.")
    if config.clahe_clip <= 0 or not 1 <= config.clahe_tiles <= 512:
        raise ValueError("CLAHE requires a positive clip limit and valid tile count.")
    if not 0 <= config.sauvola_k <= 1 or config.sauvola_r <= 0:
        raise ValueError("Sauvola requires 0 <= k <= 1 and r > 0.")
    if config.min_ridge_area < 1 or config.roi_min_area < 1:
        raise ValueError("Component area limits must be positive.")
    if config.roi_min_std <= 0 or not 0 < config.roi_max_mean <= 255:
        raise ValueError("ROI contrast/brightness limits are invalid.")
    if not 0 <= config.border_margin < 256:
        raise ValueError("Border margin must be from 0 to 255.")

def component_areas(mask: np.ndarray) -> np.ndarray:
    _, _, stats, _ = cv2.connectedComponentsWithStats(
        mask.astype(np.uint8), connectivity=8
    )
    return stats[1:, cv2.CC_STAT_AREA]

def remove_small_components(mask: np.ndarray, min_area: int) -> np.ndarray:
    _, labels, stats, _ = cv2.connectedComponentsWithStats(
        mask.astype(np.uint8), connectivity=8
    )
    keep = stats[:, cv2.CC_STAT_AREA] >= min_area
    keep[0] = False
    return keep[labels]

def estimate_roi(gray: np.ndarray, config: SkeletonConfig) -> np.ndarray:
    """Heuristic support mask for this grayscale dataset, not an annotated ROI.

    Closing/hole filling apply ONLY to the support mask, never to ridge pixels.
    """
    src = gray.astype(np.float32)
    window = (config.roi_window, config.roi_window)
    mean = cv2.boxFilter(src, -1, window, borderType=cv2.BORDER_REFLECT)
    square_mean = cv2.boxFilter(src * src, -1, window, borderType=cv2.BORDER_REFLECT)
    std = np.sqrt(np.maximum(square_mean - mean * mean, 0))
    support = (std >= config.roi_min_std) & (mean <= config.roi_max_mean)
    kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, (config.roi_close_size, config.roi_close_size)
    )
    support = cv2.morphologyEx(support.astype(np.uint8), cv2.MORPH_CLOSE, kernel) > 0
    roi = binary_fill_holes(remove_small_components(support, config.roi_min_area))
    margin = config.border_margin
    if margin:
        roi[:margin, :] = roi[-margin:, :] = False
        roi[:, :margin] = roi[:, -margin:] = False
    return roi

def build_skeleton(gray: np.ndarray, config: SkeletonConfig = SkeletonConfig()):
    """Return full-resolution arrays plus descriptive QA statistics."""
    validate_config(config)
    if gray.dtype != np.uint8 or gray.shape != (512, 512):
        raise ValueError("Expected a uint8 grayscale array of shape (512, 512).")
    roi = estimate_roi(gray, config)
    if not np.any(roi):
        raise ValueError("No fingerprint ROI found; check image contrast and ROI parameters.")
    normalized = cv2.createCLAHE(
        clipLimit=config.clahe_clip,
        tileGridSize=(config.clahe_tiles, config.clahe_tiles),
    ).apply(gray)
    threshold = threshold_sauvola(
        normalized, window_size=config.sauvola_window,
        k=config.sauvola_k, r=config.sauvola_r,
    )
    raw_binary = (normalized < threshold) & roi  # Dark ridges are foreground.
    binary = remove_small_components(raw_binary, config.min_ridge_area)
    skeleton = skeletonize(binary, method="zhang")
    if not np.any(skeleton):
        raise ValueError("No ridge skeleton found; check threshold parameters.")
    if np.any(skeleton & ~binary) or np.any(binary & ~roi):
        raise RuntimeError("Skeleton/binary support invariant failed.")
    ridge_areas = component_areas(binary)
    skeleton_areas = component_areas(skeleton)
    stats = {
        "shape_hw": list(gray.shape),
        "roi_pixels": int(roi.sum()),
        "roi_fraction": float(roi.mean()),
        "ridge_pixels_before_cleanup": int(raw_binary.sum()),
        "ridge_pixels": int(binary.sum()),
        "removed_noise_pixels": int(raw_binary.sum() - binary.sum()),
        "ridge_fraction_in_roi": float(binary.sum() / roi.sum()),
        "ridge_components_8_connected": len(ridge_areas),
        "skeleton_pixels": int(skeleton.sum()),
        "skeleton_components_8_connected": len(skeleton_areas),
        "short_skeleton_components_lt_12px": int((skeleton_areas < 12).sum()),
        "largest_ridge_component_fraction": float(ridge_areas.max() / binary.sum()),
    }
    stages = {"original": gray, "normalized": normalized, "roi": roi,
              "binary_raw": raw_binary, "binary": binary, "skeleton": skeleton}
    return stages, stats
