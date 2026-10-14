"""Private Linux pad-level evaluation + fixed-SAM-mask benchmark; no auto render.

Gate values are fixed before scoring. Evaluator is the only module that reads
human GT. SAM producer and pad extractor have no GT parameter or filesystem use.
"""
import argparse
import json
from pathlib import Path
import time
import numpy as np
from PIL import Image
from sam_pad_detector import load_finger_masks,postprocess_fingers,extract_pad_candidates,digest
from evaluate_model_segmentation_masks import validate_gt,extended_metrics
from evaluate_detector_ground_truth import overlay

GATE=dict(macro_pad_iou_min=.70,component_coverage_min=6/7,max_per_sample_outside_GT_ratio=.05,finger_exterior_pixels_max=0,observed_crease_and_unambiguous_tip_required=True,component_match_iou_min=.5)


def connection(rgb,r):
    from automatic_boundary_v1 import _square
    from protect_visible_pad_checked_v2 import observed_seed_pitch
    if not r['mask'].any():return dict(status='blocked',reason='no_pad')
    if min(rgb.shape[:2])<64:return dict(status='blocked',reason='source_too_small_for_seed')
    square=_square(r['mask']);width=r['width_profile']['median_native'];target=np.array(r['tip_xy'])+np.array(r['axis_xy'])*(.6*width);y,x=np.where(r['mask']);index=np.argmin((x-target[0])**2+(y-target[1])**2);cx=int(x[index]);cy=int(y[index]);side=min(512,max(64,round(.6*width)));side+=side%2
    h,w=rgb.shape[:2];a=min(max(0,cx-side//2),w-side);b=min(max(0,cy-side//2),h-side);seed=[a,b,a+side,b+side]
    pitch,measurement,_=observed_seed_pitch(rgb,seed);reasons=[]
    if square is None:reasons.append('square_scope_incompatible')
    if pitch is None or not 2<=pitch<=50:reasons.append('pitch_invalid_or_outside_frozen_range')
    return dict(status='blocked' if reasons else 'geometry_pitch_compatible_structure_unchecked',reasons=reasons,scope=square,seed_roi=seed,pitch_native=pitch,pitch_measurement=measurement)


def run_once(source,manifest):
    start=time.perf_counter();rgb,masks,load=load_finger_masks(source,manifest);clean,q=postprocess_fingers(masks);loaded=time.perf_counter()-start;result=extract_pad_candidates(rgb,clean,q,[r.get('tip_hint_native') for r in load['input_manifest']['masks']])
    return rgb,masks,result,dict(SAM_mask_loading_postprocess=loaded,axis_pad_boundary=result['axis_pad_seconds'],total_detector=time.perf_counter()-start)


def signature(result):
    import hashlib
    rows=[{k:v for k,v in r.items() if k!='mask'} for r in result['regions']]
    hashes=[hashlib.sha256(r['mask'].tobytes()).hexdigest() for r in result['regions']]
    return hashlib.sha256((json.dumps(rows,sort_keys=True)+str(hashes)).encode()).hexdigest()


def benchmark(source,manifest,repeats=10):
    if repeats<10:raise ValueError('At least ten measured runs')
    rows=[];hashes=[]
    for i in range(repeats+1):
        _,_,r,t=run_once(source,manifest);hashes.append(signature(r))
        if i:rows.append(t)
    if len(set(hashes))!=1:raise ValueError('nondeterministic_pad_extraction')
    stats={}
    for k in rows[0]:
        v=[r[k] for r in rows];stats[k]={name:float(f(v)) for name,f in [('mean',np.mean),('median',np.median),('min',np.min),('max',np.max),('std',np.std)]};stats[k]['p95']=float(np.percentile(v,95))
    return dict(warmup=1,measured=repeats,deterministic=True,scope='fixed saved SAM finger masks -> pad; excludes SAM model generation',stats=stats)


def evaluate(roster,gt_root,output):
    output.mkdir(parents=True,exist_ok=False);rows=[];runtime=[]
    for item in roster:
        sid=item['sample_id'];source=Path(item['source']);manifest=Path(item['manifest']);rgb,fingers,r,t=run_once(source,manifest)
        # GT enters only AFTER pad inference is complete.
        expected,meta,gt,size=validate_gt(gt_root/sid,source.parent)
        if expected.resolve()!=source.resolve():raise ValueError('GT_source_mismatch')
        union=np.logical_or.reduce(fingers) if fingers else np.zeros(rgb.shape[:2],bool);pm,pc=extended_metrics(r['mask'],gt);pm['matched_gt_components_iou_0_5']=sum(q['metrics']['iou']>=GATE['component_match_iou_min'] for q in pc['components']);fm,fc=extended_metrics(union,gt);exterior=int((r['mask']&~union).sum());assert exterior==0
        folder=output/sid;folder.mkdir();Image.fromarray(r['mask'].astype(np.uint8)*255).save(folder/'pad_union.png')
        with Image.open(source) as im:overlay(im,gt,r['mask'],folder/'pad_overlay_private.png');overlay(im,gt,union,folder/'foreground_overlay_private.png')
        details=[];reasons=[];active_reasons=[]
        for i,region in enumerate(r['regions']):
            name=f'pad_{i:03d}.png';Image.fromarray(region['mask'].astype(np.uint8)*255).save(folder/name);row={k:v for k,v in region.items() if k!='mask'};row.update(mask_path=name,mask_sha256=digest(folder/name),renderer_connection=connection(rgb,region));details.append(row)
            reasons+=region['quality'].get('reject_reasons',[])
            if region['quality'].get('reject_reason'):reasons.append(region['quality']['reject_reason'])
            if region['mask'].any():active_reasons+=region['quality'].get('reject_reasons',[])
        private=dict(schema_version='sam-pad-candidates-v1',source_sha256=meta['source_sha256'],sam_input_manifest_sha256=digest(manifest),image_width=size[0],image_height=size[1],coordinate_system='encoded_original_pixels',detector_version=r['detector_version'],status='review_required_not_protection_artifact',regions=details,mask_path='pad_union.png',mask_sha256=digest(folder/'pad_union.png'),pad_metrics=pm,foreground_metrics=fm,component_matching=pc,timing=t,ground_truth_sha256=meta['mask_sha256'])
        (folder/'pad_candidates.private.json').write_text(json.dumps(private,indent=2));rows.append(dict(sample_id=sid,pad_metrics={k:v for k,v in pm.items() if k not in ['predicted_bbox','gt_bbox','bbox_delta']},foreground_metrics={k:v for k,v in fm.items() if k not in ['predicted_bbox','gt_bbox','bbox_delta']},finger_masks=len(fingers),finger_exterior_pixels=exterior,quality_reasons=reasons,active_quality_reasons=active_reasons,renderer_blocked_regions=sum(d['renderer_connection']['status']=='blocked' for d in details),component_details=[dict(gt_component_id=q['gt_component_id'],prediction_component_id=q['prediction_component_id'],iou=q['metrics']['iou'],recall=q['metrics']['recall']) for q in pc['components']]))
        runtime.append(dict(source=source,manifest=manifest));print(sid,'pad IoU',pm['iou'],'coverage',pm['matched_gt_components'],'/',pm['gt_component_count'],reasons,flush=True)
    bench=benchmark(runtime[-1]['source'],runtime[-1]['manifest']);macro=float(np.mean([r['pad_metrics']['iou'] for r in rows]));matched=sum(r['pad_metrics']['matched_gt_components_iou_0_5'] for r in rows);total=sum(r['pad_metrics']['gt_component_count'] for r in rows);leakage=max(r['pad_metrics']['leakage_fraction'] if r['pad_metrics']['leakage_fraction'] is not None else 1 for r in rows)
    criteria=dict(macro_iou=macro>=GATE['macro_pad_iou_min'],coverage=matched/total>=GATE['component_coverage_min'],outside_GT=leakage<=GATE['max_per_sample_outside_GT_ratio'],finger_exterior=all(r['finger_exterior_pixels']==0 for r in rows),deterministic=bench['deterministic'],quality=all(not r['active_quality_reasons'] for r in rows),nonempty_all_samples=all(r['pad_metrics']['predicted_area']>0 for r in rows))
    summary=dict(detector_implemented=True,GT_evaluation_complete=True,gate=GATE,criteria=criteria,detector_approved=all(criteria.values()),macro_pad_iou=macro,component_coverage=dict(matched=matched,total=total,ratio=matched/total),max_outside_GT_ratio=leakage,samples=rows,benchmark=bench,downstream='NOT_RUN_pending_gate_and_renderer_contract',model_generation_in_benchmark=False)
    (output/'summary.json').write_text(json.dumps(summary,indent=2));return summary

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--roster',type=Path);p.add_argument('--ground-truth-root',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--benchmark-only',action='store_true');p.add_argument('--input',type=Path);p.add_argument('--finger-manifest',type=Path);a=p.parse_args()
    if a.benchmark_only:
        if a.input is None or a.finger_manifest is None:p.error('benchmark requires --input and --finger-manifest')
        result=benchmark(a.input,a.finger_manifest);a.output.mkdir(parents=True,exist_ok=False);(a.output/'benchmark.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
    else:
        if a.roster is None or a.ground_truth_root is None:p.error('evaluation requires --roster and --ground-truth-root')
        evaluate(json.loads(a.roster.read_text()),a.ground_truth_root,a.output)
