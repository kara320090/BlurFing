"""Local raw gradient direction and joint crests; diagnostic, not a classifier.

Whole-patch Fourier rings mix directions of skin creases and fine ridges. V12
checks the gradient direction only in the actual jointly witnessed strip run.
The old 0.70 axial constant is reused, but this is a different statistic and
must be evaluated as a new experiment, not a calibrated equivalent gate.
"""
import cv2
import numpy as np
from photo_visibility_peak_train_probe_v4 import CONFIG
from photo_visibility_peak_train_probe_v5 import _probe_level
from photo_visibility_joint_witness_v11 import proposals, raw_strips, joint_train


def local_direction(patch, theta, span):
    n = patch.shape[0]; y, x = np.indices(patch.shape, dtype=float)
    x -= (n - 1) / 2; y -= (n - 1) / 2
    u = x * np.cos(theta) + y * np.sin(theta) + (n - 9) / 2
    v = -x * np.sin(theta) + y * np.cos(theta)
    # Footprint between and including the two three-pixel strips; derivatives
    # are computed on the original (lightly smoothed) intensity, not a bandpass.
    selected = (u >= span[0]) & (u <= span[1]) & (np.abs(v) <= 3.)
    smooth = cv2.GaussianBlur(patch.astype(np.float64), (0, 0), .5, borderType=cv2.BORDER_REFLECT_101)
    gy, gx = np.gradient(smooth)
    normal = gx * np.cos(theta) + gy * np.sin(theta)
    tangent = -gx * np.sin(theta) + gy * np.cos(theta)
    en = float(np.sum(normal[selected] ** 2)); et = float(np.sum(tangent[selected] ** 2))
    # Signed alignment: energy of a perpendicular crease cannot pass as a ridge.
    aligned = (en - et) / max(en + et, 1e-12)
    return dict(local_direction_alignment=aligned, direction_support_pixels=int(selected.sum()))


def inspect_patch(patch, geometry):
    reason = 'spectral_proposal'
    for period, theta, axial in proposals(patch, geometry):
        reason = 'joint_raw_train'
        result = joint_train(*raw_strips(patch, theta), period)
        if result is None:
            continue
        direction = local_direction(patch, theta, result['common_run_span'])
        if direction['local_direction_alignment'] < CONFIG.min_ring_axial:
            reason = 'local_direction'; continue
        return dict(**result, **direction, normal_angle_radians=theta, ring_axial=axial,
                    ring_axial_used_as_gate=False), 'accepted'
    return None, reason


def probe_level(gray, support, max_side):
    result = _probe_level(gray, support, max_side, inspect_patch, 'photo_visibility_local_direction_v12')
    result['config'].update(raw_train_selection='matched_consecutive_raw_crests', correlation_scope='shared_train',
                            ring_axial_used_as_gate=False, direction_statistic='signed_local_gradient_alignment')
    return result
