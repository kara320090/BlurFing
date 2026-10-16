"""Explicit GT-free V6 context model inference; never enabled by default."""
import argparse,json
from pathlib import Path
import numpy as np
from PIL import Image
from train_whole_pad_context_v6 import PROTOCOL,PROTOCOL_SHA256,code_hashes
from whole_pad_context_model_v6 import load_checkpoint,encoder_identity
from whole_pad_context_inputs_v6 import ContextInputs
from train_pad_refinement_tiles_v3 import finite_model
from train_pad_refinement import seed_all
from pad_refinement_tiles_v3 import json_snapshot,unchanged,check_tiles,hash_json
from pad_refinement_data_contract_v2 import digest


def checkpoint_source_compatibility(expected, actual):
    """Only the audited additive inference validator may differ from training.

    Commit 4d5ec82 adds RGB_REFINED_BODY_V1 provenance validation. Removing
    that exact branch reproduces the previous bytes; original training inputs
    still take the identical branch. Neither model nor training record is edited.
    Unknown revisions, other changed files and changed file sets stay rejected.
    """
    if not isinstance(expected,dict) or set(expected)!=set(actual): return None
    changed={name for name in actual if actual[name]!=expected[name]}
    if not changed: return dict(mode='exact_training_sources',compatible_changes=[])
    name='pad_refinement_data_contract_v2.py'
    old='aa45082f18f3b9e7d90364bb4f420e5f930de28c71961df95669f494cb693f37'
    new='5d95e3fec9e5c47eeccecc2575ede5b342881aa46f4da6782279b31fd2757c1b'
    if changed!={name} or expected[name]!=old or actual[name]!=new: return None
    return dict(mode='audited_additive_inference_validator',compatible_changes=[dict(
        file=name,training_sha256=old,runtime_sha256=new,
        reason='RGB_REFINED_BODY_V1 validation only; original training branch unchanged')])


def load_model(folder):
    folder=Path(folder);config,sha=json_snapshot(folder/'final_config.private.json')
    runtime_code=code_hashes()
    if (config.get('training_complete') is not True or config.get('development_only') is not True or
        config.get('approved_for_inference') is not False or config.get('independent_final_test') is not False or
        config.get('protocol')!=dict(PROTOCOL) or config.get('protocol_sha256')!=PROTOCOL_SHA256 or
        hash_json(config.get('protocol'))!=PROTOCOL_SHA256 or
        checkpoint_source_compatibility(config.get('source_code_sha256'),runtime_code) is None or
        config.get('threshold')!=.5): raise ValueError('completed_whole_pad_context_V6_development_checkpoint_required')
    seed_all(PROTOCOL['seed']);model=load_checkpoint(folder/'final_context_whole_pad.pt',config['model_sha256'])
    if encoder_identity(model.context_encoder)!=config.get('context_encoder_sha256'): raise ValueError('context_checkpoint_encoder_mismatch')
    if code_hashes()!=runtime_code: raise ValueError('context_runtime_sources_changed_during_load')
    unchanged(folder/'final_config.private.json',sha);return model,config


def protection_code_hashes():
    from protect_photo_whole_pad_v3 import PROTECTION_FILES
    names=set(PROTECTION_FILES)|set(code_hashes())|{'infer_whole_pad_context_v6.py','protect_photo_whole_pad_context_v4.py'}
    return {n:digest(Path(__file__).with_name(n)) for n in sorted(names)}


def run(folder,root,output):
    folder,root,output=Path(folder),Path(root),Path(output)
    manifest,manifest_sha=json_snapshot(root/'manifest.input.private.json');check_tiles(root,manifest,'inference')
    runtime_code=code_hashes();model,config=load_model(folder)
    compatibility=checkpoint_source_compatibility(config.get('source_code_sha256'),runtime_code)
    if compatibility is None or code_hashes()!=runtime_code: raise ValueError('context_runtime_sources_changed_during_load')
    if config['consumed_registry_sha256']!=manifest['consumed_registry_sha256']: raise ValueError('frozen_consumed_registry_mismatch')
    if output.exists(): raise FileExistsError('fresh_context_prediction_output_required')
    code=digest(Path(__file__));cfg_sha=digest(folder/'final_config.private.json')
    prepared=ContextInputs(root,manifest,model);prepared.assert_unchanged(model)
    output.mkdir(parents=True,exist_ok=False);rows=[]
    for source in manifest['sources']:
        pred=prepared.predict(model,source['source_id']);finite_model(model)
        path=output/(source['source_id']+'.png');Image.fromarray(pred.astype(np.uint8)*255).save(path)
        rows.append(dict(source_id=source['source_id'],source_sha256=source['source_sha256'],prediction_sha256=digest(path),
            native_shape=list(pred.shape),body_exterior_pixels=0,development_only=True))
    prepared.assert_unchanged(model);check_tiles(root,manifest,'inference')
    unchanged(root/'manifest.input.private.json',manifest_sha);unchanged(folder/'final_config.private.json',cfg_sha)
    unchanged(folder/'final_context_whole_pad.pt',config['model_sha256']);unchanged(Path(__file__),code)
    if code_hashes()!=runtime_code: raise ValueError('frozen_context_inputs_or_code_changed')
    report=dict(model_sha256=config['model_sha256'],input_manifest_sha256=manifest_sha,rows=rows,GT_used=False,
        context_encoder_sha256=prepared.encoder_sha256,context_bindings=prepared.bindings,
        development_only=True,independent_final_test=False,approved_for_protection=False,
        inference_code_sha256=code,model_probability_calibrated=False,
        checkpoint_source_compatibility=compatibility,runtime_training_dependency_sha256=runtime_code)
    (output/'inference.private.json').write_text(json.dumps(report,indent=2),encoding='utf-8');return report


def protect_bundle(folder,root,output,detect_only=False):
    from photo_learned_pad_pipeline_v10 import evaluate_learned_mask,VERSION
    from photo_learned_pad_pipeline_v1 import save_result,pixel_hash
    from pad_refinement_data_contract_v2 import read_mask,native_shape
    folder,root,output=Path(folder),Path(root),Path(output)
    if type(detect_only) is not bool: raise ValueError('detect_only_flag_must_be_boolean')
    if output.exists(): raise FileExistsError('fresh_context_protection_output_required')
    code=protection_code_hashes();predictions=run(folder,root,output/'predictions')
    manifest,sha=json_snapshot(root/'manifest.input.private.json')
    if sha!=predictions['input_manifest_sha256']: raise ValueError('prediction_manifest_binding_mismatch')
    rows=[];indexed={r['source_id']:r for r in predictions['rows']}
    for source in manifest['sources']:
        sid=source['source_id'];path=output/'predictions'/(sid+'.png')
        mask=read_mask(path,indexed[sid]['prediction_sha256'],native_shape(source))
        returned,report=evaluate_learned_mask(source,mask,pixel_hash(mask),detect_only=detect_only)
        report.update(model_sha256=predictions['model_sha256'],model_training_version=PROTOCOL['version'],GT_used=False)
        save_result(output/sid,returned,report);rows.append(report)
    unchanged(root/'manifest.input.private.json',sha);check_tiles(root,manifest,'inference')
    if protection_code_hashes()!=code: raise ValueError('context_protection_code_changed')
    report=dict(version=VERSION,rows=rows,model_sha256=predictions['model_sha256'],
        default_pipeline_enabled=False,approved_for_protection=False,independent_final_test=False)
    (output/'protection.private.json').write_text(json.dumps(report,indent=2),encoding='utf-8');return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['model','inputs','output']: parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--protect',action='store_true');args=parser.parse_args()
    if args.protect: protect_bundle(args.model,args.inputs,args.output)
    else: run(args.model,args.inputs,args.output)
