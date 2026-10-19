"""Separated raw-profile confirmation; an uncalibrated diagnostic, not a gate.

Two strips span a quarter of a patch rather than four pixels. A bounded lag
accounts for FFT-bin direction error; it cannot jump to the next ridge cycle.
The whole-ring axial gate is not used: a crossing crease need not erase a
different, locally supported ridge direction. No labels or human boxes enter.
"""
import cv2
import numpy as np

from photo_visibility_peak_train_probe_v4 import CONFIG, peak_train
from photo_visibility_peak_train_probe_v5 import _probe_level


def bounded_agreement(left, right, period, separation, window):
    """Raw residual correlation with <1/4 cycle and FFT-bin geometric bounds."""
    # Half-bin uncertainty per Fourier axis gives <=sqrt(2)/(2*n*f)
    # angular error. Convert it to a normal displacement across the strips.
    bound = min(period/4., separation*period/(np.sqrt(2.)*window))
    max_lag = max(0, int(np.floor(bound)))
    best = (-1., 0)
    for lag in sorted(range(-max_lag, max_lag+1), key=lambda x: (abs(x), x)):
        a, b = (left[lag:], right[:-lag]) if lag > 0 else ((left[:lag], right[-lag:]) if lag < 0 else (left, right))
        a = a-a.mean(); b = b-b.mean()
        correlation = float(np.clip(a@b/max(np.linalg.norm(a)*np.linalg.norm(b), 1e-12), -1., 1.))
        if correlation > best[0]:
            best = (correlation, lag)
    return dict(correlation=best[0], lag_pixels=best[1], max_lag_pixels=max_lag,
                common_length=len(left)-abs(best[1]))


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
        u = np.arange(n-8, dtype=np.float32)-(n-9)/2
        profiles = []
        for offset in (-n/8., n/8.):
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
        if len(profiles) != 2:
            failed = 'separated_raw_peak_trains'; continue
        periods = [r['period_pixels'] for r in profiles]
        if (max(periods)-min(periods))/max(periods) > CONFIG.max_period_disagreement:
            failed = 'profile_period_disagreement'; continue
        agreement = bounded_agreement(profiles[0]['residual'], profiles[1]['residual'], 1./f, n/4., n)
        if agreement['correlation'] < CONFIG.min_strip_agreement:
            failed = 'separated_profile_disagreement'; continue
        ring = band & (np.abs(radius-f) < 1./n)
        angles = np.arctan2(fy[ring], fx[ring]); weights = power[ring]
        axial = float(abs(np.sum(weights*np.exp(2j*angles)))/max(float(weights.sum()), 1e-12))
        return dict(working_period_pixels=float(np.mean(periods)), normal_angle_radians=theta,
                    ring_axial=axial, ring_axial_used_as_gate=False, raw_strip_offsets=[-n/8., n/8.],
                    strip_agreement=agreement['correlation'], alignment=agreement,
                    profiles=[{k:v for k,v in r.items() if k != 'residual'} for r in profiles]), 'accepted'
    return None, failed


def probe_level(gray, support, max_side):
    result = _probe_level(gray, support, max_side, inspect_patch, 'photo_visibility_separated_probe_v7')
    result['config'].pop('min_ring_axial')
    result['config'].update(raw_strip_offset_fraction=.125, ring_axial_used_as_gate=False,
                            bounded_lag='floor(min(period/4,separation*period/(sqrt(2)*window)))')
    return result
