"""Explicit experimental tile inference; no target files or test-set reruns."""
import argparse,json
from pathlib import Path
from PIL import Image
import numpy as np
from train_pad_refinement_tiles_v3 import (PROTOCOL,PROTOCOL_SHA256,load_checkpoint,
    predict_source,finite_model,code_hashes)
from pad_refinement_tiles_v3 import (check_tiles,hash_json,CROP_POLICY,MERGE,json_snapshot,unchanged)
from pad_refinement_experiment_plan_v2 import POLICY_SHA256
from pad_refinement_data_contract_v2 import digest


def load_model(folder):
    cfg,cfg_sha=json_snapshot(folder/'final_config.private.json')
    if (cfg.get('training_complete') is not True or cfg.get('development_only') is not True or
            cfg.get('independent_final_test') is not False or cfg.get('approved_for_inference') is not False or
            cfg.get('protocol')!=dict(PROTOCOL) or cfg.get('protocol_sha256')!=PROTOCOL_SHA256 or
            hash_json(cfg.get('protocol'))!=PROTOCOL_SHA256 or cfg.get('crop_policy')!=CROP_POLICY or
            cfg.get('merge_policy')!=MERGE or cfg.get('tile_policy_sha256')!=POLICY_SHA256 or
            cfg.get('source_code_sha256')!=code_hashes()):
        raise ValueError('completed_V3_development_checkpoint_contract')
    model=load_checkpoint(folder/'final_tiles.pt',cfg['model_sha256'])
    unchanged(folder/'final_config.private.json',cfg_sha);return model,cfg


def run(folder,root,output):
    input_path=root/'manifest.input.private.json';manifest,input_sha=json_snapshot(input_path)
    check_tiles(root,manifest,'inference')
    if output.exists():raise FileExistsError('fresh_prediction_output_required')
    unchanged(input_path,input_sha);model,cfg=load_model(folder)
    if cfg.get('consumed_registry_sha256')!=manifest['consumed_registry_sha256']:
        raise ValueError('frozen_consumed_registry_mismatch')
    output.mkdir(parents=True,exist_ok=False);rows=[]
    for source in manifest['sources']:
        sid=source['source_id'];pred=predict_source(model,root,manifest,sid)
        finite_model(model);path=output/(sid+'.png');Image.fromarray(pred.astype(np.uint8)*255).save(path)
        rows.append(dict(source_id=sid,source_sha256=source['source_sha256'],prediction_sha256=digest(path),
                         native_shape=list(pred.shape),body_exterior_pixels=0,development_only=True))
    unchanged(input_path,input_sha)
    if cfg['source_code_sha256']!=code_hashes():raise ValueError('frozen_run_inputs_or_code_changed')
    report=dict(model_sha256=cfg['model_sha256'],input_manifest_sha256=input_sha,
                rows=rows,independent_final_test=False,approved_for_protection=False)
    (output/'inference.private.json').write_text(json.dumps(report,indent=2),encoding='utf-8');return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--model',type=Path,required=True)
    p.add_argument('--inputs',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    run(a.model,a.inputs,a.output)
