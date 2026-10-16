"""Conservative, optional enclosed-hole completion in each observed owner.

No dilation, convex hull, threshold change or bridging between owners. A hole
is geometric evidence only, not proof of a fingertip or joint boundary.
"""
import numpy as np
from scipy import ndimage
from finger_body_distal_estimator import estimate
from photo_candidate_context_v1 import candidate_contexts
from photo_native_owner_context_v1 import restore_contexts
from photo_resize_safety_v1 import validate_resize

VERSION = 'owner_enclosed_holes_v1_experimental'


def complete_owner_holes(base, coarse, body, tip, *, fill_holes=False):
    if type(fill_holes) is not bool:
        raise ValueError('fill_holes_flag_must_be_boolean')
    if (not isinstance(base, np.ndarray) or base.ndim != 2 or base.dtype != np.bool_ or
            min(base.shape) < 1 or any(not isinstance(a, np.ndarray) or a.dtype != np.bool_
            or a.shape != base.shape for a in (coarse, body, tip))):
        raise ValueError('owner_completion_mask_contract')
    validate_resize(*base.shape, 1.)
    if np.any((base | coarse | tip) & ~body):
        raise ValueError('owner_completion_outside_observed_body')
    estimated = estimate(body, tip, preserve_candidates=True)
    if not np.array_equal(coarse, estimated['mask']):
        raise ValueError('owner_completion_coarse_binding_mismatch')
    contexts = restore_contexts(candidate_contexts(estimated, body), body)
    output = base.copy()
    rows = []
    for context in contexts:
        owner, pad = context['body'], context['pad']
        seed = base & owner
        additions = np.zeros_like(base)
        if fill_holes and context['reject_reason'] is None and seed.any():
            y, x = np.where(owner)
            box = (slice(y.min(), y.max()+1), slice(x.min(), x.max()+1))
            # Explicit zero border and 4-connected background. Rotation by a
            # quarter turn preserves this pixel-topology convention. It is
            # not evidence of an anatomical boundary.
            local = np.pad(seed[box], 1)
            filled = ndimage.binary_fill_holes(local, structure=ndimage.generate_binary_structure(2, 1))[1:-1, 1:-1]
            additions[box] = filled & owner[box] & ~seed[box]
            output |= additions
        final = output & owner
        rows.append(dict(candidate_id=context['candidate_id'],
            estimator_reject_reason=context['reject_reason'],
            coarse_pixels=int(pad.sum()) if pad is not None else 0,
            before_pixels=int(seed.sum()), after_pixels=int(final.sum()),
            added_pixels=int(additions.sum()), fragments_before=ndimage.label(seed)[1],
            fragments_after=ndimage.label(final)[1],
            coarse_pixels_not_covered=int((pad & ~output).sum()) if pad is not None else None,
            candidate_has_no_protection=not bool(final.any()),
            engineering_evidence_score=context['parent'].get('confidence'),
            confidence_is_probability=False))
    if np.any(base & ~output) or np.any((output & ~base) & ~body):
        raise RuntimeError('owner_completion_preservation_failure')
    return output, dict(version=VERSION, enabled=fill_holes, candidates=rows,
        added_pixels=int((output & ~base).sum()), coarse_pixels_not_covered=int((coarse & ~output).sum()),
        semantic_tip_pixels_not_covered=int((tip & ~output).sum()),
        review_required=True, whole_photo_protection_verified=False,
        risk_measure='uncovered_model_proposals_are_not_ground_truth_missing_area',
        owner_boundaries_inferred=True, independent_validation_complete=False)
