"""Train-fold-only source-weighted class balance; no inference criteria change.

The weighted BCE logits are not calibrated unweighted posterior probabilities.
The numeric 0.5 prediction boundary is retained, but its meaning changes.
"""
import numpy as np
import torch
import torch.nn.functional as F
from pad_refinement_data_contract_v2 import load_crop
from pad_refinement_tiles_v3 import hash_json
from train_pad_refinement_tiles_v3 import source_weights

VERSION='source_class_balanced_BCE_positive_tile_Dice_v1'


def class_balance(root,manifest,ids):
    if not ids or len(ids)!=len(set(ids)) or not set(ids)<={s['source_id'] for s in manifest['sources']}:
        raise ValueError('explicit_unique_training_sources_required')
    sources={s['source_id']:s for s in manifest['sources']}
    records=[r for r in manifest['crops'] if r['source_id'] in ids]
    if {r['source_id'] for r in records}!=set(ids):raise ValueError('complete_training_tile_sources_required')
    weights=source_weights(records);positive=0.;total=0.;empty=0
    for record,weight in zip(records,weights):
        label=load_crop(root,record,sources[record['source_id']],'training')['label']
        positive+=weight*float(label.mean());total+=weight;empty+=not label.any()
    p=positive/total
    if not np.isfinite(p) or not 0<p<1:raise ValueError('both_finite_training_classes_required')
    stats=dict(version=VERSION,source_ids=sorted(ids),tiles=len(records),empty_target_tiles=int(empty),
        positive_fraction=p,positive_weight=1/(2*p),negative_weight=1/(2*(1-p)),
        estimator='equal source, equal tiles within source, equal 256x256 pixels including padding; before augmentation',
        crop_sha256=hash_json([{k:r[k] for k in ['source_id','path','file_sha256']} for r in records]))
    return stats|dict(statistics_sha256=hash_json(stats))


def per_example_loss(logits,target,statistics):
    if logits.shape!=target.shape or logits.ndim!=4 or logits.shape[1:]!=(1,256,256):raise ValueError('balanced_loss_shape_contract')
    if not torch.isfinite(logits).all() or not torch.isfinite(target).all() or not ((target==0)|(target==1)).all():
        raise ValueError('finite_binary_balanced_loss_inputs_required')
    p=statistics['positive_fraction']
    if not np.isfinite(p) or not 0<p<1:raise ValueError('both_finite_training_classes_required')
    wp,wn=1/(2*p),1/(2*(1-p))
    if statistics['positive_weight']!=wp or statistics['negative_weight']!=wn:raise ValueError('class_weight_contract')
    axes=(1,2,3);probability=logits.sigmoid();intersection=(probability*target).sum(axes)
    denominator=probability.sum(axes)+target.sum(axes)
    dice=1-(2*intersection+1)/(denominator+1)
    weights=torch.where(target==1,logits.new_tensor(wp),logits.new_tensor(wn))
    bce=(F.binary_cross_entropy_with_logits(logits,target,reduction='none')*weights).mean(axes)
    return bce+torch.where(target.sum(axes)>0,dice,torch.zeros_like(dice))
