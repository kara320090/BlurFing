"""Explicit component-local evidence experiment; anatomical FP remain possible.

No disconnected permission fragment may borrow another fragment's periodicity
or aggregate extracted features. Every prediction pixel remains represented.
"""
import numpy as np
import photo_learned_pad_pipeline_v1 as base
import photo_region_pipeline_v1 as shared
from photo_learned_pad_pipeline_v3 import prepare_scoped_region as prepare_body_scale
from photo_learned_pad_pipeline_v7 import render,working_views
from photo_body_observation_seed_v1 import prepare_region
from photo_native_owner_context_v1 import restore_contexts
from photo_component_local_evidence_v1 import connected_partition,observed_component_pitch

VERSION='photo_learned_pad_pipeline_v8_component_local_evidence_experimental'


def prepare_local(*args,**kwargs):
    artifact,geometry=prepare_region(*args,**kwargs,_pitch_observer=observed_component_pitch)
    if geometry['reject_reason']=='body_supported_pitch_unobserved':geometry['reject_reason']='component_local_pitch_unobserved'
    if geometry['reject_reason']=='body_supported_seed_unavailable':geometry['reject_reason']='component_local_seed_unavailable'
    return artifact,geometry


def prepare_scoped_region(rgb,gray,native,owner,orientation,source_sha,plan,association):
    artifact,geometry,scoped_plan,_=prepare_body_scale(rgb,gray,native,owner,orientation,source_sha,plan,association,
        _preparer=prepare_local,_version=VERSION)
    geometry.update(evidence_permission_component_local=True,anatomical_pad_verified=False)
    if artifact is None:return artifact,geometry,scoped_plan,None
    a,b,c,d=geometry['scope']['bbox_encoded_original'];local=rgb[b:d,a:c].copy();mask=native[b:d,a:c].copy()
    def scoped_render(axis):
        import transform_automatic_fingerprint_poc_v4 as frozen
        before=base.pixel_hash(local);first,_,permission=working_views(local,artifact);entry=artifact['regions'][0];calls=[]
        def observe(image,box):
            if list(box)!=entry['working_seed'] or not np.array_equal(image,first):
                raise ValueError('component_local_renderer_pitch_scope_mismatch')
            result=observed_component_pitch(image,box,permission)
            if result[0]!=geometry['observed_pitch_working'] or result[1]!=entry['pitch_measurement']:
                raise ValueError('component_local_renderer_pitch_remeasurement_mismatch')
            calls.append(True);return result
        with shared.renderer_binding._LOCK:
            previous=frozen.observed_seed_pitch
            try:
                frozen.observed_seed_pitch=observe
                candidate,report=render(local,artifact,axis)
            finally:frozen.observed_seed_pitch=previous
        if not calls:raise ValueError('component_local_renderer_observer_not_called')
        if base.pixel_hash(local)!=before:raise ValueError('component_local_source_RGB_changed')
        full=rgb.copy();full[b:d,a:c][mask]=candidate[mask]
        report.update(virtual_crop_provenance=geometry['scope'],experimental_gate_version=VERSION,
                      evidence_permission_component_local=True,renderer_pitch_remeasurement_component_local=True,anatomical_pad_verified=False)
        return full,report
    geometry.update(feature_gate_scope='connected_permission_component_square_normalized_512',frozen_gate_equivalence=False)
    return artifact,geometry,scoped_plan,scoped_render


def evaluate_learned_mask(source,mask,expected_pixel_sha256,*,detect_only=False):
    returned,report=base.evaluate_learned_mask(source,mask,expected_pixel_sha256,detect_only=detect_only,
        _scope_adapter=prepare_scoped_region,_version=VERSION,_candidate_builder=connected_partition,_context_adapter=restore_contexts)
    report.update(evidence_permission_component_local=True,anatomical_pad_verified=False,
        prediction_false_positives_possible=True,feature_scope_changed_from_frozen_seed=True,frozen_gate_equivalence=False,
        count_semantics='connected permission components within observed owners; not anatomical fingers',
        partition_policy='connected_permission_components_no_pixel_dropping')
    return returned,report


def protect_bundle(folder,root,output,detect_only=False):
    return base.protect_bundle(folder,root,output,detect_only,_mask_evaluator=evaluate_learned_mask,_version=VERSION)
