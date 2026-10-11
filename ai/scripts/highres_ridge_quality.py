from __future__ import annotations

from dataclasses import asdict, dataclass

import cv2

import numpy as np

from skimage.filters import threshold_sauvola

from skimage.morphology import skeletonize

from highres_skeleton_preview import build_skeleton, remove_small_components

from highres_skeleton_quality_review import diagnostics

@dataclass(frozen=True)
class RidgeQualityConfig:
    gradient_sigma: float = 0.8
    tensor_sigma: float = 3.0
    tangent_radius: int = 4
    tangent_sigma: float = 1.8
    blend_coherence_start: float = 0.4
    blend_coherence_full: float = 0.7
    sauvola_window: int = 31
    sauvola_k: float = 0.10
    min_ridge_area: int = 8
    contrast_window: int = 25
    spectral_patch: int = 32
    spectral_stride: int = 16
    min_ridge_period_px: float = 4.0
    max_ridge_period_px: float = 16.0
    min_contrast: float = 8.0
    min_coherence: float = 0.70
    min_band_energy: float = 0.70
    min_spectral_anisotropy: float = 0.70
    min_spectral_sharpness: float = 0.70
    max_tangent_disturbance: float = 0.22
    roi_guard_px: float = 16.0
    quality_guard_px: float = 6.0
    min_safe_fraction: float = 0.10
    min_quality_area: int = 256

REASONS = {"low_contrast": 1, "uncertain_orientation": 2,
           "weak_ridge_frequency_band": 4, "diffuse_spectral_direction": 8,
           "broad_radial_spectrum": 16, "tangent_variation": 32,
           "roi_edge": 64, "small_quality_component": 128}

def validate_config(c):
    for size in (c.sauvola_window, c.contrast_window):
        if not 3 <= size <= 511 or size % 2 != 1:
            raise ValueError("Local windows must be odd integers from 3 to 511.")
    if (not 16 <= c.spectral_patch <= 128 or c.spectral_patch % 2
            or not 1 <= c.spectral_stride <= c.spectral_patch // 2):
        raise ValueError("Require an even spectral patch and overlapping stride.")
    if not all(np.isfinite(value) for value in asdict(c).values()):
        raise ValueError("Parameters must be finite.")
    if min(c.gradient_sigma, c.tensor_sigma, c.tangent_sigma) <= 0 or not 1 <= c.tangent_radius <= 12:
        raise ValueError("Smoothing parameters must be positive and bounded.")
    if not 0 <= c.blend_coherence_start < c.blend_coherence_full <= 1:
        raise ValueError("Invalid orientation blend limits.")
    if not 2 < c.min_ridge_period_px < c.max_ridge_period_px <= c.spectral_patch:
        raise ValueError("Ridge period limits are invalid for the spectral patch.")
    for value in (c.sauvola_k, c.min_coherence, c.min_band_energy,
                  c.min_spectral_anisotropy, c.min_spectral_sharpness, c.min_safe_fraction):
        if not 0 < value <= 1:
            raise ValueError("Quality thresholds and Sauvola k must be in (0, 1].")
    if min(c.min_contrast, c.max_tangent_disturbance, c.roi_guard_px,
           c.quality_guard_px, c.min_ridge_area, c.min_quality_area) <= 0:
        raise ValueError("Area, contrast, disturbance and guard limits must be positive.")

def orientation_field(gray, c):
    src = cv2.GaussianBlur(gray.astype(np.float32), (0, 0), c.gradient_sigma)
    gx = cv2.Sobel(src, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(src, cv2.CV_32F, 0, 1, ksize=3)
    xx = cv2.GaussianBlur(gx * gx, (0, 0), c.tensor_sigma)
    yy = cv2.GaussianBlur(gy * gy, (0, 0), c.tensor_sigma)
    xy = cv2.GaussianBlur(gx * gy, (0, 0), c.tensor_sigma)
    coherence = np.clip(np.hypot(xx - yy, 2 * xy) / (xx + yy + 1e-6), 0, 1)
    # Dominant gradient points across ridges; rotate by pi/2 for ridge tangent.
    tangent = (0.5 * np.arctan2(2 * xy, xx - yy) + np.pi / 2) % np.pi
    return tangent.astype(np.float32), coherence.astype(np.float32)

def tangent_average(image, tangent, c):
    src = image.astype(np.float32)
    y, x = np.indices(src.shape, dtype=np.float32)
    result = np.zeros(src.shape, dtype=np.float32)
    total_weight = 0.0
    tx, ty = np.cos(tangent), np.sin(tangent)
    for offset in range(-c.tangent_radius, c.tangent_radius + 1):
        weight = float(np.exp(-0.5 * (offset / c.tangent_sigma) ** 2))
        sample = cv2.remap(src, x + offset * tx, y + offset * ty,
                           cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        result += weight * sample
        total_weight += weight
    return result / total_weight

def spectral_features(gray, c):
    """Overlapping Hann-window spectra; no filtering/max-response synthesis."""
    src = gray.astype(np.float32)
    height, width = src.shape
    n, half = c.spectral_patch, c.spectral_patch // 2
    padded = np.pad(src, half, mode="reflect")
    hann = np.outer(np.hanning(n), np.hanning(n)).astype(np.float32)
    fy, fx = np.meshgrid(np.fft.fftfreq(n), np.fft.fftfreq(n), indexing="ij")
    radius = np.hypot(fy, fx)
    angle = np.arctan2(fy, fx)
    band = (radius >= 1 / c.max_ridge_period_px) & (radius <= 1 / c.min_ridge_period_px)
    total_band = radius >= 1 / (1.5 * c.max_ridge_period_px)
    radial_index = np.rint(radius * n).astype(int)
    maps = np.zeros((height, width, 3), dtype=np.float32)
    weights = np.zeros((height, width), dtype=np.float32)
    # Nonzero floor gives image-edge pixels defined support in the overlap-add.
    spatial_weight = hann + 0.02
    centers_y = sorted(set(range(0, height, c.spectral_stride)) | {height - 1})
    centers_x = sorted(set(range(0, width, c.spectral_stride)) | {width - 1})
    for cy in centers_y:
        for cx in centers_x:
            patch = padded[cy:cy+n, cx:cx+n]
            mean = float((patch * hann).sum() / hann.sum())
            power = np.abs(np.fft.fft2((patch - mean) * hann)) ** 2
            band_energy = float(power[band].sum())
            energy_ratio = band_energy / max(float(power[total_band].sum()), 1e-6)
            anisotropy = np.hypot(
                (power[band] * np.cos(2 * angle[band])).sum(),
                (power[band] * np.sin(2 * angle[band])).sum(),
            ) / max(band_energy, 1e-6)
            radial = np.bincount(radial_index[band], weights=power[band], minlength=n)
            peak = int(radial.argmax())
            sharpness = float(radial[max(0, peak-1):peak+2].sum() / max(band_energy, 1e-6))
            y0, y1 = max(cy-half, 0), min(cy+half, height)
            x0, x1 = max(cx-half, 0), min(cx+half, width)
            support = spatial_weight[y0-cy+half:y1-cy+half, x0-cx+half:x1-cx+half]
            values = np.clip([energy_ratio, anisotropy, sharpness], 0, 1)
            maps[y0:y1, x0:x1] += support[..., None] * values
            weights[y0:y1, x0:x1] += support
    return np.clip(maps / np.maximum(weights[..., None], 1e-6), 0, 1)

def mask_distance(mask):
    return cv2.distanceTransform(np.pad(mask.astype(np.uint8), 1), cv2.DIST_L2, 5)[1:-1, 1:-1]

def quality_regions(gray, roi, tangent, coherence, c):
    src = gray.astype(np.float32)
    window = (c.contrast_window, c.contrast_window)
    mean = cv2.boxFilter(src, -1, window)
    contrast = np.sqrt(np.maximum(cv2.boxFilter(src * src, -1, window) - mean * mean, 0))
    disturbance = cv2.boxFilter(np.abs(src - tangent_average(src, tangent, c)), -1, window) / (contrast + 1)
    spectrum = spectral_features(gray, c)
    roi_distance = mask_distance(roi)
    checks = [(contrast < c.min_contrast, "low_contrast"),
              (coherence < c.min_coherence, "uncertain_orientation"),
              (spectrum[..., 0] < c.min_band_energy, "weak_ridge_frequency_band"),
              (spectrum[..., 1] < c.min_spectral_anisotropy, "diffuse_spectral_direction"),
              (spectrum[..., 2] < c.min_spectral_sharpness, "broad_radial_spectrum"),
              (disturbance > c.max_tangent_disturbance, "tangent_variation"),
              (roi_distance < c.roi_guard_px, "roi_edge")]
    reasons = np.zeros(gray.shape, dtype=np.uint8)
    for failed, name in checks:
        reasons[failed & roi] |= REASONS[name]
    accepted_raw = roi & (reasons == 0)
    reliable = remove_small_components(accepted_raw, c.min_quality_area)
    reasons[accepted_raw & ~reliable] |= REASONS["small_quality_component"]
    safe_mask = reliable & (mask_distance(reliable) >= c.quality_guard_px)
    classes = np.zeros(gray.shape, dtype=np.uint8)
    classes[roi] = 1  # Uncertain/review required, not necessarily damaged.
    classes[reliable] = 2  # Higher-confidence candidate region, not ground truth.
    # Feature product is only a display score. Decisions use individual gates.
    display_score = np.clip(coherence * spectrum[..., 0] * spectrum[..., 1] * spectrum[..., 2], 0, 1)
    return {"quality_classes": classes, "quality_reliable": reliable,
            "quality_uncertain": roi & ~reliable, "quality_safe": safe_mask,
            "quality_rejection_bits": reasons, "contrast": contrast,
            "coherence": coherence, "tangent_disturbance": disturbance,
            "band_energy": spectrum[..., 0], "spectral_anisotropy": spectrum[..., 1],
            "spectral_sharpness": spectrum[..., 2], "quality_display_score": display_score}

def build_ridge_quality(gray, config=RidgeQualityConfig()):
    validate_config(config)
    baseline, _ = build_skeleton(gray)
    tangent, coherence = orientation_field(gray, config)
    features = quality_regions(gray, baseline["roi"], tangent, coherence, config)
    aligned = tangent_average(baseline["normalized"], tangent, config)
    blend = np.clip((coherence - config.blend_coherence_start) /
                    (config.blend_coherence_full - config.blend_coherence_start), 0, 1)
    enhanced = np.rint(aligned * blend + baseline["normalized"] * (1 - blend)).astype(np.uint8)
    threshold = threshold_sauvola(enhanced, config.sauvola_window, config.sauvola_k, 127.5)
    raw_binary = (enhanced < threshold) & baseline["roi"]
    binary = remove_small_components(raw_binary, config.min_ridge_area)
    # Never thin a quality-clipped binary image: that would invent new endings.
    skeleton = skeletonize(binary, method="zhang")
    if not np.any(skeleton):
        raise ValueError("No refined ridge skeleton found.")
    if np.any(skeleton & ~binary) or np.any(binary & ~baseline["roi"]):
        raise RuntimeError("Refined ridge/skeleton support invariant failed.")
    before = diagnostics(baseline["binary"], baseline["skeleton"], baseline["roi"])
    after = diagnostics(binary, skeleton, baseline["roi"])
    if after["ridge_components"] != after["skeleton_components"] or after["euler_binary"] != after["euler_skeleton"]:
        raise RuntimeError("Thinning did not preserve refined binary topology.")
    roi_pixels = int(baseline["roi"].sum())
    safe_fraction = float(features["quality_safe"].sum() / roi_pixels)
    quality_status = "candidate_regions_available"
    if not features["quality_safe"].any():
        quality_status = "no_safe_region_requires_review"
    elif safe_fraction < config.min_safe_fraction:
        quality_status = "limited_safe_region_requires_review"
    stats = {"baseline": before, "refined": after,
             "roi_pixels": roi_pixels,
             "reliable_fraction_in_roi": float(features["quality_reliable"].sum() / roi_pixels),
             "safe_fraction_in_roi": safe_fraction,
             "uncertain_fraction_in_roi": float(features["quality_uncertain"].sum() / roi_pixels),
             "refined_ridge_fraction_in_roi": float(binary.sum() / roi_pixels),
             "reliable_skeleton_pixels": int((skeleton & features["quality_reliable"]).sum()),
             "safe_skeleton_pixels": int((skeleton & features["quality_safe"]).sum()),
             "rejection_reason_pixels": {
                 name: int(((features["quality_rejection_bits"] & bit) != 0).sum())
                 for name, bit in REASONS.items()},
             "quality_status": quality_status}
    stages = {"original": gray, "normalized": baseline["normalized"], "roi": baseline["roi"],
              "baseline_binary": baseline["binary"], "baseline_skeleton": baseline["skeleton"],
              "directional_enhanced": enhanced, "binary_raw": raw_binary, "binary": binary,
              "skeleton_full": skeleton, "skeleton_reliable_preview": skeleton & features["quality_reliable"],
              "skeleton_safe_preview": skeleton & features["quality_safe"], **features,
              "tangent_radians": tangent}
    return stages, stats
