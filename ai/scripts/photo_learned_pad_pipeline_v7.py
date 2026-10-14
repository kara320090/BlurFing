"""Separate experimental whole-permission-region feature gate.

Frozen renderer mathematics and numeric structure criteria are reused. Feature
ROI and coordinate domain change explicitly; this is NOT frozen-gate behavior
equivalence and never replaces the unified/default checked API.
"""
import cv2,numpy as np
import photo_learned_pad_pipeline_v1 as base
import photo_region_pipeline_v1 as shared
from photo_learned_pad_pipeline_v3 import prepare_scoped_region as prepare_body_scale
from photo_region_pipeline_v3 import render_candidate_region
from photo_body_observation_seed_v1 import prepare_region
from photo_native_owner_context_v1 import restore_contexts
from photo_owner_partition_v1 import partition
from photo_whole_region_structure_v1 import assess
from contactless_finger_width_body_v1 import estimate_finger_width_body

VERSION='photo_learned_pad_pipeline_v7_whole_permission_gate_experimental'


def working_views(rgb,artifact):
    height,width=artifact['working_shape'];orientation=artifact['exif_orientation'];scale=artifact['working_scale']
    image=cv2.resize(shared.orient(rgb,orientation),(width,height),interpolation=cv2.INTER_AREA if scale<1 else cv2.INTER_CUBIC)
    body=cv2.resize(shared.orient(artifact['body'].astype(np.uint8),orientation),(width,height),interpolation=cv2.INTER_NEAREST)>0
    permission=cv2.resize(shared.orient(artifact['coarse_mask'].astype(np.uint8),orientation),(width,height),interpolation=cv2.INTER_NEAREST)>0
    padding=artifact['regions'][0]['padding'];pad=((0,padding['bottom']),(0,padding['right']))
    return np.pad(image,pad+((0,0),),mode='edge'),np.pad(body,pad,constant_values=False),np.pad(permission,pad,constant_values=False)


def render(local,artifact,axis):
    import transform_automatic_fingerprint_poc_v4 as frozen
    import fingerprint_structure_check as structure
    first,body,permission=working_views(local,artifact);entry=artifact['regions'][0];scope=entry['working_scope'];seed=entry['working_seed']
    def check(original,candidate,box):
        if list(box)!=seed or not np.array_equal(original,first):raise ValueError('whole_region_renderer_source_contract')
        return assess(original,candidate,scope,permission,structure.estimate_finger_width(original,box))
    # Isolate this opt-in experiment from all normal adapter calls. The alias
    # is restored even if the renderer/extractor raises; no source is edited.
    with shared.renderer_binding._LOCK:
        old=frozen.check_structure_change
        try:
            frozen.check_structure_change=check
            candidate,report=render_candidate_region(local,artifact,axis)
        finally:frozen.check_structure_change=old
    if (candidate.dtype!=np.uint8 or candidate.shape!=local.shape or
            not np.array_equal(candidate[~artifact['coarse_mask']],local[~artifact['coarse_mask']])):
        raise ValueError('whole_region_native_output_contract')
    report.update(experimental_gate_version=VERSION,feature_scope_changed_from_frozen_seed=True,frozen_gate_equivalence=False)
    region=report['regions'][0]
    if region.get('applied') is True:
        final,_,_=working_views(candidate,artifact)
        # Native exterior equality was checked above. Cubic/area projection
        # can mix changed native pixels across the NEAREST permission edge.
        # Restore ORIGINAL observational context outside the working mask;
        # this changes no returned pixels and avoids counting resample spill.
        final[~permission]=first[~permission]
        width=estimate_finger_width_body(first,seed,axis,body,image_shape=tuple(artifact['working_shape']))
        native_check=assess(first,final,scope,permission,width)
        region['working_renderer_structure_check']=region['structure_check'];region['returned_RGB_structure_check']=native_check
        region['structure_check']=native_check;report['structure_checked_on_actual_native_return']=True
        report['reprojection_exterior_context_restored']=True
        if native_check.get('structure_change_passed') is not True:
            candidate=local.copy();region.update(applied=False,status='returned_RGB_structure_rejected')
            report.update(applied=False,transformation_function_passed=False,transformed_candidate_count=0,
                transformed_pad_count=0,all_detected_candidates_transformed=False,changed_pixels=0,
                returned_rgb_sha256=base.pixel_hash(local),status='returned_RGB_structure_rejected_original_returned')
    return candidate,report


def prepare_scoped_region(rgb,gray,native,owner,orientation,source_sha,plan,association):
    artifact,geometry,scoped_plan,_=prepare_body_scale(rgb,gray,native,owner,orientation,source_sha,plan,association,
        _preparer=prepare_region,_version=VERSION)
    if artifact is None:return artifact,geometry,scoped_plan,None
    a,b,c,d=geometry['scope']['bbox_encoded_original'];local=rgb[b:d,a:c].copy();mask=native[b:d,a:c].copy()
    def scoped_render(axis):
        before=base.pixel_hash(local);candidate,report=render(local,artifact,axis)
        if base.pixel_hash(local)!=before:raise ValueError('whole_region_source_RGB_changed')
        full=rgb.copy();full[b:d,a:c][mask]=candidate[mask];report['virtual_crop_provenance']=geometry['scope']
        return full,report
    geometry.update(feature_gate_scope='whole_permission_square_normalized_512',frozen_gate_equivalence=False)
    return artifact,geometry,scoped_plan,scoped_render


def evaluate_learned_mask(source,mask,expected_pixel_sha256,*,detect_only=False):
    result,report=base.evaluate_learned_mask(source,mask,expected_pixel_sha256,detect_only=detect_only,
        _scope_adapter=prepare_scoped_region,_version=VERSION,_candidate_builder=partition,_context_adapter=restore_contexts)
    report.update(feature_scope_changed_from_frozen_seed=True,frozen_gate_equivalence=False)
    return result,report


def protect_bundle(folder,root,output,detect_only=False):
    return base.protect_bundle(folder,root,output,detect_only,_mask_evaluator=evaluate_learned_mask,_version=VERSION)
