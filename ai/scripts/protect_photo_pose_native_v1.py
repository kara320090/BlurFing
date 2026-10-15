"""Explicit PHOTO-only full-hand pose experiment; no learned V6 pad fallback."""
import json,os,subprocess
from pathlib import Path
import numpy as np
from PIL import Image
import mediapipe_hand_worker_v1 as hand
import photo_pose_native_pipeline_v1 as pipeline
import photo_learned_pad_pipeline_v1 as base
import photo_region_pipeline_v1 as shared
import pad_refinement_tiles_v3 as tiles
from pad_refinement_data_contract_v2 import digest,read_source_rgb
from photo_consumed_replay_v1 import development_replay as replay_scope,consumed_roles
from protect_photo_whole_pad_context_native_v1 import canonical_rgb
from protection_runtime_sources_v1 import capture_runtime_sources,assert_runtime_sources_unchanged
from final_png_color_metadata_v1 import save_final_rgb_png

VERSION='single_photo_pose_native_v14_experimental'


def code_hashes():
    # Curated runtime snapshot; caller may extend it with platform/runtime
    # identity snapshots. No model artifacts or biometric assets are included.
    core=Path(base.__file__).parent;local=Path(__file__).parent
    names=['photo_learned_pad_pipeline_v1.py','photo_learned_pad_pipeline_v12.py',
        'photo_learned_pad_pipeline_v11.py','photo_learned_pad_pipeline_v10.py','photo_native_return_decision_v1.py',
        'photo_resize_safety_v1.py','photo_consumed_replay_v1.py','pad_refinement_data_contract_v2.py',
        'pad_refinement_tiles_v3.py','photo_region_pipeline_v1.py','photo_region_pipeline_v3.py',
        'finger_body_distal_estimator.py','fingerprint_structure_check.py',
        'transform_automatic_fingerprint_poc_v4.py','transform_automatic_fingerprint_poc_v4_boundaryblend_02.py']
    result={name:digest(core/name) for name in names}
    for name in ['photo_pose_permissions_v1.py','mediapipe_hand_worker_v1.py','photo_pose_native_pipeline_v1.py',Path(__file__).name]:
        result[name]=digest(local/name)
    return result


def usage_metadata(replay):
    if type(replay) is not bool:raise ValueError('development_replay_flag_must_be_boolean')
    values=pipeline.usage();values.pop('version') # Keep the V3 input-manifest schema identity.
    return values|dict(single_photo_entrypoint=VERSION,development_replay=replay,
        data_role='development_replay' if replay else 'unverified_user_input',
        semantic_segmentation_required=True,hand_observations_required=True,model_probability_calibrated=False,
        no_hand_or_invalid_pose_policy='original_RGB_rejected_without_fallback')


def hand_configuration():
    config=[os.environ.get(k) for k in ['BLURFING_HAND_PYTHON','BLURFING_HAND_MODEL']]
    if not all(config) or not all(Path(value).is_file() for value in config):raise ValueError('hand_runtime_not_configured')
    if hand.digest(config[1])!=hand.MODEL_SHA256:raise ValueError('official_hand_model_SHA256_mismatch')
    return config


def run(source,registry_path,output,*,photo_semantics=None,detect_only=False,development_replay=False):
    if type(detect_only) is not bool:raise ValueError('detect_only_flag_must_be_boolean')
    usage=usage_metadata(development_replay)
    source,registry_path,output=map(Path,(source,registry_path,output))
    if output.exists():raise FileExistsError('fresh_output_required')
    code=code_hashes();runtime_snapshot=capture_runtime_sources()
    registry,registry_sha=tiles.json_snapshot(registry_path);tiles.validate_registry(registry)
    original_identity=tiles.image_identity(source)
    if not development_replay:tiles.exclude_consumed(original_identity,registry)
    rgb,identity=canonical_rgb(source);route=shared.route_input(rgb)
    if route['input_type']!='PHOTO':raise ValueError('experimental_photo_input_required')
    hand_config=hand_configuration()
    if photo_semantics is None:
        semantic_config=[os.environ.get(k) for k in ['BLURFING_COLFISPOOF_PYTHON','BLURFING_COLFISPOOF_SOURCE','BLURFING_COLFISPOOF_MODEL']]
        if not all(semantic_config) or not all(Path(value).exists() for value in semantic_config):raise ValueError('photo_runtime_not_configured')
    output.mkdir(parents=True,exist_ok=False);private=output/'private';private.mkdir()
    canonical=private/'canonical_input.png';exif=Image.Exif();exif[274]=identity['source_exif_orientation']
    Image.fromarray(rgb).save(canonical,exif=exif)
    if not np.array_equal(read_source_rgb(canonical,digest(canonical)),rgb):raise ValueError('canonical_RGB_roundtrip_mismatch')
    canonical_identity=tiles.image_identity(canonical)
    roles=sorted(set(consumed_roles(original_identity,registry)+consumed_roles(canonical_identity,registry)))
    usage.update(consumed_source_detected=bool(roles),consumed_registry_roles=roles)
    # Cached semantic files keep their actual original encoded source binding.
    inference_source=source if photo_semantics is not None and identity['source_mode'] in ['RGB','L'] else canonical
    with replay_scope(registry,[original_identity,canonical_identity],enabled=development_replay):
        tiles.exclude_consumed(original_identity,registry);tiles.exclude_consumed(canonical_identity,registry)
        if photo_semantics is None:
            photo_semantics=private/'semantics'
            command=[semantic_config[0],str(Path(shared.__file__).with_name('colfispoof_body_semantics.py')),
                '--input',str(inference_source.resolve()),'--output',str(photo_semantics.resolve()),
                '--external-source',semantic_config[1],'--model',semantic_config[2]]
            subprocess.run(command,shell=False,check=True,timeout=300,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        shared.load_semantics(inference_source,rgb,photo_semantics)
        inputs=[dict(source_id='INPUT',source_path=str(inference_source.resolve()),source_sha256=digest(inference_source),
                     semantics=str(Path(photo_semantics).resolve()),acquisition_group='unknown',group_provenance='user_input_unverified')]
        view=tiles.prepare(inputs,registry,private/'dataset',purpose='inference');view.update(**usage)
        manifest=private/'dataset/manifest.input.private.json';manifest.write_text(json.dumps(view,indent=2),encoding='utf-8')
        manifest_sha=digest(manifest);tiles.check_tiles(private/'dataset',view,'inference')
        worker_path=private/'hand-landmarks.private.json'
        command=[hand_config[0],str(Path(hand.__file__)),'--input',str(inference_source.resolve()),
                 '--model',hand_config[1],'--output',str(worker_path.resolve())]
        subprocess.run(command,shell=False,check=True,timeout=300,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        record,record_sha=tiles.json_snapshot(worker_path)
        returned,report=pipeline.evaluate(view['sources'][0],record,detect_only=detect_only)
        if report.get('pose_geometry_metadata') is not None:
            geometry=pipeline.geometry_from_worker(view['sources'][0],rgb,record)
            masks=private/'pose-geometry';masks.mkdir()
            for key in ['owner_labels','proposed_labels','permission_labels','rejected_labels']:
                if base.pixel_hash(geometry[key])!=report['pose_label_sha256'][key]:raise ValueError('pose_diagnostic_regeneration_mismatch')
                Image.fromarray(geometry[key]).save(masks/(key+'.png'))
            (masks/'metadata.private.json').write_text(json.dumps(dict(axes=geometry['axes'],metadata=geometry['metadata']),indent=2),encoding='utf-8')
        tiles.unchanged(worker_path,record_sha);tiles.unchanged(manifest,manifest_sha);tiles.check_tiles(private/'dataset',view,'inference')
    if base.pixel_hash(returned)!=report['returned_RGB_sha256']:raise ValueError('returned_RGB_hash_mismatch')
    color_metadata=save_final_rgb_png(source,identity['original_source_sha256'],returned,output/'returned.png',identity['source_exif_orientation'])
    report.update(**color_metadata)
    with Image.open(output/'returned.png') as image:
        if image.mode!='RGB' or image.getexif().get(274,1)!=identity['source_exif_orientation'] or not np.array_equal(np.asarray(image),returned):
            raise ValueError('saved_RGB_EXIF_roundtrip_mismatch')
    tiles.unchanged(source,identity['original_source_sha256']);tiles.unchanged(registry_path,registry_sha)
    if hand.digest(hand_config[1])!=hand.MODEL_SHA256 or code_hashes()!=code:raise ValueError('pose_runtime_or_model_changed_during_run')
    runtime_provenance=assert_runtime_sources_unchanged(runtime_snapshot)
    report.update(**usage,input_identity=identity,input_type='photo',route=route,image_width=rgb.shape[1],image_height=rgb.shape[0],
        output_path=str((output/'returned.png').resolve()),runtime_code_sha256=code,hand_model_sha256=hand.MODEL_SHA256,
        hand_observation_file_sha256=record_sha,RGB_outside_accepted_permission_preserved=True,
        runtime_source_snapshot=runtime_provenance,runtime_source_snapshot_verified=True)
    (output/'result.private.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return returned,report


if __name__=='__main__':
    from protect_fingerprint import JSONArgumentParser,cli_progress_to_stderr
    parser=JSONArgumentParser(description=__doc__)
    for name in ['input','consumed-registry','output']:parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--photo-semantics',type=Path);parser.add_argument('--detect-only',action='store_true')
    parser.add_argument('--development-replay',action='store_true');args=parser.parse_args()
    try:
        with cli_progress_to_stderr():
            _,result=run(args.input,args.consumed_registry,args.output,photo_semantics=args.photo_semantics,
                         detect_only=args.detect_only,development_replay=args.development_replay)
        print(json.dumps(result,indent=2))
    except Exception as error:
        print(json.dumps(dict(status='error',error=type(error).__name__,reason=str(error))));raise SystemExit(1)
