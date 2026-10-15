"""Single-photo opt-in experimental PHOTO path, with no human-mask inputs.

Source -> configured COLFISPOOF -> V3 tile model -> body-owner geometry ->
unchanged frozen protection -> actual returned RGB structure check.
The experimental model remains unapproved; rejected pixels stay original.
"""
import hashlib,json,os,subprocess
from pathlib import Path
import numpy as np
from PIL import Image
from pad_refinement_tiles_v3 import (json_snapshot,unchanged,hash_json,validate_registry,exclude_consumed,image_identity,prepare)
from pad_refinement_data_contract_v2 import digest,read_source_rgb
from photo_resize_safety_v1 import validate_resize
from infer_pad_refinement_tiles_v3 import load_model
from photo_learned_pad_pipeline_v4 import protect_bundle
import photo_region_pipeline_v1 as shared

VERSION='single_photo_learned_v1_experimental'
PROTECTION_FILES=['protect_photo_learned_v1.py','photo_learned_pad_pipeline_v1.py','photo_learned_pad_pipeline_v3.py',
    'photo_learned_pad_pipeline_v4.py','photo_native_body_scale_v1.py','photo_native_owner_context_v1.py',
    'photo_body_observation_seed_v1.py','photo_owner_partition_v1.py','photo_returned_rgb_structure_v1.py',
    'photo_region_pipeline_v1.py','photo_region_pipeline_v3.py','photo_coarse_renderer_adapter_v1.py',
    'contactless_finger_width_body_v1.py','protect_visible_pad_checked_v2.py','contactless_ridge_pitch.py',
    'fingerprint_structure_check.py','whole_pad_skin_relief.py','transform_automatic_fingerprint_poc_v4.py',
    'transform_automatic_fingerprint_poc_v4_boundaryblend_02.py','photo_learned_pad_pipeline_v7.py','photo_whole_region_structure_v1.py',
    'photo_component_local_evidence_v1.py','photo_learned_pad_pipeline_v8.py','photo_quality_gate.py',
    'highres_ridge_quality.py','diagnose_ridge_measurement_noise.py','single_ridge_naturalizer_v2.py',
    'fingerprint_poc_core.py','protect_contactless_delta.py']


def protection_code_hashes():
    return {name:hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() for name in PROTECTION_FILES}


def canonical_rgb(source):
    sha=digest(source)
    with Image.open(source) as image:
        validate_resize(image.height,image.width,1.)
        orientation=image.getexif().get(274,1);mode=image.mode
        if type(orientation) is not int or orientation not in range(1,9):raise ValueError('invalid_source_exif_orientation')
        if mode in ['RGB','L']:rgb=np.asarray(image.convert('RGB')).copy();alpha_policy='not_present'
        elif mode=='RGBA':
            # Explicit compositing, never an implicit alpha-channel discard.
            rgba=np.asarray(image).astype(np.uint32);alpha=rgba[:,:,3:4]
            rgb=((rgba[:,:,:3]*alpha+255*(255-alpha)+127)//255).astype(np.uint8)
            alpha_policy='composite_over_opaque_white_integer_round_nearest'
        else:raise ValueError('unsupported_source_mode')
    unchanged(source,sha)
    return rgb,dict(original_source_sha256=sha,source_mode=mode,source_exif_orientation=orientation,
        alpha_policy=alpha_policy,EXIF_transposed=False,coordinate_system='encoded_original_pixels',
        canonical_RGB_sha256=hashlib.sha256(rgb.tobytes()).hexdigest())


def run(source,model,registry_path,output,*,photo_semantics=None,detect_only=False,experimental_whole_region_gate=False,experimental_component_local_gate=False):
    if type(experimental_whole_region_gate) is not bool:raise ValueError('whole_region_flag_must_be_boolean')
    if type(experimental_component_local_gate) is not bool:raise ValueError('component_local_flag_must_be_boolean')
    if experimental_whole_region_gate and experimental_component_local_gate:raise ValueError('experimental_gates_are_mutually_exclusive')
    backend=protect_bundle
    if experimental_whole_region_gate:
        from photo_learned_pad_pipeline_v7 import protect_bundle as backend
    if experimental_component_local_gate:
        from photo_learned_pad_pipeline_v8 import protect_bundle as backend
    source=Path(source);model=Path(model);output=Path(output);registry_path=Path(registry_path)
    if output.exists():raise FileExistsError('fresh_output_required')
    protection_hashes=protection_code_hashes()
    registry,registry_sha=json_snapshot(registry_path);validate_registry(registry)
    # Existing consumed examples cannot silently become new evaluation data.
    exclude_consumed(image_identity(source),registry)
    rgb,identity=canonical_rgb(source)
    if shared.route_input(rgb)['input_type']!='PHOTO':raise ValueError('experimental_photo_input_required')
    network,cfg=load_model(model);del network
    if cfg['consumed_registry_sha256']!=hash_json(registry):raise ValueError('frozen_consumed_registry_mismatch')
    if photo_semantics is None:
        config=[os.environ.get(k) for k in ['BLURFING_COLFISPOOF_PYTHON','BLURFING_COLFISPOOF_SOURCE','BLURFING_COLFISPOOF_MODEL']]
        if not all(config) or not all(Path(v).exists() for v in config):raise ValueError('photo_runtime_not_configured')
    output.mkdir(parents=True,exist_ok=False);private=output/'private';private.mkdir()
    canonical=private/'canonical_input.png';exif=Image.Exif();exif[274]=identity['source_exif_orientation']
    Image.fromarray(rgb).save(canonical,exif=exif)
    if not np.array_equal(read_source_rgb(canonical,digest(canonical)),rgb):raise RuntimeError('canonical_RGB_roundtrip_mismatch')
    # Cached semantics belong to original encoded RGB/L source bytes. Keep
    # that original identity instead of relabelling a cache as canonical PNG.
    inference_source=source if photo_semantics is not None and identity['source_mode'] in ['RGB','L'] else canonical
    if photo_semantics is None:
        photo_semantics=private/'semantics'
        command=[config[0],str(Path(__file__).with_name('colfispoof_body_semantics.py')),'--input',str(inference_source.resolve()),
            '--output',str(photo_semantics.resolve()),'--external-source',config[1],'--model',config[2]]
        subprocess.run(command,shell=False,check=True,timeout=300,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    shared.load_semantics(inference_source,rgb,photo_semantics)
    inputs=[dict(source_id='INPUT',source_path=str(inference_source.resolve()),source_sha256=digest(inference_source),
                 semantics=str(Path(photo_semantics).resolve()),acquisition_group='unknown',group_provenance='user_input_unverified')]
    prepare(inputs,registry,private/'dataset',purpose='inference')
    results=backend(model,private/'dataset',private/'protection',detect_only)
    report=results['rows'][0]
    with Image.open(private/'protection/INPUT/returned.png') as image:returned=np.asarray(image).copy()
    # Decode/compare rather than copying a possibly unrelated cached file.
    if hashlib.sha256(returned.tobytes()).hexdigest()!=report['returned_RGB_sha256']:raise RuntimeError('returned_RGB_hash_mismatch')
    Image.fromarray(returned).save(output/'returned.png',exif=exif)
    with Image.open(output/'returned.png') as image:
        if not np.array_equal(np.asarray(image),returned):raise RuntimeError('saved_RGB_roundtrip_mismatch')
    unchanged(source,identity['original_source_sha256']);unchanged(registry_path,registry_sha)
    if protection_code_hashes()!=protection_hashes:raise RuntimeError('protection_code_changed_during_run')
    report|=dict(single_photo_entrypoint=VERSION,input_type='photo',input_identity=identity,
        output_path=str((output/'returned.png').resolve()),model_sha256=results['model_sha256'],
        protection_code_sha256=protection_hashes,
        GT_used=False,privacy_validated=False,complete_photo_protection_verified=False,
        experimental_whole_region_gate=experimental_whole_region_gate,
        experimental_component_local_gate=experimental_component_local_gate,
        unprotected_pixels_returned_original=report['fingerprints_rejected']>0)
    (output/'result.private.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return returned,report


if __name__=='__main__':
    from protect_fingerprint import JSONArgumentParser,cli_progress_to_stderr
    p=JSONArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True)
    p.add_argument('--model',type=Path,required=True);p.add_argument('--consumed-registry',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--photo-semantics',type=Path)
    p.add_argument('--detect-only',action='store_true')
    gates=p.add_mutually_exclusive_group()
    gates.add_argument('--experimental-whole-region-gate',action='store_true',help='Historical owner-union experiment; can share evidence across fragments')
    gates.add_argument('--experimental-component-local-gate',action='store_true',help='Opt-in per-component pitch/feature evidence; model FP still possible')
    a=p.parse_args()
    try:
        with cli_progress_to_stderr():_,result=run(a.input,a.model,a.consumed_registry,a.output,photo_semantics=a.photo_semantics,
            detect_only=a.detect_only,experimental_whole_region_gate=a.experimental_whole_region_gate,
            experimental_component_local_gate=a.experimental_component_local_gate)
        print(json.dumps(result,indent=2))
    except Exception as error:
        print(json.dumps(dict(status='error',error=type(error).__name__,reason=str(error))))
        raise SystemExit(1)
