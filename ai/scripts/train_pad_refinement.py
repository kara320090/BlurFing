"""Five-fold source-level refinement training; GT7 paths are never loaded."""
import argparse,json,random,hashlib
from pathlib import Path
import numpy as np
from PIL import Image
import torch
from torch.utils.data import Dataset,DataLoader
from torchvision.transforms import functional as TF,InterpolationMode
from pad_refinement_model import build_pretrained,bce_dice

SEED=20261014
ALLOWED={'TRN-001','TRN-002','TRN-003','TRN-004','TRN-006','TRN-010','TRN-014','TRN-016','TRN-020','TRN-022'}
PROTOCOL=dict(seed=SEED,max_epochs=40,patience=6,input_size=256,batch_size=4,decoder_lr=.001,input_conv_lr=.0001,weight_decay=.0001,loss='BCE + Dice',threshold=.5,final_epoch_rule='median of five best validation epochs',encoder='MobileNetV3-small ImageNet1K V1',encoder_policy='all layers frozen except 4-channel input convolution; BatchNorm fixed eval',extra_channel_initialization='zero; RGB weights copied exactly',context_padding=.35)


def seed_all(seed):
    random.seed(seed);np.random.seed(seed);torch.manual_seed(seed);torch.use_deterministic_algorithms(True);torch.set_num_threads(8)
    if torch.cuda.is_available():torch.cuda.manual_seed_all(seed)


def folds(source_ids):
    if set(source_ids)!=ALLOWED or len(source_ids)!=10:raise ValueError('exact ten approved sources required')
    order=np.random.default_rng(SEED).permutation(sorted(source_ids)).tolist()
    return [dict(train=[s for s in order if s not in order[2*i:2*i+2]],validation=order[2*i:2*i+2]) for i in range(5)]


class Crops(Dataset):
    def __init__(self,root,manifest,ids,augment):self.root=root;self.records=[r for r in manifest['crops'] if r['source_id'] in ids];self.augment=augment
    def __len__(self):return len(self.records)
    def __getitem__(self,i):
        record=self.records[i];data=np.load(self.root/record['path']);rgb=torch.from_numpy(data['rgb'].copy()).permute(2,0,1).float()/255;mask=torch.from_numpy(data['coarse'].copy()).float()[None];label=torch.from_numpy(data['label'].copy()).float()[None]
        if self.augment:
            k=random.randrange(4);rgb=torch.rot90(rgb,k,[1,2]);mask=torch.rot90(mask,k,[1,2]);label=torch.rot90(label,k,[1,2])
            if random.random()<.5:rgb=rgb.flip(2);mask=mask.flip(2);label=label.flip(2)
            if random.random()<.5:rgb=rgb.flip(1);mask=mask.flip(1);label=label.flip(1)
            angle=random.uniform(-15,15);scale=random.uniform(.9,1.1);rgb=TF.affine(rgb,angle,[0,0],scale,[0.,0.],interpolation=InterpolationMode.BILINEAR);mask=TF.affine(mask,angle,[0,0],scale,[0.,0.],interpolation=InterpolationMode.NEAREST);label=TF.affine(label,angle,[0,0],scale,[0.,0.],interpolation=InterpolationMode.NEAREST)
            rgb=TF.adjust_brightness(rgb,random.uniform(.85,1.15));rgb=TF.adjust_contrast(rgb,random.uniform(.85,1.15));rgb=TF.adjust_saturation(rgb,random.uniform(.9,1.1))
            if random.random()<.15:rgb=TF.gaussian_blur(rgb,[3,3],[.5,.5])
            if random.random()<.15:rgb=(rgb+torch.randn_like(rgb)*.008).clamp(0,1)
        rgb=(rgb-torch.tensor([.485,.456,.406])[:,None,None])/torch.tensor([.229,.224,.225])[:,None,None]
        return torch.cat([rgb,mask]),label


def native_prediction(model,root,manifest,source_id,device):
    source=next(s for s in manifest['sources'] if s['source_id']==source_id);probability=np.zeros((source['height'],source['width']),np.float32);records=[r for r in manifest['crops'] if r['source_id']==source_id];dataset=Crops(root,manifest,[source_id],False);model.eval()
    with torch.no_grad():
        for i,record in enumerate(records):
            x,_=dataset[i];small=model(x[None].to(device)).sigmoid()[0,0].cpu().numpy();g=record['geometry'];window=small[g['top']:g['top']+g['scaled_height'],g['left']:g['left']+g['scaled_width']];native=np.asarray(Image.fromarray(window).resize((g['width'],g['height']),Image.Resampling.BILINEAR));a,b,c,d=record['bbox'];probability[b:d,a:c]=np.maximum(probability[b:d,a:c],native)
    body=np.asarray(Image.open(source['body_path']))>0;return (probability>=PROTOCOL['threshold'])&body


def validate(model,root,manifest,ids,device):
    rows=[]
    for sid in ids:
        pred=native_prediction(model,root,manifest,sid,device);source=next(s for s in manifest['sources'] if s['source_id']==sid);gt=np.asarray(Image.open(Path(source['GT_folder'])/'ground_truth_mask.png'))>0;tp=int((pred&gt).sum());fp=int((pred&~gt).sum());fn=int((~pred&gt).sum());p=int(pred.sum());g=int(gt.sum());rows.append(dict(source_id=sid,iou=tp/max(1,tp+fp+fn),dice=2*tp/max(1,p+g),precision=tp/p if p else None,recall=tp/g,leakage=fp/p if p else None))
    average={key:float(np.mean([r[key] for r in rows if r[key] is not None])) if any(r[key] is not None for r in rows) else None for key in ['iou','dice','precision','recall','leakage']};return dict(rows=rows,mean=average)


def optimizer(model):
    first=model.encoder[0][0].weight;other=[p for p in model.parameters() if p.requires_grad and p is not first]
    return torch.optim.AdamW([dict(params=[first],lr=PROTOCOL['input_conv_lr']),dict(params=other,lr=PROTOCOL['decoder_lr'])],weight_decay=PROTOCOL['weight_decay'])


def epoch(model,loader,opt,device):
    model.train();losses=[]
    for x,y in loader:
        x,y=x.to(device),y.to(device);opt.zero_grad();loss=bce_dice(model(x),y)
        if not torch.isfinite(loss):raise ValueError('nonfinite_training_loss')
        loss.backward();opt.step();losses.append(float(loss.detach().cpu()))
    if not losses:raise ValueError('empty_training_crop_loader')
    return float(np.mean(losses))


def train(root,weights,output):
    manifest=json.loads((root/'manifest.private.json').read_text());ids=[s['source_id'] for s in manifest['sources']];splits=folds(ids)
    if manifest['blocked_sources']:raise ValueError('coarse proposals missing for sources: '+','.join(manifest['blocked_sources']))
    if any(s['source_sha256'] in manifest['GT7_source_hashes'] for s in manifest['sources']):raise ValueError('GT7_train_overlap')
    # Verify mandatory pretrained acquisition before output or any optimizer step.
    seed_all(SEED);probe,encoder_sha=build_pretrained(weights);del probe
    output.mkdir(parents=True,exist_ok=False);device='cuda' if torch.cuda.is_available() else 'cpu';(output/'protocol.json').write_text(json.dumps(PROTOCOL|dict(device=device,encoder_sha256=encoder_sha,source_splits=splits),indent=2));results=[]
    for fold,split in enumerate(splits,1):
        seed_all(SEED+fold);model,_=build_pretrained(weights);model.to(device);opt=optimizer(model);loader=DataLoader(Crops(root,manifest,split['train'],True),batch_size=PROTOCOL['batch_size'],shuffle=True,num_workers=0);best=-1.;best_epoch=0;stale=0;history=[];folder=output/f'fold_{fold}';folder.mkdir()
        for step in range(1,PROTOCOL['max_epochs']+1):
            loss=epoch(model,loader,opt,device);metric=validate(model,root,manifest,split['validation'],device);score=metric['mean']['iou'];history.append(dict(epoch=step,loss=loss,validation=metric));print('fold',fold,'epoch',step,'validation IoU',score,flush=True)
            if score>best:best=score;best_epoch=step;stale=0;torch.save(model.state_dict(),folder/'best.pt');best_metric=metric
            else:stale+=1
            (folder/'history.private.json').write_text(json.dumps(history,indent=2))
            if stale>=PROTOCOL['patience']:break
        results.append(dict(fold=fold,best_epoch=best_epoch,validation=best_metric,split=split));del model,opt
    if any(not np.isfinite(r['validation']['mean']['iou']) for r in results):raise ValueError('invalid_CV_result')
    final_epochs=int(np.median([r['best_epoch'] for r in results]));(output/'cross_validation.json').write_text(json.dumps(dict(folds=results,mean_iou=float(np.mean([r['validation']['mean']['iou'] for r in results])),mean_dice=float(np.mean([r['validation']['mean']['dice'] for r in results])),final_epochs=final_epochs),indent=2))
    seed_all(SEED);model,_=build_pretrained(weights);model.to(device);opt=optimizer(model);loader=DataLoader(Crops(root,manifest,ids,True),batch_size=PROTOCOL['batch_size'],shuffle=True,num_workers=0);history=[]
    for step in range(1,final_epochs+1):history.append(dict(epoch=step,loss=epoch(model,loader,opt,device)))
    torch.save(model.cpu().state_dict(),output/'final_refinement.pt');sha=hashlib.sha256((output/'final_refinement.pt').read_bytes()).hexdigest();(output/'final_config.json').write_text(json.dumps(PROTOCOL|dict(final_epochs=final_epochs,model_sha256=sha,encoder_sha256=encoder_sha,training_source_ids=ids,GT7_train_overlap=0,training_complete=True,GT7_evaluated=False,history=history),indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--dataset',type=Path,required=True);p.add_argument('--encoder-weights',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();train(a.dataset,a.encoder_weights,a.output)
