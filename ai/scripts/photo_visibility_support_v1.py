"""Support for the actual nonnegative AREA interpolation footprint.

Resizing an all-one float image can produce 0.99999994 with OpenCV's weight
rounding. Testing that result against 1-epsilon erases valid interior pixels.
Resize the OUTSIDE indicator instead: an all-zero footprint stays exactly zero.
No tolerance permits even a small positive contribution from outside the mask.
"""
import cv2
import numpy as np
from photo_resize_safety_v1 import validate_resize


def full_area_support(support, size_xy):
    if not isinstance(support, np.ndarray) or support.dtype != np.bool_ or support.ndim != 2:
        raise ValueError('boolean_2d_support_required')
    h, w = support.shape
    validate_resize(h, w, 1.)
    if (not isinstance(size_xy, (tuple, list)) or len(size_xy) != 2
            or any(type(v) is not int or v <= 0 for v in size_xy)
            or size_xy[0] > w or size_xy[1] > h):
        raise ValueError('positive_downsample_size_xy_required')
    outside = cv2.resize((~support).astype(np.float64), tuple(size_xy), interpolation=cv2.INTER_AREA)
    return outside == 0.
