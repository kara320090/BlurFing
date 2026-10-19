"""V4 evidence math with corrected AREA footprint support; diagnostic only."""
from dataclasses import asdict
from collections import Counter
import cv2
import numpy as np
from scipy import ndimage
from photo_visibility_gate_audit_v1 import validate
from photo_visibility_peak_train_probe_v4 import CONFIG, _geometry, inspect_patch
from photo_visibility_support_v1 import full_area_support


def probe_level(gray, support, max_side):
    return _probe_level(gray, support, max_side, inspect_patch, 'photo_visibility_peak_train_probe_v5')


def _probe_level(gray, support, max_side, inspector, version):
    validate(gray, support)
    if type(max_side) is not int or max_side <= 0:
        raise ValueError('positive_integer_max_side_required')
    h, w = gray.shape
    ratio = min(1., max_side / max(h, w))
    size = (max(1, round(w * ratio)), max(1, round(h * ratio)))
    small = cv2.resize(gray.astype(np.float64), size, interpolation=cv2.INTER_AREA)
    allowed = full_area_support(support, size)
    scales = []
    for n in CONFIG.windows:
        xs = list(range(0, size[0]-n+1, CONFIG.stride))
        ys = list(range(0, size[1]-n+1, CONFIG.stride))
        accepted = np.zeros((len(ys), len(xs)), bool)
        counts = Counter(); samples = []; geometry = _geometry(n)
        for iy, y in enumerate(ys):
            for ix, x in enumerate(xs):
                sl = np.s_[y:y+n, x:x+n]
                if not allowed[sl].all():
                    continue
                value, reason = inspector(small[sl], geometry)
                counts[reason] += 1
                if value is not None:
                    accepted[iy, ix] = True
                    samples.append(dict(working_xy=[x, y], window=n, **value))
        labels, count = ndimage.label(accepted, structure=np.ones((3, 3), np.uint8))
        sizes = np.bincount(labels.ravel(), minlength=count+1); sizes[0] = 0
        scales.append(dict(window=n, eligible_windows=sum(counts.values()), credible_windows=int(accepted.sum()),
                           largest_connected_windows=int(sizes.max()), reasons=dict(counts), samples=samples))
    return dict(version=version, config=asdict(CONFIG),
                working_shape=[size[1], size[0]], actual_resize_yx=[size[1]/h, size[0]/w], scales=scales,
                support_rule='zero_outside_AREA_contribution',
                candidate_signal_observed=any(s['largest_connected_windows'] >= CONFIG.min_connected_windows for s in scales),
                automatic_visibility='uncertain', calibrated_visibility_probability=None, used_by_protection=False,
                renderer_binding_allowed=False, absence_inferred_from_failure=False, support_is_visibility_GT=False)
