"""Evaluate saved raw semantic masks; GT never enters the inference worker."""
import argparse,json,hashlib,csv
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
from evaluate_distal_pad_gt7 import validate_annotation,mask_metrics,component_count
from evaluate_detector_ground_truth import overlay
from colfispoof_raw_semantics import vote_masks
from ridge_evidence_frontend import ridge_evidence


def ridge_filter(rgb,mask):
    """Separate secondary result using the unchanged common ridge validator."""
    gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY);output=np.zeros(mask.shape,bool);qualities=[]
    count,labels,stats,_=cv2.connectedComponentsWithStats(mask.astype(np.uint8),connectivity=4)
    for label in range(1,count):
        x,y,w,h,area=map(int,stats[label]);support=labels[y:y+h,x:x+w]==label
        credible,q=ridge_evidence(gray[y:y+h,x:x+w],support)
        if q['status']=='ridge_observed':output[y:y+h,x:x+w]|=credible
        qualities.append(dict(component=label,bbox=[x,y,x+w,y+h],area=area,quality=q))
    assert not (output&~mask).any()
    return output,qualities


def aggregate(rows,key):
    positive=[r for r in rows if r['annotation_status']=='valid_positive'];values=[r[key]['iou'] for r in positive];matched=sum(r[key]['matched_components'] for r in positive);total=sum(r[key]['GT_component_count'] for r in positive)
    return dict(macro_iou=float(np.mean(values)) if values else None,median_iou=float(np.median(values)) if values else None,min_iou=min(values) if values else None,max_iou=max(values) if values else None,component_coverage=dict(matched=matched,total=total,ratio=matched/total if total else None),false_positive_components=sum(r[key]['false_positive_components'] for r in rows if r[key] is not None),missed_components=sum(r[key]['missed_components'] for r in positive))


def evaluate(roster,inference,output):
    output.mkdir(parents=True,exist_ok=False);records=json.loads((inference/'inference.json').read_text());record_by_id={r['sample_id']:r for r in records['rows']};rows=[]
    for item in roster:
        sid=item['sample_id'];gt,annotation=validate_annotation(Path(item['GT_folder']),Path(item['source']));record=record_by_id[sid]
        if record['source_sha256']!=annotation['source_sha256']:raise ValueError('inference_source_hash_mismatch')
        with Image.open(item['source']) as im:rgb=np.asarray(im.convert('RGB')).copy()
        shape=rgb.shape[:2];masks=[]
        for angle in [0,90,180,270]:
            with Image.open(inference/sid/f'rotation_{angle}.png') as im:
                a=np.asarray(im).copy()
                if im.mode!='L' or a.shape!=shape or not np.isin(a,[0,255]).all():raise ValueError('invalid_rotation_mask')
                masks.append(a==255)
        pred=vote_masks(masks);repeats=[]
        for repeat in range(1,4):
            path=inference/sid/f'consensus_repeat_{repeat}.png'
            with Image.open(path) as im:a=np.asarray(im).copy()
            if a.shape!=shape or not np.isin(a,[0,255]).all():raise ValueError('invalid_repeat_mask')
            mask=a==255
            if hashlib.sha256(mask.tobytes()).hexdigest()!=record['runs'][repeat-1]['mask_pixel_sha256']:raise ValueError('prediction_hash_mismatch')
            repeats.append(mask)
        assert np.array_equal(pred,repeats[0])
        folder=output/sid;folder.mkdir();Image.fromarray(pred.astype(np.uint8)*255).save(folder/'prediction_consensus.png')
        valid=annotation['status'] in ['valid_positive','non_target'];raw_metrics=mask_metrics(pred,gt) if valid else None
        if gt is not None:
            with Image.open(item['source']) as im:overlay(im,gt,pred,folder/'overlay_raw.private.png')
        filtered,quality=ridge_filter(rgb,pred);Image.fromarray(filtered.astype(np.uint8)*255).save(folder/'prediction_ridge_validated.png')
        if gt is not None:
            with Image.open(item['source']) as im:overlay(im,gt,filtered,folder/'overlay_ridge.private.png')
        pairwise=[dict(a=a,b=b,iou=float((masks[a]&masks[b]).sum()/max(1,(masks[a]|masks[b]).sum()))) for a in range(4) for b in range(a+1,4)]
        row=dict(sample_id=sid,annotation_status=annotation['status'],primary_policy='class 2; votes >=2/4; no component cleanup',raw_rotation_components=[component_count(m) for m in masks],consensus_components=component_count(pred),raw_metrics=raw_metrics,ridge_metrics=mask_metrics(filtered,gt) if valid else None,rotation_pairwise_iou=pairwise,diagnostic_vote_metrics={str(v):mask_metrics(vote_masks(masks,v),gt) for v in [1,3,4]} if valid else None,deterministic=all(np.array_equal(pred,m) for m in repeats),repeat_metrics=[mask_metrics(m,gt) for m in repeats] if valid else None,mask_hashes=[r['mask_pixel_sha256'] for r in record['runs']],ridge_quality=quality)
        (folder/'metrics.json').write_text(json.dumps(row,indent=2));rows.append(row);print(sid,raw_metrics,flush=True)
    summary=dict(rows=rows,raw=aggregate(rows,'raw_metrics'),ridge_validated=aggregate(rows,'ridge_metrics'),deterministic=all(r['deterministic'] for r in rows),source_model_sha256=records['model_sha256'],primary_policy='fixed 2/4; no cleanup',GT_used_for_inference=False,GT_threshold_selection=False)
    (output/'summary.json').write_text(json.dumps(summary,indent=2));return summary

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--roster',type=Path,required=True);p.add_argument('--inference',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();evaluate(json.loads(a.roster.read_text()),a.inference,a.output)
