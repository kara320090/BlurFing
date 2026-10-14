"""Private GT evaluation of semantic-body distal candidates; no GT in estimator."""
import argparse,json,hashlib,time
from pathlib import Path
import numpy as np
from PIL import Image
from finger_body_distal_estimator import estimate
from evaluate_distal_pad_gt7 import validate_annotation,mask_metrics
from evaluate_detector_ground_truth import overlay
from evaluate_colfispoof_raw_gt import ridge_filter,aggregate


def read_binary(path,shape,expected_sha):
    if hashlib.sha256(path.read_bytes()).hexdigest()!=expected_sha:raise ValueError('semantic_mask_hash_mismatch')
    with Image.open(path) as im:
        a=np.asarray(im).copy()
        if im.mode!='L' or a.shape!=shape or not np.isin(a,[0,255]).all():raise ValueError('invalid_semantic_mask')
    return a==255


def evaluate(roster,semantic_root,output):
    output.mkdir(parents=True,exist_ok=False);rows=[]
    for item in roster:
        sid=item['sample_id']
        if Path(sid).name!=sid or sid in ['.','..']:raise ValueError('invalid_sample_id')
        source=Path(item['source']);meta=json.loads((semantic_root/sid/'semantics.json').read_text());gt,annotation=validate_annotation(Path(item['GT_folder']),source)
        if meta['source_sha256']!=annotation['source_sha256'] or meta['coordinate_system']!='encoded_original_pixels':raise ValueError('source_coordinate_contract_mismatch')
        with Image.open(source) as im:rgb=np.asarray(im.convert('RGB')).copy()
        if (meta['image_height'],meta['image_width'])!=rgb.shape[:2]:raise ValueError('semantic_shape_mismatch')
        body=read_binary(semantic_root/sid/'body.png',rgb.shape[:2],meta['body_sha256']);tip=read_binary(semantic_root/sid/'tip.png',rgb.shape[:2],meta['tip_sha256'])
        tick=time.perf_counter();result=estimate(body,tip);elapsed=time.perf_counter()-tick;pred=result['mask'];repeat=estimate(body,tip);assert np.array_equal(pred,repeat['mask']);assert not (pred&~body).any()
        valid=annotation['status'] in ['valid_positive','non_target'];filtered,quality=ridge_filter(rgb,pred);folder=output/sid;folder.mkdir();Image.fromarray(pred.astype(np.uint8)*255).save(folder/'pad.png')
        if gt is not None:
            with Image.open(source) as im:overlay(im,gt,pred,folder/'overlay.private.png')
        row=dict(sample_id=sid,annotation_status=annotation['status'],raw_metrics=mask_metrics(pred,gt) if valid else None,ridge_metrics=mask_metrics(filtered,gt) if valid else None,body_exterior_pixels=0,deterministic=True,estimator_seconds=elapsed,mask_sha256=hashlib.sha256(pred.tobytes()).hexdigest(),regions=[{k:v for k,v in r.items() if k!='mask'} for r in result['regions']]);rows.append(row);(folder/'metrics.private.json').write_text(json.dumps(row,indent=2))
    summary=dict(rows=rows,raw=aggregate(rows,'raw_metrics'),ridge_diagnostic=aggregate(rows,'ridge_metrics'),deterministic=True,approved=False,approval_semantics='candidates only; quantitative gate and private visual review required',GT_used_by_estimator=False)
    (output/'summary.private.json').write_text(json.dumps(summary,indent=2));return summary

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--roster',type=Path,required=True);p.add_argument('--semantic-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();evaluate(json.loads(a.roster.read_text()),a.semantic_root,a.output)
