"""Explicit coarse completion only for an isolated, frame-truncated finger.

One estimator candidate must own the entire single native body component.
That body must touch the frame, with the coarse pad away from the frame. This
rejects ambiguous multi-finger unions, but is not proof of anatomical coverage.
The existing estimator, masks, numeric thresholds and learned pixels are kept.
"""
import numpy as np
from scipy import ndimage
from photo_coarse_cache_v31 import estimate
from photo_candidate_context_v1 import candidate_contexts
from photo_native_owner_context_v1 import restore_contexts
from photo_resize_safety_v1 import validate_resize
from photo_pitch_free_redaction_v1 import pixel_hash

VERSION='isolated_coarse_pad_completion_v1_experimental'


def complete_isolated_pad(learned,coarse,body,tip):
    if (not isinstance(learned,np.ndarray) or learned.ndim!=2 or learned.dtype!=np.bool_ or
            min(learned.shape)<1 or any(not isinstance(a,np.ndarray) or a.dtype!=np.bool_ or
            a.shape!=learned.shape for a in [coarse,body,tip])):
        raise ValueError('isolated_completion_mask_contract')
    validate_resize(*learned.shape,1.)
    if np.any((learned|coarse|tip)&~body):raise ValueError('isolated_completion_outside_observed_body')
    result=estimate(body,tip,preserve_candidates=True)
    if not np.array_equal(result['mask'],coarse):raise ValueError('isolated_completion_coarse_binding_mismatch')
    contexts=restore_contexts(candidate_contexts(result,body),body)
    _,body_count=ndimage.label(body)
    report=dict(version=VERSION,learned_pixels=int(learned.sum()),coarse_pad_pixels=int(coarse.sum()),
        added_pixels=0,result_pixels=int(learned.sum()),candidate_count=len(contexts),native_body_components=body_count,
        coarse_pad_pixel_sha256=pixel_hash(coarse),observed_body_pixel_sha256=pixel_hash(body),
        purpose='explicit_isolated_finger_completion',learned_pixels_preserved=True,
        geometric_candidate_not_joint_boundary=True,extra_skin_redaction_possible=True,
        missing_fingers_can_remain=True,anatomical_mask_coverage_verified=False,
        whole_photo_protection_verified=False,default_enabled=False)
    reason=None
    if len(contexts)!=1:reason='exactly_one_estimator_candidate_required'
    elif body_count!=1:reason='exactly_one_native_body_required'
    elif contexts[0]['reject_reason'] is not None:reason='valid_coarse_candidate_required'
    elif not np.array_equal(contexts[0]['body'],body):reason='complete_native_owner_required'
    else:
        body_frame=body[0].any() or body[-1].any() or body[:,0].any() or body[:,-1].any()
        pad_frame=coarse[0].any() or coarse[-1].any() or coarse[:,0].any() or coarse[:,-1].any()
        if not body_frame:reason='proximal_frame_cut_required'
        elif pad_frame:reason='distal_pad_touches_frame'
    if reason is not None:
        return learned.copy(),report|dict(status='unchanged_geometry_ineligible',reason=reason)
    output=learned|coarse
    report.update(status='isolated_coarse_added',reason=None,added_pixels=int((coarse&~learned).sum()),
        result_pixels=int(output.sum()))
    return output,report
