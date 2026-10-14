"""Private human-mask evaluation; never approves masks or changes detector policy.

Artifacts are upright EXIF coordinates. GT and exported comparison masks use
encoded source pixels. Raw foreground proposals are diagnostic only, including
those rejected before renderer scope validation. No GT-driven mask selection.
"""
import argparse
import csv
import json
from pathlib import Path
import time
import numpy as np
from PIL import Image, ImageOps, ImageDraw
import automatic_boundary_v1 as detector
import detection_artifact as artifact


def encoded(mask, orientation):
    methods={2:Image.Transpose.FLIP_LEFT_RIGHT,3:Image.Transpose.ROTATE_180,
             4:Image.Transpose.FLIP_TOP_BOTTOM,5:Image.Transpose.TRANSPOSE,
             6:Image.Transpose.ROTATE_90,7:Image.Transpose.TRANSVERSE,
             8:Image.Transpose.ROTATE_270}
    im=Image.fromarray(mask.astype(np.uint8)*255)
    return np.asarray(im.transpose(methods[orientation]) if orientation in methods else im)>0


def bbox(mask):
    y,x=np.where(mask)
    return [int(x.min()),int(y.min()),int(x.max())+1,int(y.max())+1] if len(x) else None


def metrics(pred,gt):
    if pred.shape!=gt.shape:raise ValueError('comparison_shape_mismatch')
    tp=int((pred&gt).sum());fp=int((pred&~gt).sum());fn=int((~pred&gt).sum())
    n=int(pred.sum());g=int(gt.sum());neg=int((~gt).sum());pb=bbox(pred);gb=bbox(gt)
    return dict(iou=tp/(tp+fp+fn),precision=tp/n if n else None,recall=tp/g,
        false_positive_rate=fp/neg if neg else None,leakage_fraction=fp/n if n else None,
        mask_area_ratio=n/g,predicted_area=n,gt_area=g,true_positive_pixels=tp,
        false_positive_pixels=fp,false_negative_pixels=fn,predicted_bbox=pb,gt_bbox=gb,
        bbox_delta=[a-b for a,b in zip(pb,gb)] if pb else None)



def component_matching(pred,gt):
    """Evaluation-only one-to-one overlap matching; never selects render input."""
    from scipy.ndimage import label
    from scipy.optimize import linear_sum_assignment
    pl,pn=label(pred);gl,gn=label(gt);scores=np.zeros((gn,pn),float)
    for i in range(gn):
        g=gl==i+1
        for j in range(pn):
            p=pl==j+1;intersection=int((p&g).sum())
            scores[i,j]=intersection/int((p|g).sum())
    match={}
    if gn and pn:
        gi,pi=linear_sum_assignment(-scores)
        match={int(i):int(j) for i,j in zip(gi,pi) if scores[i,j]>0}
    rows=[]
    for i in range(gn):
        j=match.get(i);p=pl==j+1 if j is not None else np.zeros_like(pred)
        rows.append(dict(gt_component_id=i+1,prediction_component_id=j+1 if j is not None else None,metrics=metrics(p,gl==i+1)))
    return dict(gt_component_count=gn,predicted_component_count=pn,matched_nonzero_overlap=len(match),components=rows,ground_truth_is_connected_regions_not_confirmed_finger_identity=True)

def overlay(source,gt,pred,path):
    rgb=np.asarray(source.convert('RGB')).copy();tp=gt&pred;fp=pred&~gt;fn=gt&~pred
    for m,col in [(tp,[0,255,0]),(fp,[255,0,0]),(fn,[0,120,255])]:
        rgb[m]=(rgb[m]*.5+np.array(col)*.5).astype(np.uint8)
    im=Image.fromarray(rgb);im.thumbnail((1200,1200));ImageDraw.Draw(im).text((10,10),'Green overlap / Red prediction-only / Blue GT-only',fill='white');im.save(path)


def run(gt_root,input_root,output,samples):
    verified=[]
    for sid in samples:
        folder=gt_root/sid;meta=json.loads((folder/'source.json').read_text())
        if meta.get('annotation_type')!='human_reviewed_fingerprint_pad' or meta.get('human_annotation') is not True:raise ValueError('not_human_ground_truth')
        filename=meta['source_filename']
        if Path(filename).name!=filename:raise ValueError('unsafe_source_filename')
        source=input_root/filename
        if artifact.digest(source)!=meta['source_sha256']:raise ValueError('source_hash_mismatch')
        mask_path=folder/'ground_truth_mask.png'
        if artifact.digest(mask_path)!=meta['mask_sha256']:raise ValueError('ground_truth_hash_mismatch')
        with Image.open(source) as im:
            size=im.size;orientation=im.getexif().get(274,1)
        with Image.open(mask_path) as im:
            if im.mode!='L' or im.size!=size or im.size!=(meta['image_width'],meta['image_height']):raise ValueError('GT_shape_or_mode_mismatch')
            gt=np.asarray(im).copy()
        if orientation!=meta.get('exif_orientation'):raise ValueError('GT_exif_mismatch')
        if meta.get('coordinate_system')!='encoded_original_pixels' or not np.isin(gt,[0,255]).all() or not gt.any():raise ValueError('invalid_GT_coordinates_or_pixels')
        verified.append((sid,source,meta,gt==255,orientation,artifact.digest(mask_path)))
    output.mkdir(parents=True,exist_ok=False);rows=[]
    for sid,source,meta,gt,orientation,gt_hash in verified:
        folder=output/sid;folder.mkdir();raw=[];captured={};state={'k':0}
        oldlocal=detector._local_pad;oldrot=detector._rotation;olddetect=artifact.detect_boundaries
        def rotation(k,h,w):state['k']=k;return oldrot(k,h,w)
        def local(rgb,c):
            mask,quality=oldlocal(rgb,c)
            if mask is not None:raw.append((np.rot90(mask,-state['k']).copy(),dict(quality),dict(c),state['k']))
            return mask,quality
        def detect(rgb):
            result=detector.detect_boundaries(rgb);captured['result']=result;return result
        start=time.perf_counter()
        try:
            detector._rotation=rotation;detector._local_pad=local;artifact.detect_boundaries=detect
            detection_path=artifact.write_detection(source,folder/'artifact')
        finally:
            detector._local_pad=oldlocal;detector._rotation=oldrot;artifact.detect_boundaries=olddetect
        elapsed=time.perf_counter()-start
        _,data,pred_display=artifact.validate_artifact(source,detection_path)
        pred=encoded(pred_display,orientation);Image.fromarray(pred.astype(np.uint8)*255).save(folder/'automatic_mask_encoded.png')
        with Image.open(source) as image:overlay(image,gt,pred,folder/'approved_overlay_private.png')
        raw_union=np.zeros(pred_display.shape,bool);diagnostics=[]
        for i,(mask,quality,c,k) in enumerate(raw):
            raw_union|=mask;enc=encoded(mask,orientation);name=f'raw_proposal_{i:03d}_encoded.png'
            Image.fromarray(enc.astype(np.uint8)*255).save(folder/name)
            with Image.open(source) as image:overlay(image,gt,enc,folder/f'raw_proposal_{i:03d}_overlay_private.png')
            diagnostics.append(dict(proposal_id=i,rotation_quadrants=k,quality=quality,metrics=metrics(enc,gt),mask_path=name,seed_roi_upright=c['seed_roi']))
        with Image.open(source) as image:overlay(image,gt,encoded(raw_union,orientation),folder/'raw_union_overlay_private.png')
        result=captured['result'];regions=[]
        for i,r in enumerate(result['regions']):
            regions.append(dict(region_id=i,status=r['status'],reject_reason=r['reject_reason'],scope_upright=r['scope'],pitch_native=r['pitch_native'],metrics=metrics(encoded(r['mask'],orientation),gt)))
        reason=[r['reject_reason'] for r in result['regions'] if r['reject_reason']]+[r.get('reject_reason') for r in result['rejected']]
        row=dict(sample_id=sid,status=data['status'],proposal_count=result['proposal_count'],approved_regions=len(data['regions']),gt_polygon_count=meta['polygon_count'],detection_seconds=elapsed,metrics=metrics(pred,gt),raw_union_metrics=metrics(encoded(raw_union,orientation),gt),component_matching=component_matching(pred,gt),raw_component_matching=component_matching(encoded(raw_union,orientation),gt),raw_proposals=diagnostics,regions=regions,reject_reasons=reason or ['no_fingertip'],selection='All approved regions union; no GT-based finger selection. Raw proposals are separately reported and never consumed.',source_sha256=meta['source_sha256'],ground_truth_sha256=gt_hash)
        (folder/'metrics.private.json').write_text(json.dumps(row,indent=2))
        if artifact.digest(source)!=meta['source_sha256'] or artifact.digest(gt_root/sid/'ground_truth_mask.png')!=gt_hash:raise ValueError('input_changed')
        rows.append(row);print(sid,data['status'],row['metrics']['iou'],row['reject_reasons'],flush=True)
    aggregate={}
    for field in ['iou','precision','recall','false_positive_rate','leakage_fraction','mask_area_ratio']:
        values=[r['metrics'][field] for r in rows if r['metrics'][field] is not None]
        aggregate[field]=dict(mean=float(np.mean(values)),median=float(np.median(values)),min=float(min(values)),max=float(max(values)),valid_samples=len(values)) if values else dict(mean=None,median=None,min=None,max=None,valid_samples=0)
    summary=dict(samples=rows,aggregate=aggregate,detector_approved=False,approval_basis='No automatic promotion; requires usable nonempty masks, leakage evidence and negative/control regression. Four positive GT images cannot establish rotated/small/non-target safety.',private=True)
    (output/'metrics.private.json').write_text(json.dumps(summary,indent=2))
    with (output/'sample_metrics.csv').open('w',newline='') as f:
        fields=['sample_id','status','approved_regions','iou','precision','recall','false_positive_rate','leakage_fraction','mask_area_ratio'];writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for r in rows:writer.writerow({k:(r[k] if k in r else r['metrics'][k]) for k in fields})
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--ground-truth-root',type=Path,required=True);p.add_argument('--input-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--samples',nargs='+',default=['DET-01','DET-03','DET-04','DET-05']);a=p.parse_args();run(a.ground_truth_root,a.input_root,a.output,a.samples)
