"""Explicit V6 model / V11 orientation-noise fallback experiment; no human-mask inputs.

Source -> configured COLFISPOOF -> V6 local/global context -> body-owner geometry ->
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
from infer_whole_pad_context_v6 import load_model,run as infer,protection_code_hashes as legacy_code_hashes
from train_whole_pad_context_v6 import PROTOCOL
from pad_refinement_tiles_v3 import check_tiles
from pad_refinement_data_contract_v2 import read_mask,native_shape
from photo_learned_pad_pipeline_v1 import save_result,pixel_hash
from photo_learned_pad_pipeline_v11 import evaluate_learned_mask,VERSION as PIPELINE_VERSION
import photo_region_pipeline_v1 as shared

VERSION='single_photo_whole_pad_context_noise_v1_experimental'


def protection_code_hashes():
    code=legacy_code_hashes()
    for name in ['photo_orientation_separated_pitch_v1.py','photo_learned_pad_pipeline_v11.py',Path(__file__).name]:
        code[name]=digest(Path(__file__).with_name(name))
    return code


def protect_bundle(folder,root,output,detect_only=False):
    folder,root,output=Path(folder),Path(root),Path(output)
    if type(detect_only) is not bool:raise ValueError('detect_only_flag_must_be_boolean')
    if output.exists():raise FileExistsError('fresh_context_protection_output_required')
    code=protection_code_hashes();predictions=infer(folder,root,output/'predictions')
    manifest,sha=json_snapshot(root/'manifest.input.private.json')
    if sha!=predictions['input_manifest_sha256']:raise ValueError('prediction_manifest_binding_mismatch')
    rows=[];indexed={r['source_id']:r for r in predictions['rows']}
    for source in manifest['sources']:
        sid=source['source_id'];path=output/'predictions'/(sid+'.png')
        mask=read_mask(path,indexed[sid]['prediction_sha256'],native_shape(source))
        returned,report=evaluate_learned_mask(source,mask,pixel_hash(mask),detect_only=detect_only)
        report.update(model_sha256=predictions['model_sha256'],model_training_version=PROTOCOL['version'],GT_used=False)
        save_result(output/sid,returned,report);rows.append(report)
    unchanged(root/'manifest.input.private.json',sha);check_tiles(root,manifest,'inference')
    if protection_code_hashes()!=code:raise ValueError('context_protection_code_changed')
    report=dict(version=PIPELINE_VERSION,rows=rows,model_sha256=predictions['model_sha256'],
        default_pipeline_enabled=False,approved_for_protection=False,independent_final_test=False)
    (output/'protection.private.json').write_text(json.dumps(report,indent=2),encoding='utf-8');return report

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


def run(source,model,registry_path,output,*,photo_semantics=None,detect_only=False):
    if type(detect_only) is not bool:raise ValueError('detect_only_flag_must_be_boolean')
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
    results=protect_bundle(model,private/'dataset',private/'protection',detect_only)
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
        model_probability_calibrated=False,detector_decision_boundary_equivalent_to_V4=False,
        experimental_global_context=True,experimental_multiscale_observation=True,experimental_component_local_gate=True,
        experimental_orientation_noise_fallback=True,legacy_V10_successes_preferred=True,
        rejected_candidates_present=report['fingerprints_rejected']>0,
        RGB_outside_accepted_permission_preserved=True)
    (output/'result.private.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return returned,report


if __name__=='__main__':
    from protect_fingerprint import JSONArgumentParser,cli_progress_to_stderr
    p=JSONArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True)
    p.add_argument('--model',type=Path,required=True);p.add_argument('--consumed-registry',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--photo-semantics',type=Path)
    p.add_argument('--detect-only',action='store_true')
    a=p.parse_args()
    try:
        with cli_progress_to_stderr():_,result=run(a.input,a.model,a.consumed_registry,a.output,photo_semantics=a.photo_semantics,
            detect_only=a.detect_only)
        print(json.dumps(result,indent=2))
    except Exception as error:
        print(json.dumps(dict(status='error',error=type(error).__name__,reason=str(error))))
        raise SystemExit(1)
