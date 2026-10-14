"""Review-only pad proposals from fresh axial-row evidence, never protection.

All eligible terminal contexts retain ownership ambiguity, even when their
boundary is unobserved. No semantic-tip/frame heuristic confirms anatomy.
"""
import numpy as np
import photo_terminal_branch_candidates_v2 as branch
import photo_terminal_context_diagnostic_v1 as context
from finger_body_distal_estimator import validate_candidate_context_allocation
from photo_resize_safety_v1 import validate_resize

VERSION='photo_observed_boundary_proposals_v1_experimental'


def clip_native_axial_halfplane(support,affine,selected_row):
    """Native integer pixel centers: axial_y <= row; no second +.5 or round."""
    if (not isinstance(support,np.ndarray) or support.dtype!=np.bool_ or
            support.ndim!=2 or min(support.shape)<1):
        raise ValueError('boundary_proposal_support_contract_mismatch')
    height,width=support.shape;validate_resize(height,width,1.)
    matrix=np.asarray(affine)
    if (matrix.shape!=(3,3) or not np.issubdtype(matrix.dtype,np.number) or
            np.iscomplexobj(matrix) or not np.isfinite(matrix).all() or
            isinstance(selected_row,(bool,np.bool_)) or not isinstance(selected_row,(int,np.integer)) or
            selected_row<0):raise ValueError('boundary_proposal_affine_contract_mismatch')
    matrix=matrix.astype(np.float64)
    if not np.array_equal(matrix[2],[0,0,1]):raise ValueError('boundary_proposal_affine_contract_mismatch')
    try:
        with np.errstate(over='raise',invalid='raise'):
            determinant=np.linalg.det(matrix)
            corners=np.array([[0,0,1],[width-1,0,1],[0,height-1,1],[width-1,height-1,1.]])@matrix.T
    except FloatingPointError as error:
        raise ValueError('boundary_proposal_affine_numeric_overflow') from error
    if not np.isfinite(corners).all() or not np.isfinite(determinant) or determinant==0:
        raise ValueError('boundary_proposal_affine_contract_mismatch')
    # A row-sized temporary avoids allocating a native float-coordinate raster.
    result=np.zeros_like(support);x=np.arange(width,dtype=np.float64)
    for y in range(height):
        if support[y].any():
            axial_y=matrix[1,0]*x+matrix[1,1]*y+matrix[1,2]
            result[y]=support[y]&(axial_y<=selected_row)
    return result


def propose(rgb,body,tip):
    """Fresh source RGB evidence only. None means no observed pad proposal."""
    report=context.diagnose(rgb,body,tip) # validates/preflights before pixel hashes
    before=[context._pixel_sha(a) for a in [rgb,body,tip]]
    parents=branch.estimate(body,tip)
    if context._pixel_sha(parents['mask'])!=report['pad_mask_pixel_sha256']:
        raise ValueError('boundary_proposal_parent_identity_mismatch')
    valid_count=len(report['rows'])
    # Include base retained masks, optional proposals and streaming contexts.
    validate_candidate_context_allocation(*body.shape,len(parents['regions'])+valid_count+2)
    seen=np.zeros_like(body);ambiguous=np.zeros_like(body)
    for _,support in context._contexts(body,parents):
        ambiguous|=seen&support;seen|=support
    del seen
    evidence_by_id={r['candidate_id']:r for r in report['rows']}
    rows=[];combined=np.zeros_like(body)
    for parent,support in context._contexts(body,parents):
        diagnostic=evidence_by_id[parent['candidate_id']];boundary=diagnostic['boundary']
        row=dict(candidate_id=parent['candidate_id'],mask=None,
            parent_mask_pixel_sha256=context._pixel_sha(parent['mask']),
            parent_mask_pixels=int(parent['mask'].sum()),
            semantic_tip_overlap_pixels=parent['semantic_tip_overlap_pixels'],
            anatomy_classification='unknown',frame=diagnostic['pad_frame'],
            boundary_status=boundary['status'],reject_reason=boundary.get('reason'),
            full_context_ambiguous_pixels=int((support&ambiguous).sum()))
        if boundary['status']=='observed':
            unique=support&~ambiguous
            mask=clip_native_axial_halfplane(unique,
                boundary['mapping']['encoded_source_to_axial_affine'],boundary['evidence']['selected_row'])
            if mask.any():
                if np.any(mask&combined):raise RuntimeError('boundary_proposal_ownership_overlap')
                combined|=mask
                row.update(mask=mask,reject_reason=None,mask_pixels=int(mask.sum()),
                    mask_pixel_sha256=context._pixel_sha(mask),
                    selected_axial_row=boundary['evidence']['selected_row'],
                    boundary_mapping=boundary['mapping'],
                    boundary_semantics='constant selected axial-row transect, not fitted crease or anatomical boundary',
                    pixels_added_to_parent=int((mask&~parent['mask']).sum()),
                    pixels_removed_from_parent=int((parent['mask']&~mask).sum()))
            else:row['reject_reason']='observed_boundary_unique_support_empty'
        rows.append(row)
    if before!=[context._pixel_sha(a) for a in [rgb,body,tip]]:
        raise RuntimeError('boundary_proposal_source_mutated')
    return dict(schema_version=VERSION,mask=combined,regions=rows,
        parent_union_pixel_sha256=report['pad_mask_pixel_sha256'],
        ambiguous_full_context_pixels=int(ambiguous.sum()),
        ownership_policy='all eligible contexts participate; overlapping pixels unowned before boundary selection',
        unobserved_boundary_policy='no proposal; no geometry fallback',
        input_pixel_sha256=dict(zip(['RGB','body','tip'],before)),
        coordinate_system='encoded_source_pixels',anatomy_classification='unknown',
        semantic_tip_used_for_selection=False,frame_used_for_selection=False,
        approved_for_use=False,renderer_binding_allowed=False,protection_applied=False,
        default_pipeline_changed=False)
