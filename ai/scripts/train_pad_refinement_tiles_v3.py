"""Development-only group-heldout tile training. No historical test labels."""
import argparse
import io
import json
import platform
from importlib.metadata import version as package_version
from pathlib import Path
from types import MappingProxyType
import numpy as np
from PIL import Image
import torch
import torch.nn.functional as F
from torch.utils.data import Dataset,DataLoader

from pad_refinement_model import build_pretrained,PadRefinement
from torchvision.models import mobilenet_v3_small
from train_pad_refinement import Crops,optimizer,seed_all
from pad_refinement_data_contract_v2 import checked_bytes,digest,read_gt
from pad_refinement_tiles_v3 import (VERSION,CROP_POLICY,MERGE,hash_json,input_view,
    check_tiles,check_header,check_input_source,json_snapshot,unchanged)
from pad_refinement_experiment_plan_v2 import POLICY_SHA256

PROTOCOL=MappingProxyType(dict(version='tile_group_training_v3_development',seed=20261015,
    max_epochs=40,patience=6,batch_size=4,device='cpu',threads=8,threshold=.5,
    input_size=256,decoder_lr=.001,input_conv_lr=.0001,weight_decay=.0001,
    loss='per-example BCE + smoothed Dice',crop_policy=CROP_POLICY,merge_policy=MERGE,
    tile_policy_sha256=POLICY_SHA256,dataset_contract=VERSION,
    sampling='all tiles once per epoch, seeded shuffle, no target-based sampling',
    source_weight='T/(S*n_source); no per-batch weight renormalization',
    step_loss='weighted sum / configured batch size, including final partial batch',
    validation='full native source macro IoU; group-disjoint developmental early stopping',
    final_epoch_rule='floor median of group best epochs; earliest strict-IoU tie',
    encoder='official MobileNetV3-small ImageNet1K V1; input conv trainable, other encoder frozen/BN eval',
    augmentation='unchanged historical RGB/coarse/label aligned augmentation',
    independent_final_test=False,approved_for_inference=False))
PROTOCOL_SHA256=hash_json(dict(PROTOCOL))


def finite_model(model,gradients=False):
    for tensor in list(model.parameters())+list(model.buffers()):
        if not torch.isfinite(tensor).all():raise ValueError('nonfinite_model_state')
        if gradients and getattr(tensor,'grad',None) is not None and not torch.isfinite(tensor.grad).all():
            raise ValueError('nonfinite_model_gradient')


def per_example_loss(logits,target):
    if logits.shape!=target.shape or logits.ndim!=4 or logits.shape[1:]!=(1,256,256):
        raise ValueError('tile_logits_target_shape')
    if not torch.isfinite(logits).all() or not torch.isfinite(target).all():raise ValueError('nonfinite_loss_input')
    probability=logits.sigmoid();axes=(1,2,3)
    intersection=(probability*target).sum(axes);denominator=probability.sum(axes)+target.sum(axes)
    return F.binary_cross_entropy_with_logits(logits,target,reduction='none').mean(axes)+(1-(2*intersection+1)/(denominator+1))


def source_weights(records):
    if not records:raise ValueError('empty_training_tiles')
    counts={sid:sum(r['source_id']==sid for r in records) for sid in {r['source_id'] for r in records}}
    return [len(records)/(len(counts)*counts[r['source_id']]) for r in records]


class WeightedTiles(Dataset):
    def __init__(self,root,manifest,ids):
        self.data=Crops(root,manifest,ids,True);self.weights=source_weights(self.data.records)
    def __len__(self):return len(self.data)
    def __getitem__(self,index):
        x,y=self.data[index];return x,y,torch.tensor(self.weights[index],dtype=torch.float32)


def make_loader(root,manifest,ids,seed):
    data=WeightedTiles(root,manifest,ids)
    return DataLoader(data,batch_size=PROTOCOL['batch_size'],shuffle=True,
                      generator=torch.Generator().manual_seed(seed),num_workers=0)


def train_epoch(model,loader,opt):
    model.train();total=0.;count=0
    for x,y,weight in loader:
        opt.zero_grad();losses=per_example_loss(model(x),y);weighted=losses*weight
        loss=weighted.sum()/PROTOCOL['batch_size']
        if not torch.isfinite(loss):raise ValueError('nonfinite_training_loss')
        loss.backward();finite_model(model,True);opt.step();finite_model(model)
        total+=float(weighted.detach().sum());count+=len(x)
    if not count:raise ValueError('empty_training_loader')
    return total/count


def normalized_input(arrays):
    rgb=torch.from_numpy(arrays['rgb']).permute(2,0,1).float()/255
    rgb=(rgb-torch.tensor([.485,.456,.406])[:,None,None])/torch.tensor([.229,.224,.225])[:,None,None]
    return torch.cat([rgb,torch.from_numpy(arrays['coarse']).float()[None]])


def restore_probability_mean(body,records,values):
    if body.ndim!=2 or body.dtype!=np.bool_ or not records or len(records)!=len(values) or len(records)>256:
        raise ValueError('probability_merge_contract')
    probability=np.zeros(body.shape,np.float32);count=np.zeros(body.shape,np.uint16)
    for record,small in zip(records,values):
        if small.shape!=(256,256) or not np.isfinite(small).all() or small.min()<0 or small.max()>1:
            raise ValueError('tile_probability_contract')
        g=record['geometry'];window=small[g['top']:g['top']+g['scaled_height'],g['left']:g['left']+g['scaled_width']]
        native=np.asarray(Image.fromarray(window.astype(np.float32)).resize((g['width'],g['height']),Image.Resampling.BILINEAR))
        a,b,c,d=record['bbox']
        if not (0<=a<c<=body.shape[1] and 0<=b<d<=body.shape[0]) or native.shape!=(d-b,c-a):
            raise ValueError('native_probability_bbox_contract')
        probability[b:d,a:c]+=native;count[b:d,a:c]+=1
    if np.any(body & (count==0)):raise ValueError('incomplete_native_body_prediction_coverage')
    np.divide(probability,count,out=probability,where=count>0)
    if not np.isfinite(probability).all():raise ValueError('nonfinite_native_probability')
    return probability


def predict_source(model,root,manifest,sid):
    """Only the separate zero-label input assets are read, even during CV."""
    view=input_view(manifest);check_header(view,'inference')
    source=next(s for s in view['sources'] if s['source_id']==sid)
    records=[r for r in view['crops'] if r['source_id']==sid]
    body,arrays=check_input_source(root,source,records,view['consumed_registry'])
    values=[]
    model.eval()
    with torch.no_grad():
        for start in range(0,len(records),PROTOCOL['batch_size']):
            batch=arrays[start:start+PROTOCOL['batch_size']]
            x=torch.stack([normalized_input(a) for a in batch]);logits=model(x)
            if logits.shape!=(len(batch),1,256,256) or not torch.isfinite(logits).all():raise ValueError('tile_model_output_contract')
            values.extend(logits.sigmoid().cpu().numpy()[:,0])
    probability=restore_probability_mean(body,records,values)
    return (probability>=PROTOCOL['threshold'])&body


def source_metrics(pred,gt):
    if pred.shape!=gt.shape or pred.dtype!=np.bool_ or gt.dtype!=np.bool_:raise ValueError('native_metric_mask_contract')
    tp=int((pred&gt).sum());fp=int((pred&~gt).sum());fn=int((gt&~pred).sum())
    return dict(iou=tp/max(1,tp+fp+fn),dice=2*tp/max(1,int(pred.sum()+gt.sum())),
                precision=tp/int(pred.sum()) if pred.any() else None,recall=tp/int(gt.sum()),
                true_positive_pixels=tp,false_positive_pixels=fp,false_negative_pixels=fn)


def validation(model,root,manifest,ids,save=None):
    rows=[];sources={s['source_id']:s for s in manifest['sources']}
    for sid in sorted(ids):
        pred=predict_source(model,root,manifest,sid) # prediction before targets
        row=dict(source_id=sid,**source_metrics(pred,read_gt(sources[sid])))
        if save is not None:
            Image.fromarray(pred.astype(np.uint8)*255).save(save/(sid+'.png'))
            row['mask_pixel_sha256']=__import__('hashlib').sha256(pred.tobytes()).hexdigest()
        rows.append(row)
    return dict(rows=rows,source_macro_iou=float(np.mean([r['iou'] for r in rows])),
                source_macro_dice=float(np.mean([r['dice'] for r in rows])))


def code_hashes():
    return {name:digest(Path(__file__).with_name(name)) for name in [
        'train_pad_refinement_tiles_v3.py','pad_refinement_tiles_v3.py','pad_refinement_model.py',
        'pad_refinement_experiment_plan_v2.py','pad_refinement_data_contract_v2.py','train_pad_refinement.py',
        'prepare_pad_refinement_data.py','finger_body_distal_estimator.py','infer_pad_refinement_tiles_v3.py',
        'photo_resize_safety_v1.py']}


def save_checkpoint(model,path):
    finite_model(model);torch.save(model.state_dict(),path);return digest(path)


def load_checkpoint(path,expected):
    data=checked_bytes(path,expected);model=PadRefinement(mobilenet_v3_small(weights=None))
    model.load_state_dict(torch.load(io.BytesIO(data),map_location='cpu',weights_only=True),strict=True)
    finite_model(model);model.eval();return model


def train(root,weights,output):
    manifest_path=root/'manifest.private.json';manifest,manifest_sha=json_snapshot(manifest_path)
    input_path=root/'manifest.input.private.json';published,input_sha=json_snapshot(input_path)
    code_sha=code_hashes()
    check_tiles(root,manifest,'training')
    if hash_json(published)!=hash_json(input_view(manifest)):raise ValueError('published_input_manifest_mismatch')
    check_tiles(root,published,'inference')
    if output.exists():raise FileExistsError('fresh_training_output_required')
    unchanged(manifest_path,manifest_sha);unchanged(input_path,input_sha)
    if code_hashes()!=code_sha:raise ValueError('frozen_run_inputs_or_code_changed')
    seed_all(PROTOCOL['seed']);probe,encoder_sha=build_pretrained(weights);del probe
    frozen=dict(protocol=dict(PROTOCOL),protocol_sha256=PROTOCOL_SHA256,
                manifest_sha256=manifest_sha,input_manifest_sha256=input_sha,
                consumed_registry_sha256=manifest['consumed_registry_sha256'],
                group_split_sha256=hash_json(manifest['group_split_plan']),source_code_sha256=code_sha,
                encoder_sha256=encoder_sha,runtime=dict(python=platform.python_version(),platform=platform.platform(),
                    device='cpu',threads=torch.get_num_threads(),
                    packages={name:package_version(name) for name in ['torch','torchvision','numpy','Pillow','opencv-python-headless','scipy','scikit-image']}),
                splits=manifest['group_split_plan']['folds'],development_only=True,independent_final_test=False)
    output.mkdir(parents=True,exist_ok=False)
    (output/'frozen_protocol.private.json').write_text(json.dumps(frozen,indent=2),encoding='utf-8')
    best=[];oof=[]
    for index,split in enumerate(frozen['splits'],1):
        folder=output/f'fold_{index}';folder.mkdir();seed_all(PROTOCOL['seed']+index)
        model,_=build_pretrained(weights);opt=optimizer(model);loader=make_loader(root,manifest,split['train'],PROTOCOL['seed']+index)
        best_score=-1.;best_epoch=0;stale=0;history=[];best_sha=None
        for step in range(1,PROTOCOL['max_epochs']+1):
            loss=train_epoch(model,loader,opt);metric=validation(model,root,manifest,split['validation']);score=metric['source_macro_iou']
            if not np.isfinite(score):raise ValueError('nonfinite_validation_metric')
            if score>best_score:
                best_score=score;best_epoch=step;stale=0;best_sha=save_checkpoint(model,folder/'best.pt')
            else:stale+=1
            history.append(dict(epoch=step,loss=loss,validation=metric))
            (folder/'history.private.json').write_text(json.dumps(history,indent=2),encoding='utf-8')
            print(json.dumps(dict(fold=index,epoch=step,loss=loss,source_macro_iou=score,best_epoch=best_epoch,stale=stale)),flush=True)
            if stale>=PROTOCOL['patience']:break
        del model,opt
        model=load_checkpoint(folder/'best.pt',best_sha);predictions=folder/'oof_masks';predictions.mkdir()
        metric=validation(model,root,manifest,split['validation'],predictions);oof.extend(metric['rows'])
        best.append(dict(fold=index,best_epoch=best_epoch,best_sha256=best_sha,validation=metric,split=split))
        del model
    ids=[s['source_id'] for s in manifest['sources']]
    if len(oof)!=len(ids) or {r['source_id'] for r in oof}!=set(ids):raise ValueError('complete_unique_OOF_sources_required')
    epochs=int(np.floor(np.median([b['best_epoch'] for b in best])))
    cv=dict(folds=best,OOF_source_macro_iou=float(np.mean([r['iou'] for r in oof])),
            OOF_source_macro_dice=float(np.mean([r['dice'] for r in oof])),
            group_macro_iou=float(np.mean([b['validation']['source_macro_iou'] for b in best])),
            final_epochs=epochs,rows=oof,development_only=True,independent_final_test=False)
    (output/'cross_validation.private.json').write_text(json.dumps(cv,indent=2),encoding='utf-8')
    seed_all(PROTOCOL['seed']);model,_=build_pretrained(weights);opt=optimizer(model)
    loader=make_loader(root,manifest,ids,PROTOCOL['seed']);history=[]
    for step in range(1,epochs+1):
        loss=train_epoch(model,loader,opt);history.append(dict(epoch=step,loss=loss))
        print(json.dumps(dict(final_epoch=step,loss=loss)),flush=True)
    check_tiles(root,manifest,'training')
    if (digest(manifest_path)!=frozen['manifest_sha256'] or digest(root/'manifest.input.private.json')!=frozen['input_manifest_sha256'] or
            code_hashes()!=frozen['source_code_sha256']):raise ValueError('frozen_run_inputs_or_code_changed')
    model_sha=save_checkpoint(model,output/'final_tiles.pt')
    config=frozen | dict(training_complete=True,model_sha256=model_sha,final_epochs=epochs,history=history,
                         approved_for_inference=False,crop_policy=CROP_POLICY,merge_policy=MERGE,tile_policy_sha256=POLICY_SHA256)
    (output/'final_config.private.json').write_text(json.dumps(config,indent=2),encoding='utf-8')
    return cv


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--dataset',type=Path,required=True)
    p.add_argument('--encoder-weights',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    train(a.dataset,a.encoder_weights,a.output)
