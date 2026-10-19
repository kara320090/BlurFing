"""Joint raw ridge witnesses, for uncalibrated development diagnostics only.

Two individually periodic strips with merely overlapping intervals do not prove
that the same four crests were seen. Match consecutive crests in both strips,
and calculate agreement only over their shared train. No human labels enter.
"""
import cv2
import numpy as np
from scipy import ndimage, signal

from photo_visibility_peak_train_probe_v4 import CONFIG
from photo_visibility_peak_train_probe_v5 import _probe_level


def raw_extrema(profile, period):
    raw = np.asarray(profile, dtype=np.float64)
    residual = raw - ndimage.gaussian_filter1d(raw, period * 1.5, mode='reflect')
    residual = ndimage.gaussian_filter1d(residual, .5, mode='reflect')
    std = float(residual.std())
    if std * std <= 2. / 12.:
        return None
    prominence = max(2 * np.sqrt(1. / 12.), CONFIG.prominence_std_fraction * std)
    distance = max(2, int(np.floor(period * .5)))
    smooth = ndimage.gaussian_filter1d(raw, .5, mode='reflect')
    peaks, _ = signal.find_peaks(smooth, prominence=prominence, distance=distance)
    troughs, _ = signal.find_peaks(-smooth, prominence=prominence, distance=distance)
    return peaks, troughs, residual


def joint_train(left, right, period):
    """Same consecutive cycles on disjoint strips, no skipped crests or phase wrap."""
    evidence = [raw_extrema(p, period) for p in (left, right)]
    if any(e is None for e in evidence):
        return None
    pa, ta, ra = evidence[0]; pb, tb, rb = evidence[1]
    # A quarter period is the phase bound, not a fitted visibility threshold.
    # Larger displacements can match a different ridge rather than the same one.
    bound = period / 4.
    for count in range(min(len(pa), len(pb)), CONFIG.min_peaks - 1, -1):
        for ia in range(len(pa) - count + 1):
            a = pa[ia:ia + count]
            for ib in range(len(pb) - count + 1):
                b = pb[ib:ib + count]
                if np.max(np.abs(a - b)) > bound:
                    continue
                records = []
                for run, troughs, total in ((a, ta, len(pa)), (b, tb, len(pb))):
                    gaps = np.diff(run)
                    pitch = float(np.median(gaps)); cv = float(gaps.std() / gaps.mean())
                    if (abs(pitch - period) / period > CONFIG.max_period_disagreement
                            or cv > CONFIG.max_spacing_cv
                            or any(not np.any((troughs > p) & (troughs < q)) for p, q in zip(run[:-1], run[1:]))):
                        break
                    records.append(dict(period_pixels=pitch, peak_count=count, spacing_cv=cv,
                                        run_start=int(run[0]), run_end=int(run[-1]),
                                        crest_positions=run.tolist(), total_profile_peaks=total,
                                        extrema_witness='smoothed_undetrended_intensity'))
                if len(records) != 2:
                    continue
                periods = [r['period_pixels'] for r in records]
                if (max(periods) - min(periods)) / max(periods) > CONFIG.max_period_disagreement:
                    continue
                start = int(max(a[0], b[0])); end = int(min(a[-1], b[-1]))
                if end <= start:
                    continue
                x, y = ra[start:end + 1], rb[start:end + 1]
                x = x - x.mean(); y = y - y.mean()
                corr = float(np.clip(x @ y / max(np.linalg.norm(x) * np.linalg.norm(y), 1e-12), -1., 1.))
                if corr < CONFIG.min_strip_agreement:
                    continue
                return dict(working_period_pixels=float(np.mean(periods)), strip_agreement=corr,
                            common_run_span=[start, end], matched_crest_count=count,
                            max_crest_displacement=float(np.max(np.abs(a - b))),
                            max_phase_displacement_pixels=bound, profiles=records)
    return None


def proposals(patch, geometry):
    n = patch.shape[0]; hann, fx, fy, radius, band = geometry
    residual = patch - cv2.GaussianBlur(patch, (0, 0), n / 8, borderType=cv2.BORDER_REFLECT_101)
    if float(np.mean(residual ** 2)) <= 2. / 12.:
        return []
    power = np.abs(np.fft.fft2(residual * hann)) ** 2
    floor = max(float(np.median(power[band])), np.finfo(float).eps * max(float(power.sum()), 1.))
    found = []; vectors = []
    for index in np.argsort(np.where(band, power, -1).ravel())[::-1]:
        pos = np.unravel_index(index, power.shape)
        if not band[pos] or power[pos] / floor < CONFIG.min_peak_to_noise:
            break
        vector = np.array([fx[pos], fy[pos]])
        if any(min(np.linalg.norm(vector - v), np.linalg.norm(vector + v)) <= 1. / n for v in vectors):
            continue
        f = float(radius[pos]); ring = band & (np.abs(radius - f) < 1. / n)
        angles = np.arctan2(fy[ring], fx[ring]); weights = power[ring]
        axial = float(abs(np.sum(weights * np.exp(2j * angles))) / max(float(weights.sum()), 1e-12))
        found.append((1. / f, float(np.arctan2(vector[1], vector[0])), axial))
        vectors.append(vector)
        if len(found) == CONFIG.max_hypotheses:
            break
    return found


def raw_strips(patch, theta):
    n = patch.shape[0]
    u = np.arange(n - 8, dtype=np.float32) - (n - 9) / 2
    strips = []
    for offset in (-2., 2.):
        v = np.array([offset - 1, offset, offset + 1], np.float32)[:, None]
        mx = (n - 1) / 2 + u[None, :] * np.cos(theta) - v * np.sin(theta)
        my = (n - 1) / 2 + u[None, :] * np.sin(theta) + v * np.cos(theta)
        if min(mx.min(), my.min()) < 0 or max(mx.max(), my.max()) > n - 1:
            raise ValueError('raw_strip_outside_validated_patch')
        strips.append(cv2.remap(patch.astype(np.float32), mx.astype(np.float32), my.astype(np.float32),
                                interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT).mean(axis=0))
    return strips


def inspect_patch(patch, geometry):
    reason = 'spectral_direction'
    for period, theta, axial in proposals(patch, geometry):
        if axial < CONFIG.min_ring_axial:
            continue
        reason = 'joint_raw_train'
        result = joint_train(*raw_strips(patch, theta), period)
        if result is not None:
            return dict(**result, normal_angle_radians=theta, ring_axial=axial), 'accepted'
    return None, reason


def probe_level(gray, support, max_side):
    result = _probe_level(gray, support, max_side, inspect_patch, 'photo_visibility_joint_witness_v11')
    result['config'].update(raw_train_selection='matched_consecutive_raw_crests', correlation_scope='shared_train')
    return result
