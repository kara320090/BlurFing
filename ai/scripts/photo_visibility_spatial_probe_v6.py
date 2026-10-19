"""Four-strip spatial confirmation instead of a global ring direction gate.

Crossing creases spread spectral directions even when narrow ridge trains remain
locally visible. FFT only proposes candidates; four separated raw profiles must
confirm each. No human boxes or labels, and no calibrated visibility decision.
"""
import cv2
import numpy as np
from photo_visibility_peak_train_probe_v4 import CONFIG, peak_train
from photo_visibility_peak_train_probe_v5 import _probe_level

OFFSETS = (-6., -2., 2., 6.)


def inspect_patch(patch, geometry):
    n = patch.shape[0]; hann, fx, fy, radius, band = geometry
    residual = patch-cv2.GaussianBlur(patch, (0, 0), n/8, borderType=cv2.BORDER_REFLECT_101)
    if float(np.mean(residual**2)) <= 2./12.:
        return None, 'quantization_floor'
    power = np.abs(np.fft.fft2(residual*hann))**2
    floor = max(float(np.median(power[band])), np.finfo(float).eps*max(float(power.sum()), 1.))
    candidates = []
    for index in np.argsort(np.where(band, power, -1).ravel())[::-1]:
        pos = np.unravel_index(index, power.shape)
        if not band[pos] or power[pos]/floor < CONFIG.min_peak_to_noise:
            break
        vector = np.array([fx[pos], fy[pos]])
        if any(min(np.linalg.norm(vector-v), np.linalg.norm(vector+v)) <= 1./n for _, v in candidates):
            continue
        candidates.append((pos, vector))
        if len(candidates) == CONFIG.max_hypotheses:
            break
    failed = 'spectral_proposal'
    for pos, vector in candidates:
        f = float(radius[pos]); theta = float(np.arctan2(vector[1], vector[0]))
        length = n-8; u = np.arange(length, dtype=np.float32)-(length-1)/2
        profiles = []
        for offset in OFFSETS:
            v = np.array([offset-1, offset, offset+1], dtype=np.float32)[:, None]
            mx = (n-1)/2+u[None, :]*np.cos(theta)-v*np.sin(theta)
            my = (n-1)/2+u[None, :]*np.sin(theta)+v*np.cos(theta)
            if mx.min() < 0 or my.min() < 0 or mx.max() > n-1 or my.max() > n-1:
                raise ValueError('profile_left_validated_patch')
            values = cv2.remap(patch.astype(np.float32), mx.astype(np.float32), my.astype(np.float32),
                               interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
            result = peak_train(values.mean(axis=0), 1./f)
            if result is None:
                break
            profiles.append(result)
        if len(profiles) != len(OFFSETS):
            failed = 'four_raw_peak_trains'; continue
        periods = [r['period_pixels'] for r in profiles]
        if (max(periods)-min(periods))/max(periods) > CONFIG.max_period_disagreement:
            failed = 'profile_period_disagreement'; continue
        correlations = []
        for left, right in zip(profiles[:-1], profiles[1:]):
            a = left['residual']-left['residual'].mean(); b = right['residual']-right['residual'].mean()
            correlations.append(float(np.clip(a@b/max(np.linalg.norm(a)*np.linalg.norm(b), 1e-12), -1., 1.)))
        if min(correlations) < CONFIG.min_strip_agreement:
            failed = 'spatial_profile_disagreement'; continue
        ring = band & (np.abs(radius-f) < 1./n)
        angles = np.arctan2(fy[ring], fx[ring]); weights = power[ring]
        axial = float(abs(np.sum(weights*np.exp(2j*angles)))/max(float(weights.sum()), 1e-12))
        return dict(working_period_pixels=float(np.mean(periods)), normal_angle_radians=theta,
                    ring_axial=axial, ring_axial_used_as_gate=False,
                    strip_agreement=min(correlations), adjacent_strip_agreements=correlations,
                    profiles=[{k:v for k,v in r.items() if k != 'residual'} for r in profiles]), 'accepted'
    return None, failed


def probe_level(gray, support, max_side):
    result = _probe_level(gray, support, max_side, inspect_patch, 'photo_visibility_spatial_probe_v6')
    result['config'].pop('min_ring_axial')
    result['config'].update(raw_strip_offsets=list(OFFSETS), ring_axial_used_as_gate=False)
    return result
