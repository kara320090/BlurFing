"""Opt-in learned native pads + observed body axes + frozen protection gates.

No component cleanup, largest-owner selection, default activation or target use.
Group-heldout masks can exercise the renderer as developmental diagnostics.
"""
import argparse,hashlib,json,time
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
from scipy import ndimage
import photo_region_pipeline_v1 as shared
from photo_region_pipeline_v3 import render_candidate_region,HANDLED
from photo_candidate_context_v1 import candidate_contexts
from photo_quality_gate import state,summarize
from finger_body_distal_estimator import estimate
from pad_refinement_data_contract_v2 import (verify_source,read_source_rgb,read_body,read_mask,native_shape,digest)
from pad_refinement_tiles_v3 import json_snapshot,unchanged,check_tiles

VERSION='photo_learned_pad_pipeline_v1_experimental'
MAX_COMPONENTS=256


def pixel_hash(mask):return hashlib.sha256(mask.tobytes()).hexdigest()


def associate_learned_body_axis(native,contexts):
    if not isinstance(native,np.ndarray) or native.dtype!=np.bool_ or native.ndim!=2 or not native.any():
        raise ValueError('nonempty_boolean_learned_component_required')
    matches=[]
    for context in contexts:
        body=context['body']
        if body.shape!=native.shape or body.dtype!=np.bool_:raise ValueError('learned_body_shape_contract')
        # Invalid contexts still participate in overlap detection.
        if np.any(native & body):matches.append(context)
    if len(matches)!=1:raise ValueError('learned_body_owner_unavailable' if not matches else 'learned_body_owner_ambiguous')
    context=matches[0]
    if np.any(native & ~context['body']):raise ValueError('learned_component_crosses_body_owner')
    if context['reject_reason'] is not None:raise ValueError('learned_body_axis_unavailable:'+context['reject_reason'])
    parent=context['parent']
    required={'mask','major_axis_yx','working_scale','metadata_coordinate_system','component','watershed_part'}
    if not required<=parent.keys():raise ValueError('learned_body_axis_metadata_unavailable')
    try:axis=np.asarray(parent['major_axis_yx'],dtype=np.float64);scale=float(parent['working_scale'])
    except (ValueError,TypeError):raise ValueError('learned_body_axis_metadata_invalid') from None
    if axis.shape!=(2,) or not np.isfinite(axis).all() or not np.linalg.norm(axis)>0 or not np.isfinite(scale) or not 0<scale<=1:
        raise ValueError('learned_body_axis_metadata_invalid')
    # Reuse the observed parent axis conversion; learned pixels need not be
    # inside the parent's old coarse pad. Full body ownership was checked above.
    association=shared.associate_axis(parent['mask'],[parent])
    association.update(estimator_region_index=context['estimator_region_index'],candidate_id=context['candidate_id'],
                       watershed_part=parent['watershed_part'],association_policy='unique_observed_body_context',
                       coarse_subset_required=False)
    return association,context['body']


def evaluate_learned_mask(source,mask,expected_pixel_sha256,*,detect_only=False):
    """Source is an inference-manifest record; mask is hash-bound native bool."""
    start=time.perf_counter()
    if any(k.startswith('GT') for k in source):raise ValueError('GT_fields_forbidden_in_learned_protection')
    verify_source(source,'inference');rgb=read_source_rgb(source['source_path'],source['source_sha256'])
    if (not isinstance(mask,np.ndarray) or mask.dtype!=np.bool_ or mask.shape!=native_shape(source) or
            pixel_hash(mask)!=expected_pixel_sha256):raise ValueError('learned_prediction_mask_contract')
    body=read_body(source);tip=read_mask(source['tip_path'],source['tip_sha256'],body.shape)
    if np.any(mask & ~body):raise ValueError('learned_prediction_outside_observed_body')
    orientation=source['source_exif_orientation'];route=shared.route_input(rgb)
    returned=rgb.copy();regions=[];failure=None;count=None
    try:
        if type(orientation) is not int or orientation not in range(1,9):raise ValueError('invalid_source_exif_orientation')
        if route['input_type']!='PHOTO':raise ValueError('experimental_photo_input_required')
        labels,count=ndimage.label(mask)
        if count>MAX_COMPONENTS:raise ValueError('learned_component_resource_limit')
        result=estimate(body,tip,preserve_candidates=True);contexts=candidate_contexts(result,body)
        plans=shared.plan_region_scales(mask);gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
        for plan in plans['regions']:
            native=labels==plan['component']
            row=dict(region_id=plan['component'],mask_pixels=int(native.sum()),mask_pixel_sha256=pixel_hash(native),
                     scale_plan=plan,status='rejected',quality_status='REJECT_OTHER',reason=plan['reject_reason'])
            try:
                if plan['status']=='planned':
                    association,owner=associate_learned_body_axis(native,contexts);row['association']=association
                    artifact,geometry=shared.prepare_region(rgb,gray,native,owner,orientation,source['source_sha256'],plan,association)
                    row.update(geometry=geometry,reason=geometry['reject_reason'])
                    if artifact is not None:
                        roi=artifact['regions'][0]['roi'];roi.detector_name=VERSION;roi.detector_version=VERSION
                        roi.validate(rgb,source['source_sha256'])
                        row['detector_provenance']=VERSION
                        if detect_only:row['reason']='detect_only'
                        else:
                            candidate,details=render_candidate_region(rgb,artifact,geometry['axis_working_yx'])
                            row['renderer_details']=details
                            if len(details['regions'])!=1 or details['regions'][0].get('candidate_id')!=f"coarse-{plan['component']}":
                                raise ValueError('region_renderer_identity_contract_mismatch')
                            report=details['regions'][0];applied=report.get('applied')
                            if type(applied) is not bool:raise ValueError('region_applied_flag_contract_mismatch')
                            if applied and report.get('structure_check',{}).get('structure_change_passed') is not True:
                                raise ValueError('region_structure_guard_contract_mismatch')
                            row['reason']=None if applied else (report.get('structure_check',{}).get('reason') or report.get('status') or 'renderer_contract_not_satisfied')
                            if applied:
                                if (not isinstance(candidate,np.ndarray) or candidate.dtype!=np.uint8 or candidate.shape!=rgb.shape or
                                        not np.array_equal(candidate[~native],rgb[~native])):
                                    raise ValueError('region_renderer_output_contract_mismatch')
                                returned[native]=candidate[native];row.update(status='transformed',quality_status='TRANSFORMED')
                if row['status']!='transformed':row['quality_status']=state(row['reason'])
            except HANDLED as error:row.update(reason=str(error),error=type(error).__name__,quality_status=state(str(error)))
            if row['status']=='rejected' and not np.array_equal(returned[native],rgb[native]):raise RuntimeError('rejected_region_pixels_changed')
            regions.append(row)
        for row in regions:
            native=labels==row['region_id']
            if row['status']=='rejected' and not np.array_equal(returned[native],rgb[native]):raise RuntimeError('rejected_region_pixels_changed')
    except HANDLED as error:
        returned=rgb.copy();failure=dict(reject_reason=str(error),error=type(error).__name__)
        for row in regions:row.update(status='rejected',quality_status='REJECT_OTHER',reason='experiment_contract_failure')
    verify_source(source,'inference')
    if (not np.array_equal(returned[~mask],rgb[~mask]) or pixel_hash(rgb)!=source['source_RGB_sha256'] or
            pixel_hash(mask)!=expected_pixel_sha256):raise RuntimeError('source_or_exterior_changed')
    report=summarize(regions)|dict(version=VERSION,source_sha256=source['source_sha256'],source_id=source['source_id'],
        prediction_pixel_sha256=expected_pixel_sha256,coordinate_system='encoded_original_pixels',source_exif_orientation=orientation,
        predicted_component_count=count,processed_region_count=len(regions),
        default_pipeline_enabled=False,approved_for_protection=False,independent_validation_complete=False,PHOTO_FAIL_CLOSED_PIPELINE_READY=False,
        algorithm_thresholds_unchanged=True,frozen_files_unchanged=True,exterior_preserved=True,rejected_pixels_preserved=True,
        changed_pixels=int(np.any(returned!=rgb,axis=2).sum()),returned_RGB_sha256=pixel_hash(returned),
        count_semantics='connected learned mask components, not true fingerprint count',timing_total=time.perf_counter()-start)
    if failure:report.update(failure)
    return returned,report


def save_result(output,returned,report):
    output.mkdir(parents=True,exist_ok=False);exif=Image.Exif();exif[274]=report['source_exif_orientation']
    Image.fromarray(returned).save(output/'returned.png',exif=exif)
    with Image.open(output/'returned.png') as image:
        if not np.array_equal(np.asarray(image),returned):raise RuntimeError('saved_RGB_roundtrip_mismatch')
    (output/'result.private.json').write_text(json.dumps(report,indent=2),encoding='utf-8')


def protect_bundle(folder,root,output,detect_only=False):
    from infer_pad_refinement_tiles_v3 import run
    if output.exists():raise FileExistsError('fresh_protection_output_required')
    # Full input/checkpoint preflight happens inside run before forward/output.
    predictions=run(folder,root,output/'predictions')
    manifest,sha=json_snapshot(root/'manifest.input.private.json')
    if sha!=predictions['input_manifest_sha256']:raise ValueError('prediction_input_manifest_mismatch')
    check_tiles(root,manifest,'inference');rows=[]
    indexed={r['source_id']:r for r in predictions['rows']}
    for source in manifest['sources']:
        sid=source['source_id'];path=output/'predictions'/(sid+'.png')
        mask=read_mask(path,indexed[sid]['prediction_sha256'],native_shape(source))
        returned,report=evaluate_learned_mask(source,mask,pixel_hash(mask),detect_only=detect_only)
        report['model_sha256']=predictions['model_sha256'];save_result(output/sid,returned,report);rows.append(report)
    unchanged(root/'manifest.input.private.json',sha)
    check_tiles(root,manifest,'inference')
    result=dict(version=VERSION,rows=rows,model_sha256=predictions['model_sha256'],default_pipeline_enabled=False,approved_for_protection=False)
    (output/'protection.private.json').write_text(json.dumps(result,indent=2),encoding='utf-8');return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--model',type=Path,required=True)
    p.add_argument('--inputs',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--detect-only',action='store_true');a=p.parse_args()
    protect_bundle(a.model,a.inputs,a.output,a.detect_only)
