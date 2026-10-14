"""Opt-in body-associated skin interval width; no production approval.

Requires a single associated native body mapped to the current image. Retains
the v1 color, row, width and IQR criteria. Semantic bounds cannot rescue a
cross-section touching the image/sampling boundary or missing RGB evidence.
"""
import cv2
import numpy as np
from protect_rgb_fingerprint import validate_roi

VERSION = 'contactless_finger_width_body_v1_experimental'


def estimate_finger_width_body(rgb, box, axis_yx, body_mask, *, image_shape=None):
    rgb, box = validate_roi(rgb, box)
    if (not isinstance(body_mask, np.ndarray) or body_mask.dtype != np.bool_
            or body_mask.shape != rgb.shape[:2] or not body_mask.any()):
        raise ValueError('nonempty_boolean_body_mask_matching_image_required')
    observed_shape = rgb.shape[:2] if image_shape is None else image_shape
    if (not isinstance(observed_shape, (list,tuple)) or len(observed_shape) != 2
            or any(type(v) is not int or not 0 < v <= limit
                   for v,limit in zip(observed_shape,rgb.shape[:2]))):
        raise ValueError('valid_unpadded_image_shape_required')
    observed_height, observed_width = observed_shape
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
    if not (cy < observed_height and cx < observed_width and body_mask[cy, cx]):
        raise ValueError('body_seed_center_unavailable')
    seed = rgb[max(0,cy-20):min(rgb.shape[0],cy+21),
               max(0,cx-20):min(rgb.shape[1],cx+21)]
    saturation = float(np.median(cv2.cvtColor(seed, cv2.COLOR_RGB2HSV)[:,:,1]))
    threshold = max(12.0, saturation*.5)
    samples, rejected = [], []
    body_u8 = body_mask.astype(np.uint8)
    for offset in range(-90, 91, 30):
        row_center = center + offset*axis
        if not (0 <= row_center[0] < observed_height and 0 <= row_center[1] < observed_width):
            rejected.append(dict(axis_offset=offset, reason='row_center_outside_image'))
            continue
        distances = np.arange(-600, 600, dtype=np.float64)
        points = row_center + distances[:,None]*normal
        valid = ((points[:,0] >= 0) & (points[:,0] <= observed_height-1)
                 & (points[:,1] >= 0) & (points[:,1] <= observed_width-1))
        points, distances = points[valid], distances[valid]
        if not len(points):
            rejected.append(dict(axis_offset=offset, reason='no_in_bounds_samples'))
            continue
        mx = points[:,1].astype(np.float32)[None]
        my = points[:,0].astype(np.float32)[None]
        body = cv2.remap(body_u8, mx, my, cv2.INTER_NEAREST,
                         borderMode=cv2.BORDER_CONSTANT)[0] > 0
        index = int(np.argmin(np.abs(distances)))
        if not body[index]:
            rejected.append(dict(axis_offset=offset, reason='body_missing_at_row_center'))
            continue
        left, right = index, index+1
        while left > 0 and body[left-1]:left -= 1
        while right < len(body) and body[right]:right += 1
        if left == 0 or right == len(body):
            rejected.append(dict(axis_offset=offset, reason='body_interval_touches_sample_boundary',
                                 body_width=right-left))
            continue
        row = cv2.remap(rgb, mx, my, cv2.INTER_LINEAR,
                       borderMode=cv2.BORDER_CONSTANT)[0]
        hsv = cv2.cvtColor(row[None], cv2.COLOR_RGB2HSV)[0]
        skin = ((hsv[:,1] >= threshold) & (row[:,0].astype(int)-row[:,1].astype(int) >= 2)
                & (hsv[:,2] > 30))
        skin = cv2.morphologyEx(skin.astype(np.uint8)[None], cv2.MORPH_CLOSE,
                               np.ones((1,9), np.uint8))[0] > 0
        associated = skin & body
        if not associated[index]:
            nearby = np.flatnonzero(associated[left:right] & (np.abs(distances[left:right]) <= 20))
            if not len(nearby):
                rejected.append(dict(axis_offset=offset, reason='no_associated_skin_near_seed_center'))
                continue
            nearby += left
            index = int(nearby[np.argmin(np.abs(distances[nearby]))])
        a, b = index, index+1
        while a > left and associated[a-1]:a -= 1
        while b < right and associated[b]:b += 1
        observed = b-a
        if not 160 <= observed <= 900:
            rejected.append(dict(axis_offset=offset, reason='width_outside_existing_range', width=observed))
            continue
        samples.append(dict(axis_offset=offset, width=observed, body_width=right-left,
                            skin_interval_limited_by_body=bool(skin[left-1] or skin[right]),
                            start_yx=points[a].tolist(), end_yx=points[b-1].tolist()))
    info = dict(version=VERSION, axis_yx=axis.tolist(), samples=samples,
                rejected_samples=rejected, seed_saturation=saturation,
                saturation_threshold=threshold, coordinate_system='caller_current_image_pixels',
                width_semantics='contiguous RGB skin interval intersected with associated semantic body',
                observed_unpadded_image_shape=list(observed_shape),
                physical_dpi_known=False, default_pipeline_enabled=False, thresholds_changed=False)
    if len(samples) < 5:
        return info | dict(status='insufficient_boundary_rows', width=None)
    widths = np.array([row['width'] for row in samples])
    median = float(np.median(widths))
    iqr = float(np.percentile(widths,75)-np.percentile(widths,25))
    return info | dict(status='estimated' if iqr/median <= .25 else 'unstable_boundary_width',
                       width=median, width_iqr=iqr, relative_iqr=iqr/median)
