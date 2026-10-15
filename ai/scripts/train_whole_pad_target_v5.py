"""Separate class-balanced whole-pad development experiment; not a V4 rewrite."""
import argparse,json,platform
from pathlib import Path
from types import MappingProxyType
from importlib.metadata import version as package_version
import numpy as np
import torch
from pad_whole_target_training_v4 import check
from pad_refinement_data_contract_v2 import digest
from pad_refinement_tiles_v3 import json_snapshot,unchanged,hash_json
import train_pad_refinement_tiles_v3 as common
from pad_refinement_model import build_pretrained
from train_pad_refinement import optimizer,seed_all
from train_whole_pad_target_v4 import (PROTOCOL as V4,code_hashes as V4_code_hashes,
    asset_bindings,assert_assets,PreparedInputs,validation)
from whole_pad_balanced_loss_v1 import class_balance,per_example_loss,VERSION as LOSS_VERSION

PROTOCOL=MappingProxyType(dict(V4)|dict(version='whole_pad_target_training_v5_balanced_development',
    loss=LOSS_VERSION,probability_calibration='weighted BCE posterior; 0.5 numeric boundary retained, unweighted decision meaning not equivalent',
    balance_estimation='train-fold-only source-weighted mean tile foreground fraction; padding included before augmentation'))
PROTOCOL_SHA256=hash_json(dict(PROTOCOL))


def code_hashes():
    return V4_code_hashes()|{n:digest(Path(__file__).with_name(n)) for n in ['train_whole_pad_target_v5.py','whole_pad_balanced_loss_v1.py']}


def train_epoch(model,loader,opt,statistics):
    model.train();total=0.;count=0
    for x,y,weight in loader:
        opt.zero_grad();weighted=per_example_loss(model(x),y,statistics)*weight
        loss=weighted.sum()/PROTOCOL['batch_size']
        if not torch.isfinite(loss):raise ValueError('nonfinite_training_loss')
        loss.backward();common.finite_model(model,True);opt.step();common.finite_model(model)
        total+=float(weighted.detach().sum());count+=len(x)
    if not count:raise ValueError('empty_training_loader')
    return total/count

def train(root,weights,output):
    root=Path(root);output=Path(output)
    manifest_path=root/'manifest.whole.private.json';manifest,manifest_sha=json_snapshot(manifest_path)
    input_path=root/'manifest.input.private.json';view,input_sha=json_snapshot(input_path)
    view=check(root,manifest);code_sha=code_hashes()
    # Reused helpers must retain precisely the declared shared numeric rules.
    for key,value in common.PROTOCOL.items():
        if key not in ['version','dataset_contract','loss'] and PROTOCOL[key]!=value:raise ValueError('shared_numeric_protocol_mismatch')
    if output.exists():raise FileExistsError('fresh_whole_pad_training_output_required')
    unchanged(manifest_path,manifest_sha);unchanged(input_path,input_sha)
    assets=asset_bindings(root,manifest,view,weights)
    assert_assets(assets)
    if code_hashes()!=code_sha:raise ValueError('frozen_run_inputs_or_code_changed')
    ids=[s['source_id'] for s in manifest['sources']]
    balances=[class_balance(root,manifest,s['train']) for s in manifest['group_split_plan']['folds']]
    final_balance=class_balance(root,manifest,ids)
    seed_all(PROTOCOL['seed']);probe,encoder_sha=build_pretrained(weights);del probe
    frozen=dict(protocol=dict(PROTOCOL),protocol_sha256=PROTOCOL_SHA256,source_code_sha256=code_sha,
        manifest_sha256=manifest_sha,input_manifest_sha256=input_sha,encoder_sha256=encoder_sha,
        consumed_registry_sha256=view['consumed_registry_sha256'],group_split_sha256=hash_json(manifest['group_split_plan']),
        splits=manifest['group_split_plan']['folds'],fold_class_balance=balances,final_class_balance=final_balance,development_only=True,independent_final_test=False,
        runtime=dict(python=platform.python_version(),platform=platform.platform(),device='cpu',threads=PROTOCOL['threads'],
            packages={n:package_version(n) for n in ['torch','torchvision','numpy','Pillow','opencv-python-headless','scipy','scikit-image']}))
    def stable():
        unchanged(manifest_path,manifest_sha);unchanged(input_path,input_sha)
        assert_assets(assets)
        if code_hashes()!=code_sha:raise ValueError('frozen_run_inputs_or_code_changed')
    stable();prepared=PreparedInputs(root,view);stable();output.mkdir(parents=True,exist_ok=False)
    (output/'frozen_protocol.private.json').write_text(json.dumps(frozen,indent=2),encoding='utf-8')
    best=[];oof=[]
    for index,split in enumerate(frozen['splits'],1):
        folder=output/f'fold_{index}';folder.mkdir();stable();seed_all(PROTOCOL['seed']+index)
        # Fresh official ImageNet initialization prevents leakage from the old
        # final GT10 model into a fold that holds out a GT10 acquisition group.
        model,_=build_pretrained(weights);opt=optimizer(model);loader=common.make_loader(root,manifest,split['train'],PROTOCOL['seed']+index)
        best_score=-1.;best_epoch=0;stale=0;history=[];best_sha=None
        for step in range(1,PROTOCOL['max_epochs']+1):
            loss=train_epoch(model,loader,opt,balances[index-1]);metric=validation(model,root,manifest,view,split['validation'],prepared=prepared);score=metric['source_macro_iou']
            if not np.isfinite(score):raise ValueError('nonfinite_whole_pad_validation')
            if score>best_score:best_score=score;best_epoch=step;stale=0;best_sha=common.save_checkpoint(model,folder/'best.pt')
            else:stale+=1
            history.append(dict(epoch=step,loss=loss,validation=metric));stable()
            (folder/'history.private.json').write_text(json.dumps(history,indent=2),encoding='utf-8')
            print(json.dumps(dict(fold=index,epoch=step,loss=loss,source_macro_iou=score,best_epoch=best_epoch,stale=stale)),flush=True)
            if stale>=PROTOCOL['patience']:break
        del model,opt
        stable();check(root,manifest);model=common.load_checkpoint(folder/'best.pt',best_sha)
        predictions=folder/'oof_masks';predictions.mkdir();metric=validation(model,root,manifest,view,split['validation'],predictions,prepared);oof.extend(metric['rows'])
        best.append(dict(fold=index,best_epoch=best_epoch,best_sha256=best_sha,validation=metric,split=split));del model
    ids=[s['source_id'] for s in manifest['sources']]
    if len(oof)!=len(ids) or {r['source_id'] for r in oof}!=set(ids):raise ValueError('complete_unique_OOF_sources_required')
    epochs=int(np.floor(np.median([b['best_epoch'] for b in best])))
    cv=dict(folds=best,OOF_source_macro_iou=float(np.mean([r['iou'] for r in oof])),
        OOF_source_macro_dice=float(np.mean([r['dice'] for r in oof])),
        group_macro_iou=float(np.mean([b['validation']['source_macro_iou'] for b in best])),
        policy_macro_iou={p:float(np.mean([r['iou'] for r in oof if r['policy']==p])) for p in {r['policy'] for r in oof}},
        final_epochs=epochs,rows=oof,development_only=True,independent_final_test=False)
    (output/'cross_validation.private.json').write_text(json.dumps(cv,indent=2),encoding='utf-8')
    seed_all(PROTOCOL['seed']);model,_=build_pretrained(weights);opt=optimizer(model);loader=common.make_loader(root,manifest,ids,PROTOCOL['seed']);history=[]
    for step in range(1,epochs+1):
        loss=train_epoch(model,loader,opt,final_balance);stable();history.append(dict(epoch=step,loss=loss))
        print(json.dumps(dict(stage='final',epoch=step,epochs=epochs,loss=loss)),flush=True)
    check(root,manifest);stable();model_sha=common.save_checkpoint(model,output/'final_balanced_whole_pad.pt');stable()
    config=frozen|dict(training_complete=True,approved_for_inference=False,model_sha256=model_sha,final_epochs=epochs,
        training_source_ids=ids,history=history,architecture='unchanged V3 MobileNetV3-small plus decoder',
        input_geometry='unchanged GT-free V3 native-body tiles',threshold=common.PROTOCOL['threshold'])
    (output/'final_config.private.json').write_text(json.dumps(config,indent=2),encoding='utf-8')
    return config


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for n in ['dataset','encoder-weights','output']:parser.add_argument('--'+n,type=Path,required=True)
    args=parser.parse_args();train(args.dataset,args.encoder_weights,args.output)
