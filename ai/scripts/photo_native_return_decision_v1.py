"""Judge one fixed proposal after exact native RGB projection, never fake a pass.

Working evidence remains diagnostic. Final native evidence uses the unchanged
whole-permission predicate. This opt-in decision domain differs from V7/V11.
"""
import cv2,numpy as np
import photo_region_pipeline_v1 as shared
from photo_learned_pad_pipeline_v1 import pixel_hash
from photo_learned_pad_pipeline_v7 import working_views
from photo_region_pipeline_v3 import render_candidate_region
from photo_whole_region_structure_v1 import assess
from contactless_finger_width_body_v1 import estimate_finger_width_body

VERSION='native_return_structure_decision_v1_experimental'


def project_proposal(local,artifact,proposal):
    first,_,allowed=working_views(local,artifact)
    if (proposal.dtype!=np.uint8 or proposal.shape!=first.shape or
            not np.array_equal(proposal[~allowed],first[~allowed])):
        raise ValueError('native_proposal_working_RGB_contract')
    h,w=artifact['working_shape'];orientation=artifact['exif_orientation']
    upright=shared.orient(local,orientation)
    resized=cv2.resize(proposal[:h,:w],(upright.shape[1],upright.shape[0]),interpolation=cv2.INTER_CUBIC)
    projected=shared.orient(resized,orientation,inverse=True)
    native=local.copy();mask=artifact['coarse_mask'];native[mask]=projected[mask]
    if not np.array_equal(native[~mask],local[~mask]):raise ValueError('native_proposal_exterior_changed')
    return native


def render(local,artifact,axis):
    import transform_automatic_fingerprint_poc_v4 as frozen
    import fingerprint_structure_check as structure
    if len(artifact['regions'])!=1:raise ValueError('single_native_proposal_required')
    before=pixel_hash(local);first,body,permission=working_views(local,artifact)
    entry=artifact['regions'][0];scope=entry['working_scope'];seed=entry['working_seed'];captured=[]
    def uninspected(previous,report):
        if (previous.dtype!=np.uint8 or previous.shape!=local.shape or not np.array_equal(previous,local) or
                report.get('applied',False) is not False or report.get('transformation_function_passed',False) is not False or
                report.get('changed_pixels',0)!=0 or report.get('transformed_candidate_count',0)!=0 or
                report.get('transformed_pad_count',0)!=0 or any(r.get('applied',False) is not False for r in report['regions'])):
            raise ValueError('native_decision_uninspected_renderer_success')
        report.update(applied=False,transformation_function_passed=False,changed_pixels=0,
            transformed_candidate_count=0,transformed_pad_count=0,all_detected_candidates_transformed=False,
            returned_rgb_sha256=pixel_hash(local))
        return local.copy(),report
    def check(original,proposal,box):
        if captured or list(box)!=seed or not np.array_equal(original,first):
            raise ValueError('native_decision_working_source_contract')
        width=structure.estimate_finger_width(original,box)
        result=assess(original,proposal,scope,permission,width)
        if type(result.get('structure_change_passed')) is not bool:raise ValueError('native_decision_flag_contract')
        # Keep the REAL working decision; no synthetic pass enters frozen code.
        captured.append(dict(proposal=proposal.copy(),width=width,check=result))
        return result
    with shared.renderer_binding._LOCK:
        old=frozen.check_structure_change
        try:
            frozen.check_structure_change=check
            previous,report=render_candidate_region(local,artifact,axis)
        finally:frozen.check_structure_change=old
        if pixel_hash(local)!=before:raise ValueError('native_decision_source_changed')
        report.update(experimental_native_decision=VERSION,final_native_gate_authoritative=True,
            frozen_gate_equivalence=False,structure_checked_on_actual_native_return=False)
        if not captured:return uninspected(previous,report)
        evidence=captured[0];working_check=evidence['check'];region=report['regions'][0]
        region['working_renderer_structure_check']=working_check
        if working_check.get('reason') not in ['changed_structure_observed','insufficient_features','structure_change_not_demonstrated']:
            return uninspected(previous,report)
        candidate=project_proposal(local,artifact,evidence['proposal'])
        if working_check['structure_change_passed'] and not np.array_equal(candidate,previous):
            raise ValueError('native_decision_projection_disagrees_with_adapter')
        final,_,_=working_views(candidate,artifact)
        # Observation only: native exterior was checked before this restoration.
        final[~permission]=first[~permission]
        width=estimate_finger_width_body(first,seed,axis,body,image_shape=tuple(artifact['working_shape']))
        if width!=evidence['width']:raise ValueError('native_decision_original_width_mismatch')
        native_check=assess(first,final,scope,permission,width)
        if type(native_check.get('structure_change_passed')) is not bool:raise ValueError('native_decision_flag_contract')
        region['returned_RGB_structure_check']=native_check;region['structure_check']=native_check
        report.update(structure_checked_on_actual_native_return=True,reprojection_exterior_context_restored=True,
            proposal_count=1,proposal_seed_scale_or_renderer_retries=0,
            working_candidate_passed=working_check['structure_change_passed'],
            working_proposal_changed_pixels=int(np.any(evidence['proposal']!=first,axis=2).sum()))
        passed=native_check['structure_change_passed']
        returned=candidate if passed else local.copy()
        changed=int(np.any(returned!=local,axis=2).sum())
        if passed and changed==0:raise ValueError('native_decision_success_without_RGB_change')
        if pixel_hash(local)!=before:raise ValueError('native_decision_source_changed')
        region.update(applied=passed,status='native_RGB_structure_changed_protection_unverified' if passed else 'returned_RGB_structure_rejected')
        report.update(applied=passed,transformation_function_passed=passed,transformed_candidate_count=int(passed),
            transformed_pad_count=int(passed),all_detected_candidates_transformed=passed,changed_pixels=changed,
            returned_rgb_sha256=pixel_hash(returned),
            status='native_RGB_structure_changed_protection_unverified' if passed else 'returned_RGB_structure_rejected_original_returned')
        return returned,report
