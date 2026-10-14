"""Native estimator ownership/scale contracts; no union-based candidate relabel."""
import re
import cv2
import numpy as np
from scipy import ndimage
from photo_region_scale_plan_v1 import NORMALIZED_WIDTH
from photo_resize_safety_v1 import validate_resize, ResizeSafetyError

VERSION = 'photo_candidate_context_v1_experimental'


def candidate_contexts(result, observed_body):
    """Validate all masks before rendering; overlapping owners are rejected.

    Disconnected pieces keep their estimator ID. Touching distinct owners stay
    distinct. Overlap is never assigned to a largest/first/last candidate.
    """
    shape = observed_body.shape
    if (observed_body.dtype != np.bool_ or observed_body.ndim != 2 or min(shape) < 1):
        raise ValueError('observed_body_contract_mismatch')
    union = result['mask']
    if (not isinstance(union, np.ndarray) or union.dtype != np.bool_ or
            union.shape != shape or np.any(union & ~observed_body)):
        raise ValueError('candidate_union_contract_mismatch')
    rows, identities = [], set()
    pad_union = np.zeros(shape, bool)
    pad_seen, pad_overlap = np.zeros(shape, bool), np.zeros(shape, bool)
    body_seen, body_overlap = np.zeros(shape, bool), np.zeros(shape, bool)
    for index, parent in enumerate(result['regions'], 1):
        identity = parent.get('candidate_id')
        if (not isinstance(identity, str) or
                re.fullmatch(r'body-[0-9]{4,}-part-[0-9]{4,}', identity) is None or identity in identities):
            raise ValueError('candidate_identity_contract_mismatch')
        identities.add(identity)
        body = parent.get('body_mask')
        pad = parent.get('mask')
        if (not isinstance(body, np.ndarray) or body.dtype != np.bool_ or body.shape != shape or
                parent.get('context_coordinate_system') != 'encoded_original_pixels' or
                np.any(body & ~observed_body)):
            raise ValueError('candidate_body_contract_mismatch')
        if parent.get('reject_reason') is None:
            if (not isinstance(pad, np.ndarray) or pad.dtype != np.bool_ or pad.shape != shape or
                    not pad.any() or np.any(pad & ~body)):
                raise ValueError('candidate_pad_contract_mismatch')
        elif pad is not None:
            raise ValueError('rejected_estimator_candidate_has_pad')
        body_overlap |= body_seen & body
        body_seen |= body
        if pad is not None:
            pad_overlap |= pad_seen & pad
            pad_seen |= pad
            pad_union |= pad
        rows.append(dict(candidate_id=identity, estimator_region_index=index,
                         parent=parent, pad=pad, body=body, reject_reason=parent.get('reject_reason')))
    if not np.array_equal(pad_union, union):
        raise ValueError('candidate_union_identity_loss')
    for row in rows:
        pad, body = row['pad'], row['body']
        if pad is not None and np.any(pad & pad_overlap):
            row['reject_reason'] = 'candidate_pad_ownership_overlap'
        elif np.any(body & body_overlap):
            row['reject_reason'] = 'candidate_body_ownership_overlap'
    return rows


def plan_candidate_scale(mask, component):
    """Use the maximum inscribed diameter of this candidate, including pieces.

    Same 400px normalization and allocation guard as region v1. Tiny separate
    candidates cannot change another plan; no fragment removal or scale clamp.
    """
    if (not isinstance(mask, np.ndarray) or mask.dtype != np.bool_ or mask.ndim != 2 or
            min(mask.shape) < 1 or not mask.any()):
        raise ValueError('nonempty_boolean_candidate_pad_required')
    y, x = np.where(mask)
    local = mask[y.min():y.max()+1, x.min():x.max()+1].astype(np.uint8)
    distance = cv2.distanceTransform(np.pad(local, 1), cv2.DIST_L2, 5)[1:-1, 1:-1]
    diameter = 2. * float(distance.max())
    scale = NORMALIZED_WIDTH / diameter
    _, fragments = ndimage.label(local)
    plan = dict(component=component, bbox=[int(x.min()), int(y.min()), int(x.max())+1, int(y.max())+1],
                mask_pixels=int(mask.sum()), native_fragment_count=fragments,
                observed_native_diameter=diameter, working_scale=scale,
                diameter_policy='max_inscribed_diameter_within_estimator_candidate',
                component_filtering=False)
    try:
        shape, audit = validate_resize(*mask.shape, scale)
        plan.update(status='planned', working_shape=list(shape), resize_audit=audit, reject_reason=None)
    except ResizeSafetyError as error:
        plan.update(status='rejected', working_shape=None, resize_audit=error.audit, reject_reason=error.reason)
    return plan
