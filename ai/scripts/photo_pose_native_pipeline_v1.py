"""Explicit observed-pose candidates with unchanged V12 actual-native gate."""
import hashlib,json
from pathlib import Path
import numpy as np
from PIL import Image
import mediapipe_hand_worker_v1 as hand
import photo_pose_permissions_v1 as pose
import photo_learned_pad_pipeline_v1 as base
from photo_learned_pad_pipeline_v12 import prepare_scoped_region
from photo_quality_gate import summarize
from pad_refinement_data_contract_v2 import verify_source,read_source_rgb,read_body,digest

VERSION='photo_pose_native_v14_experimental'


def usage():
    return dict(version=VERSION,GT_used=False,privacy_validated=False,complete_photo_protection_verified=False,
        default_pipeline_enabled=False,approved_for_protection=False,independent_validation_complete=False,
        independent_final_test=False,V6_learned_pad_model_used=False,anatomical_pad_verified=False,
        final_native_gate_authoritative=True,working_structure_is_diagnostic=True,
        algorithm_thresholds_unchanged=True,frozen_files_unchanged=True,
        permission_source=pose.VERSION,legacy_estimator_contexts_used=False,
        legacy_estimator_execution='existing base estimate still runs; its contexts are explicitly discarded by pose builder',
        no_best_result_or_detector_fallback=True)


def verify_worker(source,rgb,record):
    if not isinstance(record,dict):raise ValueError('pose_worker_record_contract')
    _,upright,orientation=hand.decode(source['source_path'])
    expected=dict(version=hand.VERSION,source_sha256=source['source_sha256'],encoded_RGB_sha256=source['source_RGB_sha256'],
        upright_RGB_sha256=base.pixel_hash(upright),encoded_shape=list(rgb.shape),upright_shape=list(upright.shape),
        source_exif_orientation=source['source_exif_orientation'],model_sha256=hand.MODEL_SHA256,
        worker_code_sha256=digest(Path(hand.__file__)),configuration=hand.CONFIGURATION,GT_used=False)
    for key,value in expected.items():
        if record.get(key)!=value:raise ValueError('pose_worker_binding_mismatch:'+key)
    runtime=record.get('runtime')
    if (type(record.get('source_exif_orientation')) is not int or not isinstance(runtime,dict) or
            orientation!=source['source_exif_orientation'] or runtime.get('mediapipe_version')!=hand.MEDIAPIPE_VERSION):
        raise ValueError('pose_worker_runtime_or_orientation_mismatch')
    count=record.get('hand_count');hands=record.get('hands')
    if type(count) is not int or not isinstance(hands,list) or not 0<=count<=hand.CONFIGURATION['num_hands'] or count!=len(hands):
        raise ValueError('pose_worker_hand_count_contract')
    if record.get('status')!=('observed' if count else 'no_hand_observed'):raise ValueError('pose_worker_status_contract')
    for observed in hands:
        if not isinstance(observed,dict):raise ValueError('pose_worker_landmark_contract')
        raw=np.asarray(observed.get('normalized_xy'))
        if raw.shape!=(21,2) or raw.dtype.kind not in 'iuf' or not np.isfinite(raw).all():raise ValueError('pose_worker_landmark_contract')


def build_candidates(geometry):
    owners=geometry['owner_labels'];proposed=geometry['proposed_labels'];bound=geometry['permission_labels'];unbound=geometry['rejected_labels']
    labels=np.zeros(owners.shape,np.uint16);records=[]
    for axis in geometry['axes']:
        digit=axis['digit'];digit_label=axis['label'];owner=owners==digit_label
        for native,reason in [(bound==digit_label,None),(unbound==digit_label,'pose_permission_not_connected_to_observed_TIP')]:
            if not native.any():continue
            if np.any(native&(labels>0)) or np.any(native&~owner):raise ValueError('pose_candidate_overlap_or_owner_contract')
            component=len(records)+1;labels[native]=component;identity='pose-'+digit+('-unbound' if reason else '-TIP-connected')
            association=None if reason else dict(axis_native_yx=axis['axis_native_yx'],candidate_id=identity,
                association_policy='observed_finite_segment_BODY_owner_and_exact_TIP_component',anatomical_owner_verified=False,
                pose_tip_id=axis['tip_id'],pose_joint_id=axis['DIP_or_IP_id'])
            records.append(dict(candidate_id=identity,reason=reason,association=association,owner=owner,
                plan=dict(component=component,status='rejected' if reason else 'planned',reject_reason=reason,
                          working_scale=1.,mask_pixels=int(native.sum()))))
    if not np.array_equal(labels>0,proposed>0):raise ValueError('pose_candidate_pixel_loss')
    return labels,records


def geometry_from_worker(source,rgb,record):
    verify_worker(source,rgb,record)
    if record['hand_count']!=1:raise ValueError('pose_exactly_one_observed_hand_required')
    body=read_body(source)
    native=pose.normalized_landmarks_to_native(record['hands'][0]['normalized_xy'],body.shape,source['source_exif_orientation'])
    return pose.pose_permissions(body,native)


def _verify_source_unchanged(source,rgb):
    verify_source(source,'inference')
    if base.pixel_hash(rgb)!=source['source_RGB_sha256']:raise ValueError('pose_decoded_source_changed')


def evaluate(source,worker_record,*,detect_only=False):
    if type(detect_only) is not bool:raise ValueError('detect_only_flag_must_be_boolean')
    verify_source(source,'inference');rgb=read_source_rgb(source['source_path'],source['source_sha256'])
    try:geometry=geometry_from_worker(source,rgb,worker_record)
    except (ValueError,TypeError,KeyError) as error:
        # A normal rejection must not conceal a raced source/semantic file or
        # mutation of the decoded original in standalone-library usage.
        _verify_source_unchanged(source,rgb)
        report=summarize([])|usage()|dict(source_id=source['source_id'],source_sha256=source['source_sha256'],
            source_exif_orientation=source['source_exif_orientation'],coordinate_system='encoded_original_pixels',
            reject_reason=str(error),changed_pixels=0,returned_RGB_sha256=base.pixel_hash(rgb),
            exterior_preserved=True,rejected_pixels_preserved=True,RGB_outside_accepted_permission_preserved=True,
            pose_worker_hand_count=worker_record.get('hand_count') if isinstance(worker_record,dict) else None)
        return rgb.copy(),report
    labels,records=build_candidates(geometry);mask=geometry['proposed_labels']>0;before=base.pixel_hash(labels)
    def candidates(actual,old_contexts):
        # The estimator contexts deliberately have no role in pose ownership.
        if not np.array_equal(actual,mask) or base.pixel_hash(labels)!=before:raise ValueError('pose_candidate_identity_changed')
        return dict(labels=labels,records=records)
    returned,report=base.evaluate_learned_mask(source,mask,base.pixel_hash(mask),detect_only=detect_only,
        _version=VERSION,_scope_adapter=prepare_scoped_region,_candidate_builder=candidates)
    accepted=np.zeros(mask.shape,bool)
    for region in report['regions']:
        if region['status']=='transformed':accepted|=labels==region['region_id']
    if not np.array_equal(returned[~accepted],rgb[~accepted]):raise ValueError('pose_actual_RGB_changed_outside_accepted_permission')
    _verify_source_unchanged(source,rgb)
    if base.pixel_hash(labels)!=before:raise ValueError('pose_candidate_identity_changed')
    report.update(**usage(),RGB_outside_accepted_permission_preserved=True,unbound_pixels_preserved=True,
        pose_worker_hand_count=worker_record['hand_count'],pose_worker_model_sha256=worker_record['model_sha256'],
        pose_worker_record_sha256=hashlib.sha256(json.dumps(worker_record,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
        pose_geometry_metadata=geometry['metadata'],pose_axes=geometry['axes'],
        pose_label_sha256={key:base.pixel_hash(geometry[key]) for key in ['owner_labels','proposed_labels','permission_labels','rejected_labels']},
        pose_bound_permission_pixels=int((geometry['permission_labels']>0).sum()),pose_unbound_rejected_pixels=int((geometry['rejected_labels']>0).sum()),
        count_semantics='observed-pose digit permission groups plus unbound rejected diagnostics; not anatomical finger detection count')
    return returned,report
