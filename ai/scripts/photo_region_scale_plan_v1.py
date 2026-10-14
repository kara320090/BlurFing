"""Experimental per-region allocation plan; not wired into default inference.

All native coarse components remain in the plan. A tiny fragment's resource
rejection cannot change another component's scale. No learned filtering, mask
cleanup, renderer, or reference substitution is performed here.
"""
import cv2
import numpy as np
from scipy import ndimage
from photo_resize_safety_v1 import validate_resize, ResizeSafetyError

VERSION = 'photo_region_scale_plan_v1_experimental'
NORMALIZED_WIDTH = 400.0  # Existing adapter width-normalization target.


def plan_region_scales(coarse_mask):
    if (not isinstance(coarse_mask, np.ndarray) or coarse_mask.dtype != np.bool_
            or coarse_mask.ndim != 2 or min(coarse_mask.shape) < 1):
        raise ValueError('nonempty_shape_boolean_coarse_mask_required')
    height, width = coarse_mask.shape
    labels, count = ndimage.label(coarse_mask)
    regions = []
    for component, slices in enumerate(ndimage.find_objects(labels), 1):
        y, x = slices
        local = (labels[slices] == component).astype(np.uint8)
        distance = cv2.distanceTransform(np.pad(local, 1), cv2.DIST_L2, 5)[1:-1, 1:-1]
        diameter = 2.0 * float(distance.max())
        scale = NORMALIZED_WIDTH / diameter
        region = dict(component=component, bbox=[x.start, y.start, x.stop, y.stop],
                      mask_pixels=int(local.sum()), observed_native_diameter=diameter,
                      working_scale=scale)
        try:
            shape, audit = validate_resize(height, width, scale)
            region.update(status='planned', working_shape=list(shape), resize_audit=audit,
                          reject_reason=None)
        except ResizeSafetyError as error:
            region.update(status='rejected', working_shape=None, resize_audit=error.audit,
                          reject_reason=error.reason)
        regions.append(region)
    return dict(version=VERSION, coordinate_system='encoded_original_pixels',
                detected_component_count=count, regions=regions,
                component_filtering=False, default_pipeline_enabled=False,
                PHOTO_DETECTOR_APPROVED=False, PHOTO_PROTECTION_PRODUCTION_READY=False)
