"""Explain the frozen ridge gate without changing it or accepting human labels.

Ablations are diagnostic counterfactuals, not replacement acceptance rules.
Patch counts are overlapping measurements, not independent samples.
"""
from collections import Counter

import cv2
import numpy as np

from external_pitch_evidence import MIN_PATCHES
from highres_ridge_quality import RidgeQualityConfig, orientation_field
from photo_resize_safety_v1 import validate_resize


def validate(gray, support):
    if (not isinstance(gray, np.ndarray) or gray.dtype != np.uint8 or gray.ndim != 2
            or not isinstance(support, np.ndarray) or support.dtype != np.bool_
            or support.shape != gray.shape or not support.any()):
        raise ValueError('uint8_gray_and_nonempty_boolean_support_required')
    validate_resize(*gray.shape, 1.)


def audit_ridge_level(gray, support, max_side):
    """Reproduce V1 scalar decisions exactly and expose why each window fails."""
    validate(gray, support)
    if type(max_side) is not int or max_side <= 0:
        raise ValueError('positive_integer_max_side_required')
    h, w = gray.shape
    ratio = min(1., max_side / max(h, w))
    size = (max(1, round(w*ratio)), max(1, round(h*ratio)))
    small = cv2.resize(gray, size, interpolation=cv2.INTER_AREA)
    allowed = cv2.resize(support.astype(np.uint8), size, interpolation=cv2.INTER_NEAREST) > 0
    g = small.astype(np.float32)
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0); gy = cv2.Sobel(g, cv2.CV_32F, 0, 1)
    xx = cv2.GaussianBlur(gx*gx, (0, 0), 3); yy = cv2.GaussianBlur(gy*gy, (0, 0), 3)
    xy = cv2.GaussianBlur(gx*gy, (0, 0), 3)
    coherence = np.hypot(xx-yy, 2*xy)/(xx+yy+1e-6)
    window = np.outer(np.hanning(32), np.hanning(32))
    f = np.fft.fftfreq(32); radius = np.hypot(f[:, None], f[None, :])
    band = (radius >= .065) & (radius <= .30)
    metrics, combinations = [], Counter()
    names = ['contrast', 'coherence', 'radial_concentration', 'nonzero_energy']
    ablations = dict.fromkeys(names, 0)
    valid_count = eligible = all_windows = detrended_count = 0
    py, px = np.indices((32, 32), dtype=np.float64)
    px -= 15.5; py -= 15.5; plane_denominator = float((px*px).sum())
    for y in range(0, small.shape[0]-31, 16):
        for x in range(0, small.shape[1]-31, 16):
            all_windows += 1
            sl = np.s_[y:y+32, x:x+32]
            if allowed[sl].mean() < .8: continue
            eligible += 1
            patch = g[sl]; contrast = float(patch.std()); co = float(np.median(coherence[sl]))
            power = np.abs(np.fft.fft2((patch-patch.mean())*window))**2
            total = float(power.sum()); index = np.unravel_index(np.argmax(power*band), power.shape)
            frequency = float(radius[index])
            radial = float(power[(np.abs(radius-frequency) < .025) & band].sum()/max(total, 1e-6))
            passed = [contrast >= 8, co >= .45, radial >= .40, total > 0]
            valid_count += int(all(passed))
            # Isolate illumination leakage with exactly the same scalar gates.
            # This counterfactual does not alter the returned frozen status.
            residual = patch-patch.mean()-(patch*px).sum()/plane_denominator*px-(patch*py).sum()/plane_denominator*py
            dp = np.abs(np.fft.fft2(residual*window))**2
            dt = float(dp.sum()); di = np.unravel_index(np.argmax(dp*band), dp.shape)
            df = float(radius[di]); dr = float(dp[(np.abs(radius-df)<.025)&band].sum()/max(dt,1e-6))
            detrended_count += int(contrast >= 8 and co >= .45 and dr >= .40 and dt > 0)
            combinations['+'.join(n for n, p in zip(names, passed) if not p) or 'accepted'] += 1
            for i, name in enumerate(names):
                ablations[name] += int(all(p for j, p in enumerate(passed) if j != i))
            metrics.append([contrast, co, radial])
    quantiles = {name:np.percentile(np.asarray(metrics)[:, i], [10, 50, 90, 99]).tolist()
                 for i, name in enumerate(names[:3])} if metrics else {}
    return dict(version='frozen_ridge_gate_audit_v1', working_shape=list(small.shape),
                all_windows=all_windows, eligible_windows=eligible, credible_windows=valid_count,
                status='ridge_observed' if valid_count >= 4 else 'ridge_evidence_insufficient',
                failure_combinations=dict(combinations), quantiles_p10_p50_p90_p99=quantiles,
                planar_detrended_credible_windows=detrended_count,
                credible_windows_if_one_gate_removed=ablations,
                ablations_are_diagnostic_only=True, thresholds_unchanged=True)


def audit_pitch_sampling(gray, support):
    """Distinguish no usable geometry from failed periodicity; no pitch fallback."""
    validate(gray, support)
    _, coherence = orientation_field(gray, RidgeQualityConfig(tensor_sigma=5))
    grid = eligible = oriented = 0
    for y in range(80, gray.shape[0]-80, 64):
        for x in range(80, gray.shape[1]-80, 64):
            grid += 1
            region = np.s_[y-24:y+24, x-24:x+24]
            if support[region].mean() < .95: continue
            eligible += 1
            oriented += int(coherence[region].mean() >= .65)
    return dict(grid_centers=grid, mask_eligible_centers=eligible,
                orientation_pass_centers=oriented, required_accepted_patches=MIN_PATCHES,
                geometry_cannot_reach_required_patches=eligible < MIN_PATCHES,
                orientation_cannot_reach_required_patches=oriented < MIN_PATCHES,
                counts_are_upper_bounds_before_profile_checks=True,
                no_periodicity_is_not_absence=True)
