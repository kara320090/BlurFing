"""Explicit V6 pad detection followed by visible solid black redaction.

This separate experimental entrypoint has no pitch/feature acceptance gate.
Detection masks remain unverified; absent predictions remain unredacted.
"""
import json,os,subprocess
from pathlib import Path
import numpy as np
from PIL import Image
import pad_refinement_tiles_v3 as tiles
import photo_region_pipeline_v1 as shared
from pad_refinement_data_contract_v2 import digest,read_mask,native_shape,read_source_rgb
from photo_consumed_replay_v1 import development_replay as replay_scope,consumed_roles
from protection_runtime_sources_v1 import capture_runtime_sources,assert_runtime_sources_unchanged
from final_png_color_metadata_v1 import save_final_rgb_png
from photo_pitch_free_redaction_v1 import redact,pixel_hash

VERSION='single_photo_pitch_free_v1_experimental'


def run(source,model,registry_path,output,*,photo_semantics=None,development_replay=False,include_observed_pose=False,include_coarse_pad=False,complete_holes=False,allow_scanner=False,rounded_pads=False,candidate_only=False):
    if type(development_replay) is not bool:raise ValueError('development_replay_flag_must_be_boolean')
    if type(include_observed_pose) is not bool:raise ValueError('include_observed_pose_flag_must_be_boolean')
    if type(include_coarse_pad) is not bool:raise ValueError('include_coarse_pad_flag_must_be_boolean')
    if type(complete_holes) is not bool:raise ValueError('complete_holes_flag_must_be_boolean')
    if type(allow_scanner) is not bool:raise ValueError('allow_scanner_flag_must_be_boolean')
    if type(rounded_pads) is not bool:raise ValueError('rounded_pads_flag_must_be_boolean')
    if type(candidate_only) is not bool:raise ValueError('candidate_only_flag_must_be_boolean')
    source,model,registry_path,output=map(Path,(source,model,registry_path,output))
    if output.exists() or output.is_symlink():raise FileExistsError('fresh_output_required')
    # Early contract checks and pure redaction tools do not require Torch.
    from photo_source_rgb_v1 import canonical_rgb
    snapshot=capture_runtime_sources()
    registry,registry_sha=tiles.json_snapshot(registry_path);tiles.validate_registry(registry)
    original_identity=tiles.image_identity(source)
    if not development_replay:tiles.exclude_consumed(original_identity,registry)
    rgb,identity=canonical_rgb(source)
    route=shared.route_input(rgb)
    if candidate_only and route['input_type']!='PHOTO':
        raise ValueError('candidate_only_requires_PHOTO')
    if route['input_type']=='FINGERPRINT_IMAGE' and allow_scanner:
        return scanner_redaction(source,rgb,identity,route,output,registry_path,registry_sha,snapshot,development_replay)
    if route['input_type']!='PHOTO':
        raise ValueError('fingerprint_image_requires_scanner_mode' if route['input_type']=='FINGERPRINT_IMAGE' else 'input_type_uncertain_review_required')
    from infer_whole_pad_context_v6 import load_model,run as infer
    network,config=load_model(model);del network
    if config['consumed_registry_sha256']!=tiles.hash_json(registry):raise ValueError('frozen_consumed_registry_mismatch')
    if photo_semantics is None:
        runtime=[os.environ.get(k) for k in ['BLURFING_COLFISPOOF_PYTHON','BLURFING_COLFISPOOF_SOURCE','BLURFING_COLFISPOOF_MODEL']]
        if not all(runtime) or not all(Path(v).exists() for v in runtime):raise ValueError('photo_runtime_not_configured')
    if include_observed_pose:
        from protect_photo_pose_native_v1 import hand_configuration
        hand_runtime=hand_configuration()
    output.mkdir(parents=True,exist_ok=False);private=output/'private';private.mkdir()
    canonical=private/'canonical_input.png';exif=Image.Exif();exif[274]=identity['source_exif_orientation']
    Image.fromarray(rgb).save(canonical,exif=exif)
    if not np.array_equal(read_source_rgb(canonical,digest(canonical)),rgb):raise ValueError('canonical_RGB_roundtrip_mismatch')
    canonical_identity=tiles.image_identity(canonical)
    inference_source=source if photo_semantics is not None and identity['source_mode'] in ['RGB','L'] else canonical
    with replay_scope(registry,[original_identity,canonical_identity],enabled=development_replay):
        tiles.exclude_consumed(original_identity,registry);tiles.exclude_consumed(canonical_identity,registry)
        if photo_semantics is None:
            photo_semantics=private/'semantics'
            subprocess.run([runtime[0],str(Path(shared.__file__).with_name('colfispoof_body_semantics.py')),
                '--input',str(inference_source.resolve()),'--output',str(photo_semantics.resolve()),
                '--external-source',runtime[1],'--model',runtime[2]],shell=False,check=True,timeout=300,
                stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        shared.load_semantics(inference_source,rgb,photo_semantics)
        inputs=[dict(source_id='INPUT',source_path=str(inference_source.resolve()),source_sha256=digest(inference_source),
            semantics=str(Path(photo_semantics).resolve()),acquisition_group='unknown',group_provenance='unverified_user_input')]
        manifest=tiles.prepare(inputs,registry,private/'dataset',purpose='inference')
        predictions=infer(model,private/'dataset',private/'predictions')
        tiles.unchanged(private/'dataset/manifest.input.private.json',predictions['input_manifest_sha256'])
        tiles.check_tiles(private/'dataset',manifest,'inference')
    record=manifest['sources'][0];mask_path=private/'predictions/INPUT.png'
    mask=read_mask(mask_path,predictions['rows'][0]['prediction_sha256'],native_shape(record))
    from pad_refinement_data_contract_v2 import read_body
    learned=mask.copy();body=read_body(record)
    coarse=read_mask(record['coarse_path'],record['coarse_sha256'],native_shape(record))
    tip=read_mask(record['tip_path'],record['tip_sha256'],native_shape(record))
    detector_policy='V6_only';pose_metadata=None;coarse_metadata=None;pose_geometry=None
    if include_coarse_pad:
        from photo_isolated_coarse_completion_v1 import complete_isolated_pad
        mask,coarse_metadata=complete_isolated_pad(mask,coarse,body,tip)
        detector_policy='V6_with_isolated_coarse_completion'
    if include_observed_pose:
        import mediapipe_hand_worker_v1 as hand
        from photo_pose_native_pipeline_v1 import geometry_from_worker
        worker=private/'hand.private.json'
        subprocess.run([hand_runtime[0],str(Path(hand.__file__)),'--input',str(inference_source.resolve()),
            '--model',hand_runtime[1],'--output',str(worker.resolve())],shell=False,check=True,timeout=300,
            stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        hand_record,worker_sha=tiles.json_snapshot(worker)
        try:geometry=geometry_from_worker(record,rgb,hand_record)
        except ValueError as error:
            if str(error)!='pose_exactly_one_observed_hand_required':raise
            pose_metadata=dict(status=('no_single_observed_hand_base_mask_retained' if include_coarse_pad
                                       else 'no_single_observed_hand_V6_only'),reason=str(error))
        else:
            pose_geometry=geometry
            pose=geometry['permission_labels']>0;added=int((pose&~mask).sum());mask=mask|pose
            pose_metadata=dict(status='unreviewed_pose_union',added_pixels=added,anatomical_boundary_verified=False)
        tiles.unchanged(worker,worker_sha)
        if hand.digest(hand_runtime[1])!=hand.MODEL_SHA256:raise ValueError('official_hand_model_SHA256_mismatch')
        detector_policy=('V6_with_isolated_coarse_completion_union_observed_pose_if_available' if include_coarse_pad
                         else 'V6_union_observed_pose_if_available')
    from photo_owner_hole_completion_v1 import complete_owner_holes
    before_completion=mask.copy()
    mask,completion=complete_owner_holes(mask,coarse,body,tip,fill_holes=complete_holes)
    if complete_holes:detector_policy+='_owner_enclosed_holes'
    before_rounding=mask.copy();rounding=None
    if rounded_pads:
        from photo_rounded_pad_v1 import rounded_pads as round_whole_pads
        mask,rounding=round_whole_pads(mask,coarse,body,tip,pose_geometry=pose_geometry)
        detector_policy+='_rounded_whole_pad_geometry'
    if candidate_only:
        # The automatic renderer consumes masks, not a provisional black image.
        # Keep all inference/source checks and the two masks used downstream.
        returned=None
        report,artifacts=candidate_artifacts(rgb,mask,before_rounding,output,rounded_pads)
        color=dict(output_path=None)
    else:
        returned,report=redact(rgb,mask,pixel_hash(rgb),pixel_hash(mask))
        color=save_final_rgb_png(source,identity['original_source_sha256'],returned,output/'returned.png',identity['source_exif_orientation'])
        color['output_path']=str((output/'returned.png').resolve())
        Image.fromarray(mask.astype(np.uint8)*255).save(output/'redacted_mask.png')
        from pitch_free_artifacts_v1 import save_artifacts
        artifacts=save_artifacts(source,identity,rgb,coarse,mask,returned,output,
            stages=dict(body_mask=body,tip_mask=tip,learned_mask=learned,before_completion_mask=before_completion,
                **(dict(before_rounding_mask=before_rounding) if rounded_pads else {})))
    tiles.unchanged(source,identity['original_source_sha256']);tiles.unchanged(registry_path,registry_sha)
    runtime_sources=assert_runtime_sources_unchanged(snapshot)
    roles=sorted(set(consumed_roles(original_identity,registry)+consumed_roles(canonical_identity,registry)))
    report.update(single_photo_entrypoint=VERSION,input_identity=identity,model_sha256=predictions['model_sha256'],
        mask_scope='unreviewed_model_proposal',detector_policy=detector_policy,pose_metadata=pose_metadata,
        coarse_coverage_metadata=coarse_metadata,completion_metadata=completion,rounded_pad_metadata=rounding,input_type='PHOTO',route=route,**artifacts,
        GT_used=False,independent_final_test=False,development_replay=development_replay,
        consumed_source_detected=bool(roles),consumed_registry_roles=roles,runtime_source_snapshot=runtime_sources,
        runtime_source_snapshot_verified=True,
        **color)
    (output/'result.private.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return returned,report


def candidate_artifacts(rgb,mask,before_rounding,output,rounded_pads):
    """Minimal intermediate artifacts; deliberately no returned/protected RGB."""
    if (rgb.dtype!=np.uint8 or rgb.ndim!=3 or rgb.shape[-1]!=3
            or mask.dtype!=np.bool_ or mask.shape!=rgb.shape[:2]
            or before_rounding.dtype!=np.bool_ or before_rounding.shape!=mask.shape):
        raise ValueError('candidate_artifact_geometry')
    Image.fromarray(mask.astype(np.uint8)*255).save(output/'redacted_mask.png')
    if rounded_pads:
        Image.fromarray(before_rounding.astype(np.uint8)*255).save(output/'before_rounding_mask.png')
    return dict(status='candidates_only_no_protection',candidate_only=True,
        protection_applied=False,privacy_validated=False,
        anatomical_mask_coverage_verified=False,whole_photo_protection_verified=False,
        input_RGB_sha256=pixel_hash(rgb),mask_pixel_sha256=pixel_hash(mask)),dict()


def scanner_redaction(source,rgb,identity,route,output,registry_path,registry_sha,snapshot,development_replay):
    """Reuse scanner ROI detection; never invoke a hand CNN for scanner inputs.

    The existing detector uses periodic-ridge evidence, while the visible solid
    redaction does not estimate pitch or synthesize a fingerprint texture.
    """
    from scanner_fingerprint_detector import detect_scanner
    from pitch_free_artifacts_v1 import save_artifacts
    regions,detail=detect_scanner(rgb,identity['original_source_sha256'])
    mask=np.zeros(rgb.shape[:2],bool)
    for region in regions:
        region.validate(rgb,identity['original_source_sha256']);mask|=region.binary_mask>0
    output.mkdir(parents=True,exist_ok=False)
    returned,report=redact(rgb,mask,pixel_hash(rgb),pixel_hash(mask))
    color=save_final_rgb_png(source,identity['original_source_sha256'],returned,output/'returned.png',identity['source_exif_orientation'])
    Image.fromarray(mask.astype(np.uint8)*255).save(output/'redacted_mask.png')
    artifacts=save_artifacts(source,identity,rgb,mask,mask,returned,output)
    tiles.unchanged(source,identity['original_source_sha256']);tiles.unchanged(registry_path,registry_sha)
    report.update(single_photo_entrypoint=VERSION,input_identity=identity,input_type='FINGERPRINT_IMAGE',route=route,
        detector_policy='existing_scanner_ROI',detection=detail,photo_models_used=False,
        detection_requires_periodic_ridge_evidence=True,development_replay=development_replay,
        independent_final_test=False,GT_used=False,runtime_source_snapshot=assert_runtime_sources_unchanged(snapshot),
        runtime_source_snapshot_verified=True,output_path=str((output/'returned.png').resolve()),**artifacts,**color)
    (output/'result.private.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return returned,report


if __name__=='__main__':
    from protect_fingerprint import JSONArgumentParser,cli_progress_to_stderr
    parser=JSONArgumentParser(description=__doc__)
    for name in ['input','model','consumed-registry','output']:parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--photo-semantics',type=Path);parser.add_argument('--development-replay',action='store_true')
    parser.add_argument('--include-observed-pose',action='store_true',help='Explicit wider unreviewed proposal; can redact extra background.')
    parser.add_argument('--include-coarse-pad',action='store_true',help='Explicit isolated-finger coarse completion; may redact extra skin.')
    parser.add_argument('--complete-holes',action='store_true',help='Fill enclosed holes within each observed owner; no boundary dilation.')
    parser.add_argument('--rounded-pads',action='store_true',help='Replace eligible owners with rounded distal caps; inferred boundaries require review.')
    parser.add_argument('--allow-scanner',action='store_true',help='Route fingerprint-only inputs to the existing scanner ROI detector.');args=parser.parse_args()
    try:
        with cli_progress_to_stderr():_,result=run(args.input,args.model,args.consumed_registry,args.output,
            photo_semantics=args.photo_semantics,development_replay=args.development_replay,include_observed_pose=args.include_observed_pose,
            include_coarse_pad=args.include_coarse_pad,complete_holes=args.complete_holes,allow_scanner=args.allow_scanner,rounded_pads=args.rounded_pads)
        print(json.dumps(result,indent=2))
    except Exception as error:
        from photo_source_rgb_v1 import source_diagnostic
        try:diagnostic=source_diagnostic(args.input)
        except Exception as diagnostic_error:diagnostic=dict(header_error=type(diagnostic_error).__name__)
        print(json.dumps(dict(status='error',error=type(error).__name__,reason=str(error),input_diagnostic=diagnostic)));raise SystemExit(1)
