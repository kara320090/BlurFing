"""Explicit unapproved V5 balanced whole-pad checkpoint inference."""
import argparse,json
from pathlib import Path
import numpy as np
from PIL import Image
from train_whole_pad_target_v5 import PROTOCOL,PROTOCOL_SHA256,code_hashes
from train_pad_refinement_tiles_v3 import load_checkpoint,predict_source,finite_model
from train_pad_refinement import seed_all
from pad_refinement_tiles_v3 import json_snapshot,unchanged,check_tiles,hash_json
from pad_refinement_data_contract_v2 import digest


def load_model(folder):
    folder=Path(folder);config,sha=json_snapshot(folder/'final_config.private.json')
    if (config.get('training_complete') is not True or config.get('development_only') is not True or
            config.get('approved_for_inference') is not False or config.get('independent_final_test') is not False or
            config.get('protocol')!=dict(PROTOCOL) or config.get('protocol_sha256')!=PROTOCOL_SHA256 or
            hash_json(config.get('protocol'))!=PROTOCOL_SHA256 or config.get('source_code_sha256')!=code_hashes() or
            config.get('threshold')!=.5):raise ValueError('completed_whole_pad_V5_development_checkpoint_required')
    seed_all(PROTOCOL['seed']);model=load_checkpoint(folder/'final_balanced_whole_pad.pt',config['model_sha256'])
    unchanged(folder/'final_config.private.json',sha);return model,config


def run(folder,root,output):
    folder,root,output=Path(folder),Path(root),Path(output)
    manifest,manifest_sha=json_snapshot(root/'manifest.input.private.json');check_tiles(root,manifest,'inference')
    model,config=load_model(folder)
    if config['consumed_registry_sha256']!=manifest['consumed_registry_sha256']:raise ValueError('frozen_consumed_registry_mismatch')
    if output.exists():raise FileExistsError('fresh_prediction_output_required')
    code=digest(Path(__file__));cfg_sha=digest(folder/'final_config.private.json');output.mkdir(parents=True,exist_ok=False);rows=[]
    for source in manifest['sources']:
        pred=predict_source(model,root,manifest,source['source_id']);finite_model(model)
        path=output/(source['source_id']+'.png');Image.fromarray(pred.astype(np.uint8)*255).save(path)
        rows.append(dict(source_id=source['source_id'],source_sha256=source['source_sha256'],prediction_sha256=digest(path),
            native_shape=list(pred.shape),body_exterior_pixels=0,development_only=True))
    check_tiles(root,manifest,'inference');unchanged(root/'manifest.input.private.json',manifest_sha)
    unchanged(folder/'final_config.private.json',cfg_sha);unchanged(folder/'final_balanced_whole_pad.pt',config['model_sha256']);unchanged(Path(__file__),code)
    if code_hashes()!=config['source_code_sha256']:raise ValueError('frozen_run_inputs_or_code_changed')
    report=dict(model_sha256=config['model_sha256'],input_manifest_sha256=manifest_sha,rows=rows,development_only=True,
        independent_final_test=False,approved_for_protection=False,inference_code_sha256=code,
        model_probability_calibrated=False,detector_decision_boundary_equivalent_to_V4=False)
    (output/'inference.private.json').write_text(json.dumps(report,indent=2),encoding='utf-8');return report


def protect_bundle(folder,root,output,detect_only=False,*,spatial_observation=False,multiscale_observation=False):
    if type(spatial_observation) is not bool or type(multiscale_observation) is not bool:raise ValueError('observation_flag_must_be_boolean')
    if spatial_observation and multiscale_observation:raise ValueError('conflicting_observation_experiments')
    import photo_learned_pad_pipeline_v8 as component
    import photo_learned_pad_pipeline_v9 as spatial
    import photo_learned_pad_pipeline_v10 as multiscale
    from photo_learned_pad_pipeline_v1 import save_result,pixel_hash
    from pad_refinement_data_contract_v2 import read_mask,native_shape
    backend=multiscale if multiscale_observation else spatial if spatial_observation else component
    folder,root,output=Path(folder),Path(root),Path(output)
    if output.exists():raise FileExistsError('fresh_protection_output_required')
    predictions=run(folder,root,output/'predictions');manifest,sha=json_snapshot(root/'manifest.input.private.json')
    if sha!=predictions['input_manifest_sha256']:raise ValueError('prediction_manifest_binding_mismatch')
    rows=[];indexed={r['source_id']:r for r in predictions['rows']}
    for source in manifest['sources']:
        sid=source['source_id'];path=output/'predictions'/(sid+'.png');mask=read_mask(path,indexed[sid]['prediction_sha256'],native_shape(source))
        returned,report=backend.evaluate_learned_mask(source,mask,pixel_hash(mask),detect_only=detect_only)
        report['model_sha256']=predictions['model_sha256'];report['model_training_version']=PROTOCOL['version']
        save_result(output/sid,returned,report);rows.append(report)
    unchanged(root/'manifest.input.private.json',sha);check_tiles(root,manifest,'inference')
    report=dict(version=backend.VERSION,rows=rows,model_sha256=predictions['model_sha256'],
        default_pipeline_enabled=False,approved_for_protection=False,independent_final_test=False)
    (output/'protection.private.json').write_text(json.dumps(report,indent=2),encoding='utf-8');return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for n in ['model','inputs','output']:parser.add_argument('--'+n,type=Path,required=True)
    args=parser.parse_args();run(args.model,args.inputs,args.output)
