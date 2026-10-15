"""Explicit existing distal geometry permissions with the V12 native RGB gate.

The V6 learned pad model is NOT used. No per-photo best-result selection,
threshold tuning, source-specific condition or production approval is implied.
"""
import hashlib,json,os,subprocess
from pathlib import Path
import numpy as np
from PIL import Image
import pad_refinement_tiles_v3 as tiles
from pad_refinement_data_contract_v2 import digest,read_source_rgb,read_mask,native_shape
from photo_consumed_replay_v1 import development_replay as replay_scope,consumed_roles
from protect_photo_whole_pad_context_native_v1 import canonical_rgb,protection_code_hashes as native_code_hashes
from photo_learned_pad_pipeline_v12 import evaluate_learned_mask,VERSION as GATE_VERSION
from photo_learned_pad_pipeline_v1 import pixel_hash,save_result
import photo_region_pipeline_v1 as shared

VERSION='photo_distal_native_v13_experimental'
PERMISSION='existing_COLFISPOOF_body_distal_v2'


def code_hashes():
    names=['finger_body_distal_estimator.py','pad_refinement_tiles_v3.py','photo_consumed_replay_v1.py',Path(__file__).name]
    return native_code_hashes()|{name:digest(Path(__file__).with_name(name)) for name in names}


def usage_metadata(replay):
    if type(replay) is not bool:raise ValueError('development_replay_flag_must_be_boolean')
    return dict(development_replay=replay,data_role='development_replay' if replay else 'unverified_user_input',
        independent_final_test=False,V6_learned_pad_model_used=False,permission_source=PERMISSION,
        semantic_segmentation_required=True,model_probability_calibrated=False,
        default_pipeline_enabled=False,approved_for_protection=False,privacy_validated=False,
        complete_photo_protection_verified=False,GT_used=False)


def protect_prepared(dataset,output,*,detect_only=False):
    if type(detect_only) is not bool:raise ValueError('detect_only_flag_must_be_boolean')
    dataset,output=Path(dataset),Path(output)
    if output.exists():raise FileExistsError('fresh_distal_protection_output_required')
    manifest,sha=tiles.json_snapshot(dataset/'manifest.input.private.json')
    tiles.check_tiles(dataset,manifest,'inference')
    usage=usage_metadata(manifest.get('development_replay',False));code=code_hashes()
    output.mkdir(parents=True,exist_ok=False);rows=[]
    for source in manifest['sources']:
        # Use the already published geometry-only coarse mask, never GT or V6.
        mask=read_mask(source['coarse_path'],source['coarse_sha256'],native_shape(source))
        returned,report=evaluate_learned_mask(source,mask,pixel_hash(mask),detect_only=detect_only)
        report.update(**usage,version=VERSION,protection_gate=GATE_VERSION,
            permission_file_sha256=source['coarse_sha256'],runtime_code_sha256=code)
        save_result(output/source['source_id'],returned,report);rows.append(report)
    tiles.check_tiles(dataset,manifest,'inference');tiles.unchanged(dataset/'manifest.input.private.json',sha)
    if code_hashes()!=code:raise RuntimeError('distal_runtime_code_changed_during_run')
    result=dict(version=VERSION,rows=rows,**usage)
    (output/'protection.private.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result


def run(source,registry_path,output,*,photo_semantics=None,detect_only=False,development_replay=False):
    if type(detect_only) is not bool:raise ValueError('detect_only_flag_must_be_boolean')
    usage=usage_metadata(development_replay)
    source,registry_path,output=Path(source),Path(registry_path),Path(output)
    if output.exists():raise FileExistsError('fresh_output_required')
    code=code_hashes();registry,registry_sha=tiles.json_snapshot(registry_path);tiles.validate_registry(registry)
    original_identity=tiles.image_identity(source)
    if not development_replay:tiles.exclude_consumed(original_identity,registry)
    rgb,identity=canonical_rgb(source)
    route=shared.route_input(rgb)
    if route['input_type']!='PHOTO':raise ValueError('experimental_photo_input_required')
    if photo_semantics is None:
        config=[os.environ.get(k) for k in ['BLURFING_COLFISPOOF_PYTHON','BLURFING_COLFISPOOF_SOURCE','BLURFING_COLFISPOOF_MODEL']]
        if not all(config) or not all(Path(v).exists() for v in config):raise ValueError('photo_runtime_not_configured')
    output.mkdir(parents=True,exist_ok=False);private=output/'private';private.mkdir()
    canonical=private/'canonical_input.png';exif=Image.Exif();exif[274]=identity['source_exif_orientation']
    Image.fromarray(rgb).save(canonical,exif=exif)
    if not np.array_equal(read_source_rgb(canonical,digest(canonical)),rgb):raise RuntimeError('canonical_RGB_roundtrip_mismatch')
    canonical_identity=tiles.image_identity(canonical)
    roles=sorted(set(consumed_roles(original_identity,registry)+consumed_roles(canonical_identity,registry)))
    usage.update(consumed_source_detected=bool(roles),consumed_registry_roles=roles)
    inference_source=source if photo_semantics is not None and identity['source_mode'] in ['RGB','L'] else canonical
    with replay_scope(registry,[original_identity,canonical_identity],enabled=development_replay):
        tiles.exclude_consumed(original_identity,registry);tiles.exclude_consumed(canonical_identity,registry)
        if photo_semantics is None:
            photo_semantics=private/'semantics'
            command=[config[0],str(Path(__file__).with_name('colfispoof_body_semantics.py')),
                '--input',str(inference_source.resolve()),'--output',str(photo_semantics.resolve()),
                '--external-source',config[1],'--model',config[2]]
            subprocess.run(command,shell=False,check=True,timeout=300,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        shared.load_semantics(inference_source,rgb,photo_semantics)
        inputs=[dict(source_id='INPUT',source_path=str(inference_source.resolve()),source_sha256=digest(inference_source),
            semantics=str(Path(photo_semantics).resolve()),acquisition_group='unknown',group_provenance='user_input_unverified')]
        view=tiles.prepare(inputs,registry,private/'dataset',purpose='inference');view.update(**usage)
        (private/'dataset/manifest.input.private.json').write_text(json.dumps(view,indent=2),encoding='utf-8')
        results=protect_prepared(private/'dataset',private/'protection',detect_only=detect_only)
    report=results['rows'][0]
    with Image.open(private/'protection/INPUT/returned.png') as image:returned=np.asarray(image).copy()
    if pixel_hash(returned)!=report['returned_RGB_sha256']:raise RuntimeError('returned_RGB_hash_mismatch')
    Image.fromarray(returned).save(output/'returned.png',exif=exif)
    with Image.open(output/'returned.png') as image:
        if not np.array_equal(np.asarray(image),returned):raise RuntimeError('saved_RGB_roundtrip_mismatch')
    tiles.unchanged(source,identity['original_source_sha256']);tiles.unchanged(registry_path,registry_sha)
    if code_hashes()!=code:raise RuntimeError('distal_runtime_code_changed_during_run')
    report.update(**usage,input_identity=identity,single_photo_entrypoint=VERSION,input_type='photo',route=route,
        image_width=rgb.shape[1],image_height=rgb.shape[0],output_path=str((output/'returned.png').resolve()),
        runtime_code_sha256=code,RGB_outside_accepted_permission_preserved=True)
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

