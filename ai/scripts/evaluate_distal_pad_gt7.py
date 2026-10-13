"""Status-aware private evaluation: annotation metadata never enters inference."""
import argparse,json,time,hashlib
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
from sam_pad_detector import digest,load_finger_masks,postprocess_fingers
from distal_pad_estimator_experimental import estimate
from evaluate_detector_ground_truth import component_matching,overlay


def component_count(mask):return int(cv2.connectedComponents(mask.astype(np.uint8),connectivity=4)[0]-1)


def validate_annotation(folder,source):
    meta=json.loads((folder/'source.json').read_text());before=digest(source)
    if meta.get('source_sha256')!=before:raise ValueError('GT_source_hash_mismatch')
    if meta.get('human_annotation') is not True or meta.get('annotation_type')!='human_reviewed_fingerprint_pad':raise ValueError('GT_not_human')
    if meta.get('coordinate_system')!='encoded_original_pixels':raise ValueError('GT_coordinate_mismatch')
    with Image.open(source) as im:
        size=im.size;orientation=im.getexif().get(274,1)
    if size!=(meta['image_width'],meta['image_height']) or orientation!=meta.get('exif_orientation'):raise ValueError('GT_source_shape_or_EXIF_mismatch')
    path=folder/'ground_truth_mask.png';mask=None
    if path.exists():
        if path.is_symlink() or digest(path)!=meta.get('mask_sha256'):raise ValueError('GT_mask_hash_mismatch')
        with Image.open(path) as im:
            if im.format!='PNG' or im.mode!='L' or im.size!=size:raise ValueError('GT_mask_shape_or_dtype_mismatch')
            values=np.asarray(im).copy()
        if not np.isin(values,[0,255]).all():raise ValueError('GT_nonbinary')
        mask=values==255
    declared=meta.get('annotation_status');status=declared
    if declared is None:
        status='valid_positive' if mask is not None and mask.any() else 'unresolved_status'
        derivation='existing human nonempty pad annotation; annotation_status absent' if status=='valid_positive' else 'empty/missing mask without declared status'
    elif declared=='ambiguous_unusable':status='ambiguous_unusable';derivation='explicit annotation_status'
    elif declared in ['non-target','non_target']:status='non_target';derivation='explicit annotation_status'
    elif declared in ['valid_positive','positive','annotated','human_reviewed']:status='valid_positive';derivation='explicit annotation_status'
    else:status='unresolved_status';derivation='unknown declared status'
    if status=='non_target' and (mask is None or mask.any()):raise ValueError('non_target_requires_verified_empty_mask')
    if status=='valid_positive' and (mask is None or not mask.any()):raise ValueError('positive_GT_missing_or_empty')
    return mask,dict(status=status,declared_annotation_status=declared,status_derivation=derivation,source_sha256=before,mask_present=mask is not None,image_width=size[0],image_height=size[1],binary_verified=mask is not None,polygon_count=meta.get('polygon_count'),component_count=component_count(mask) if mask is not None else None,metadata_sha256=digest(folder/'source.json'))


def mask_metrics(pred,gt):
    tp=int((pred&gt).sum());fp=int((pred&~gt).sum());fn=int((~pred&gt).sum());p=int(pred.sum());g=int(gt.sum());union=tp+fp+fn
    m=dict(iou=tp/union if union else 1.,dice=2*tp/(p+g) if p+g else 1.,precision=tp/p if p else None,recall=tp/g if g else None,predicted_outside_GT_ratio=fp/p if p else None,predicted_pixels=p,GT_pixels=g,true_positive_pixels=tp,false_positive_pixels=fp,false_negative_pixels=fn,predicted_component_count=component_count(pred),GT_component_count=component_count(gt))
    if g:
        matches=component_matching(pred,gt);accepted=[r for r in matches['components'] if r['metrics']['iou']>=.5];matched=len(accepted)
    else:matched=0
    m.update(matched_components=matched,component_coverage=matched/m['GT_component_count'] if g else None,false_positive_components=m['predicted_component_count']-matched,missed_components=m['GT_component_count']-matched)
    return m


def run_once(item):
    tick=time.perf_counter();rgb,masks,meta=load_finger_masks(Path(item['source']),Path(item['manifest']));postprocess_fingers(masks);loaded=time.perf_counter()-tick;tick=time.perf_counter();result=estimate(rgb,masks,[r.get('tip_hint_native') for r in meta['input_manifest']['masks']]);pad=time.perf_counter()-tick
    return rgb,masks,result,dict(SAM_loading_validation_preflight_postprocess=loaded,pad_estimator=pad,total_detector=loaded+pad)


def evaluate(roster,output):
    output.mkdir(parents=True,exist_ok=False)
    # Validate all annotations first, then never pass them to run_once/estimate.
    annotations={r['sample_id']:validate_annotation(Path(r['GT_folder']),Path(r['source'])) for r in roster};rows=[]
    for item in roster:
        sid=item['sample_id']
        if Path(sid).name!=sid or sid in ['.','..']:raise ValueError('invalid_sample_id')
        gt,integrity=annotations[sid];rgb,fingers,result,timing=run_once(item);folder=output/sid;folder.mkdir();pred=result['mask'];union=np.logical_or.reduce(fingers) if fingers else np.zeros(pred.shape,bool);assert not (pred&~union).any()
        repeat=run_once(item)[2];assert np.array_equal(pred,repeat['mask'])
        row=dict(sample_id=sid,annotation=integrity,detector_status='review_candidates' if pred.any() else 'rejected',candidate_count=len(result['regions']),predicted_pad_count=component_count(pred),boundary_sources=[r['proximal_boundary_source'] for r in result['regions']],confidence=[r['confidence'] for r in result['regions']],reject_reasons=[r['reject_reason'] for r in result['regions']],protection_auto_approved=bool(result['approved_for_use']),reviewable_region_count=sum(r['reject_reason'] is None for r in result['regions']),finger_exterior_pixels=int((pred&~union).sum()),deterministic=True,timing=timing,mask_pixel_sha256=hashlib.sha256(pred.tobytes()).hexdigest())
        if integrity['status'] in ['valid_positive','non_target']:row['metrics']=mask_metrics(pred,gt)
        else:row['metrics']=None
        Image.fromarray(pred.astype(np.uint8)*255).save(folder/'predicted_pad_mask.png')
        if gt is not None:
            with Image.open(item['source']) as im:overlay(im,gt,pred,folder/'overlay_private.png')
        private=row|dict(regions=[{k:v for k,v in r.items() if k not in ['mask','diagnostic_geometry_mask']} for r in result['regions']]);(folder/'details.private.json').write_text(json.dumps(private,indent=2));rows.append(row);print(sid,integrity['status'],None if row['metrics'] is None else row['metrics']['iou'],flush=True)
    positive=[r for r in rows if r['annotation']['status']=='valid_positive'];negative=[r for r in rows if r['annotation']['status']=='non_target'];ambiguous=[r for r in rows if r['annotation']['status']=='ambiguous_unusable']
    gt_count=sum(r['metrics']['GT_component_count'] for r in positive);matched=sum(r['metrics']['matched_components'] for r in positive)
    summary=dict(rows=rows,valid_positive_count=len(positive),ambiguous_count=len(ambiguous),non_target_count=len(negative),unresolved_count=sum(r['annotation']['status']=='unresolved_status' for r in rows),macro_positive_iou=float(np.mean([r['metrics']['iou'] for r in positive])) if positive else None,component_coverage=dict(matched=matched,total=gt_count,ratio=matched/gt_count if gt_count else None),non_target_false_positive_components=sum(r['metrics']['false_positive_components'] for r in negative) if negative else None,ambiguous_protection_auto_approval_count=sum(r['protection_auto_approved'] for r in ambiguous) if ambiguous else None,ambiguous_review_candidate_count=sum(r['reviewable_region_count'] for r in ambiguous) if ambiguous else None,detector_approved=False,downstream='NOT_RUN')
    (output/'summary.json').write_text(json.dumps(summary,indent=2));return summary


def benchmark(item):
    rows=[];hashes=[]
    for i in range(11):
        _,_,r,t=run_once(item);hashes.append(hashlib.sha256(r['mask'].tobytes()).hexdigest())
        if i:rows.append(t)
    assert len(set(hashes))==1
    return dict(warmup=1,measured=10,deterministic=True,scope='saved SAM masks; no neural SAM inference',stats={k:{name:float(f([r[k] for r in rows])) for name,f in [('mean',np.mean),('median',np.median),('min',np.min),('max',np.max),('std',np.std),('p95',lambda v:np.percentile(v,95))]} for k in rows[0]})

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--roster',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--benchmark-sample',default='CAP-042');a=p.parse_args();roster=json.loads(a.roster.read_text());evaluate(roster,a.output);b=benchmark(next(r for r in roster if r['sample_id']==a.benchmark_sample));(a.output/'benchmark.json').write_text(json.dumps(b,indent=2))
