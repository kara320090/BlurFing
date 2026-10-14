"""Experimental axis-aware observation, separate from the frozen width gate.

The caller must supply the finger axis in the current image's y/x coordinates.
Existing color/width/IQR criteria are retained; this is not a production width
estimator and is not installed into the renderer or structure checker.
"""
import cv2
import numpy as np
from protect_rgb_fingerprint import validate_roi

VERSION = 'contactless_finger_width_axis_v1_experimental'


def estimate_finger_width_axis(rgb, box, axis_yx):
    rgb, box = validate_roi(rgb, box)
    axis = np.asarray(axis_yx, dtype=np.float64)
    if axis.shape != (2,) or not np.isfinite(axis).all():
        raise ValueError('finite_axis_yx_required')
    length = float(np.linalg.norm(axis))
    if not np.isfinite(length) or length == 0:
        raise ValueError('nonzero_finite_axis_required')
    axis = axis / length
    normal = np.array([-axis[1], axis[0]])
    x0, y0, x1, y1 = box
    center = np.array([(y0+y1)//2, (x0+x1)//2], np.float64)
    cy, cx = center.astype(int)
    seed = rgb[max(0,cy-20):min(rgb.shape[0],cy+21),
               max(0,cx-20):min(rgb.shape[1],cx+21)]
    saturation = float(np.median(cv2.cvtColor(seed, cv2.COLOR_RGB2HSV)[:,:,1]))
    threshold = max(12.0, saturation * .5)
    samples, rejected_samples = [], []
    for offset in range(-90, 91, 30):
        row_center = center + offset * axis
        if not (0 <= row_center[0] < rgb.shape[0] and 0 <= row_center[1] < rgb.shape[1]):
            rejected_samples.append(dict(axis_offset=offset, reason='row_center_outside_image'))
            continue
        distances = np.arange(-600, 600, dtype=np.float64)
        points = row_center + distances[:,None] * normal
        valid = ((points[:,0] >= 0) & (points[:,0] <= rgb.shape[0]-1)
                 & (points[:,1] >= 0) & (points[:,1] <= rgb.shape[1]-1))
        points, distances = points[valid], distances[valid]
        if not len(points):
            rejected_samples.append(dict(axis_offset=offset, reason='no_in_bounds_samples'))
            continue
        row = cv2.remap(rgb, points[:,1].astype(np.float32)[None],
                       points[:,0].astype(np.float32)[None], cv2.INTER_LINEAR,
                       borderMode=cv2.BORDER_CONSTANT)[0]
        hsv = cv2.cvtColor(row[None], cv2.COLOR_RGB2HSV)[0]
        skin = ((hsv[:,1] >= threshold) & (row[:,0].astype(int)-row[:,1].astype(int) >= 2)
                & (hsv[:,2] > 30))
        skin = cv2.morphologyEx(skin.astype(np.uint8)[None], cv2.MORPH_CLOSE,
                               np.ones((1,9),np.uint8))[0] > 0
        index = int(np.argmin(np.abs(distances)))
        if not skin[index]:
            nearby = np.flatnonzero(skin & (np.abs(distances) <= 20))
            if not len(nearby):
                rejected_samples.append(dict(axis_offset=offset, reason='no_skin_near_seed_center'))
                continue
            index = int(nearby[np.argmin(np.abs(distances[nearby]))])
        left, right = index, index+1
        while left > 0 and skin[left-1]:left -= 1
        while right < len(skin) and skin[right]:right += 1
        observed = right-left
        if left == 0 or right == len(skin) or not 160 <= observed <= 900:
            rejected_samples.append(dict(axis_offset=offset, width=observed,
                reason='skin_interval_touches_sample_boundary' if left == 0 or right == len(skin)
                       else 'width_outside_existing_range'))
            continue
        samples.append(dict(axis_offset=offset, width=observed,
                            start_yx=points[left].tolist(), end_yx=points[right-1].tolist()))
    info = dict(version=VERSION, axis_yx=axis.tolist(), samples=samples, rejected_samples=rejected_samples,
                seed_saturation=saturation, saturation_threshold=threshold,
                coordinate_system='caller_current_image_pixels',
                physical_dpi_known=False, default_pipeline_enabled=False,
                thresholds_changed=False)
    if len(samples) < 5:
        return info | dict(status='insufficient_boundary_rows', width=None)
    widths = np.array([sample['width'] for sample in samples])
    median = float(np.median(widths))
    iqr = float(np.percentile(widths,75)-np.percentile(widths,25))
    return info | dict(status='estimated' if iqr/median <= .25 else 'unstable_boundary_width',
                       width=median, width_iqr=iqr, relative_iqr=iqr/median)
