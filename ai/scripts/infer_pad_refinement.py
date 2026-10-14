"""Hash-bound trained refinement inference; no GT inputs or threshold selection."""
import argparse,json,hashlib,time
from pathlib import Path
import numpy as np
from PIL import Image
import torch
from torchvision.models import mobilenet_v3_small
from pad_refinement_model import PadRefinement
from train_pad_refinement import native_prediction,seed_all,SEED


def load_final(folder):
    folder=Path(folder);cfg=json.loads((folder/'final_config.json').read_text());path=folder/'final_refinement.pt'
    if not cfg.get('training_complete') or cfg['threshold']!=.5:raise ValueError('completed_fixed_protocol_model_required')
    if hashlib.sha256(path.read_bytes()).hexdigest()!=cfg['model_sha256']:raise ValueError('final_model_hash_mismatch')
    seed_all(SEED);model=PadRefinement(mobilenet_v3_small(weights=None));model.load_state_dict(torch.load(path,map_location='cpu',weights_only=True),strict=True);model.eval();return model,cfg


def run(folder,crop_root,output,one_shot=False):
    model,cfg=load_final(folder);manifest=json.loads((crop_root/'manifest.private.json').read_text())
    if one_shot:
        if {s['source_id'] for s in manifest['sources']}!={'DET-01','DET-03','DET-04','DET-05','CAP-016','CAP-042','CAP-054'}:raise ValueError('exact_GT7_test_ids_required')
        # An exclusive ledger prevents repeating this model's final test after
        # reading its results. Determinism forwards occur inside this one run.
        with (folder/'GT7_one_shot_started.json').open('x') as file:json.dump(dict(model_sha256=cfg['model_sha256'],threshold=.5),file)
    output.mkdir(parents=True,exist_ok=False);rows=[]
    for source in manifest['sources']:
        sid=source['source_id']
        if Path(sid).name!=sid or sid in ['.','..']:raise ValueError('invalid_sample_id')
        path=Path(source['source_path'])
        if hashlib.sha256(path.read_bytes()).hexdigest()!=source['source_sha256']:raise ValueError('source_hash_mismatch')
        tick=time.perf_counter();pred=native_prediction(model,crop_root,manifest,sid,'cpu');duration=time.perf_counter()-tick;repeat=native_prediction(model,crop_root,manifest,sid,'cpu');assert np.array_equal(pred,repeat);body=np.asarray(Image.open(source['body_path']))>0;assert not (pred&~body).any();Image.fromarray(pred.astype(np.uint8)*255).save(output/(sid+'.png'));rows.append(dict(sample_id=sid,source_sha256=source['source_sha256'],mask_pixel_sha256=hashlib.sha256(pred.tobytes()).hexdigest(),body_exterior_pixels=0,deterministic=True,inference_seconds=duration))
    result=dict(model_sha256=cfg['model_sha256'],threshold=.5,rows=rows,device='CPU');(output/'inference.private.json').write_text(json.dumps(result,indent=2));return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--model',type=Path,required=True);p.add_argument('--crops',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--one-shot-GT7',action='store_true');a=p.parse_args();run(a.model,a.crops,a.output,a.one_shot_GT7)
