"""New group-development run; all numeric training rules remain V3-compatible."""
import argparse,json,platform
from pathlib import Path
from types import MappingProxyType
from importlib.metadata import version as package_version
import numpy as np
import torch
from PIL import Image
from pad_whole_target_training_v4 import check,VERSION
from pad_refinement_data_contract_v2 import read_gt,digest
from pad_refinement_tiles_v3 import json_snapshot,unchanged,hash_json
import train_pad_refinement_tiles_v3 as common
from pad_refinement_model import build_pretrained
from train_pad_refinement import optimizer,seed_all
from pad_refinement_tiles_v3 import check_input_source
from photo_resize_safety_v1 import MAX_ESTIMATED_WORKING_BYTES

PROTOCOL=MappingProxyType(dict(common.PROTOCOL)|dict(version='whole_pad_target_training_v4_development',
    dataset_contract=VERSION,new_data_group='one conservative reviewed archive cluster; acquisition/person independence unverified',
    label_policy='legacy pad boundaries retained; new explicitly reviewed whole distal pads',
    validation_inputs='verified immutable GT-free in-memory snapshot; same V3 forward and merge',
    evaluation='separate legacy/new policy metrics; group-heldout development early stopping, not a final test'))
PROTOCOL_SHA256=hash_json(dict(PROTOCOL))


def code_hashes():
    return common.code_hashes()|{n:digest(Path(__file__).with_name(n)) for n in [
        'train_whole_pad_target_v4.py','pad_whole_target_training_v4.py','import_whole_pad_annotations_v1.py']}


def asset_bindings(root,manifest,view,weights):
    pairs=[]
    for source in view['sources']:
        pairs.extend((source[p],source[h]) for p,h in [('source_path','source_sha256'),('body_path','body_sha256'),
            ('tip_path','tip_sha256'),('semantics_path','semantics_sha256'),('coarse_path','coarse_sha256')])
    for source in manifest['sources']:
        pairs.extend([(str(Path(source['GT_folder'])/'source.json'),source['GT_metadata_sha256']),
                      (str(Path(source['GT_folder'])/'ground_truth_mask.png'),source['GT_mask_sha256'])])
    for record in manifest['crops']+view['crops']:pairs.append((str(Path(root)/record['path']),record['file_sha256']))
    evidence=manifest['group_evidence']
    pairs.extend((evidence[p],evidence[h]) for p,h in [('legacy_manifest_path','legacy_manifest_sha256'),('import_report_path','import_report_sha256')])
    pairs.append((str(weights),digest(weights)))
    indexed={}
    for path,expected in pairs:
        absolute=str(Path(path).resolve())
        if absolute in indexed and indexed[absolute]!=expected:raise ValueError('inconsistent_training_asset_binding')
        indexed[absolute]=expected
    return indexed


def assert_assets(bindings):
    for path,expected in bindings.items():unchanged(path,expected)


class PreparedInputs:
    """No annotations are available in this interface. Assets remain hash-bound."""
    def __init__(self,root,view):
        if view.get('purpose')!='inference' or view.get('GT_present') is not False:raise ValueError('GT_free_prediction_view_required')
        planned=sum(s['height']*s['width'] for s in view['sources'])+len(view['crops'])*256*256*5
        if planned>MAX_ESTIMATED_WORKING_BYTES:raise ValueError('prediction_cache_resource_limit')
        self.sources={}
        for source in view['sources']:
            records=[r for r in view['crops'] if r['source_id']==source['source_id']]
            body,arrays=check_input_source(root,source,records,view['consumed_registry'])
            body.setflags(write=False)
            for values in arrays:
                for value in values.values():value.setflags(write=False)
            self.sources[source['source_id']]=(body,records,arrays)

    def predict(self,model,sid):
        body,records,arrays=self.sources[sid];values=[];model.eval()
        with torch.no_grad():
            for start in range(0,len(records),common.PROTOCOL['batch_size']):
                # Copy read-only uint8 buffers before Torch conversion; neither
                # the caller nor model receives writable cached input arrays.
                x=torch.stack([common.normalized_input({k:v.copy() for k,v in a.items()}) for a in arrays[start:start+common.PROTOCOL['batch_size']]])
                logits=model(x)
                if logits.shape!=(len(x),1,256,256) or not torch.isfinite(logits).all():raise ValueError('tile_model_output_contract')
                values.extend(logits.sigmoid().cpu().numpy()[:,0])
        probability=common.restore_probability_mean(body,records,values)
        return (probability>=common.PROTOCOL['threshold'])&body


def validation(model,root,manifest,view,ids,save=None,prepared=None):
    rows=[];sources={s['source_id']:s for s in manifest['sources']}
    for sid in sorted(ids):
        pred=prepared.predict(model,sid) if prepared is not None else common.predict_source(model,root,view,sid)
        row=dict(source_id=sid,policy=sources[sid]['GT_policy'],**common.source_metrics(pred,read_gt(sources[sid])))
        if save is not None:
            Image.fromarray(pred.astype(np.uint8)*255).save(save/(sid+'.png'))
            row['mask_pixel_sha256']=__import__('hashlib').sha256(pred.tobytes()).hexdigest()
        rows.append(row)
    return dict(rows=rows,source_macro_iou=float(np.mean([r['iou'] for r in rows])),
        source_macro_dice=float(np.mean([r['dice'] for r in rows])),
        policy_macro_iou={p:float(np.mean([r['iou'] for r in rows if r['policy']==p])) for p in {r['policy'] for r in rows}})


def train(root,weights,output):
    root=Path(root);output=Path(output)
    manifest_path=root/'manifest.whole.private.json';manifest,manifest_sha=json_snapshot(manifest_path)
    input_path=root/'manifest.input.private.json';view,input_sha=json_snapshot(input_path)
    view=check(root,manifest);code_sha=code_hashes()
    # Reused helpers must retain precisely the declared shared numeric rules.
    for key,value in common.PROTOCOL.items():
        if key not in ['version','dataset_contract'] and PROTOCOL[key]!=value:raise ValueError('shared_numeric_protocol_mismatch')
    if output.exists():raise FileExistsError('fresh_whole_pad_training_output_required')
    unchanged(manifest_path,manifest_sha);unchanged(input_path,input_sha)
    assets=asset_bindings(root,manifest,view,weights)
    assert_assets(assets)
    if code_hashes()!=code_sha:raise ValueError('frozen_run_inputs_or_code_changed')
    seed_all(PROTOCOL['seed']);probe,encoder_sha=build_pretrained(weights);del probe
    frozen=dict(protocol=dict(PROTOCOL),protocol_sha256=PROTOCOL_SHA256,source_code_sha256=code_sha,
        manifest_sha256=manifest_sha,input_manifest_sha256=input_sha,encoder_sha256=encoder_sha,
        consumed_registry_sha256=view['consumed_registry_sha256'],group_split_sha256=hash_json(manifest['group_split_plan']),
        splits=manifest['group_split_plan']['folds'],development_only=True,independent_final_test=False,
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
            loss=common.train_epoch(model,loader,opt);metric=validation(model,root,manifest,view,split['validation'],prepared=prepared);score=metric['source_macro_iou']
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
        loss=common.train_epoch(model,loader,opt);stable();history.append(dict(epoch=step,loss=loss))
        print(json.dumps(dict(stage='final',epoch=step,epochs=epochs,loss=loss)),flush=True)
    check(root,manifest);stable();model_sha=common.save_checkpoint(model,output/'final_whole_pad.pt');stable()
    config=frozen|dict(training_complete=True,approved_for_inference=False,model_sha256=model_sha,final_epochs=epochs,
        training_source_ids=ids,history=history,architecture='unchanged V3 MobileNetV3-small plus decoder',
        input_geometry='unchanged GT-free V3 native-body tiles',threshold=common.PROTOCOL['threshold'])
    (output/'final_config.private.json').write_text(json.dumps(config,indent=2),encoding='utf-8')
    return config


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for n in ['dataset','encoder-weights','output']:parser.add_argument('--'+n,type=Path,required=True)
    args=parser.parse_args();train(args.dataset,args.encoder_weights,args.output)
