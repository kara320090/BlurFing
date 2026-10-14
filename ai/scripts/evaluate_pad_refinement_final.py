"""Metrics for already-frozen predictions; never trains/selects model settings."""
import argparse,json,hashlib
from pathlib import Path
import numpy as np
from PIL import Image
from evaluate_distal_pad_gt7 import validate_annotation,mask_metrics
from evaluate_detector_ground_truth import overlay
from evaluate_colfispoof_raw_gt import aggregate


def evaluate(roster,predictions,output):
    output.mkdir(parents=True,exist_ok=False);audit=json.loads((predictions/'inference.private.json').read_text());identity={r['sample_id']:r for r in audit['rows']};rows=[]
    for item in roster:
        sid=item['sample_id'];gt,annotation=validate_annotation(Path(item['GT_folder']),Path(item['source']));record=identity[sid]
        if annotation['source_sha256']!=record['source_sha256']:raise ValueError('prediction_source_mismatch')
        with Image.open(predictions/(sid+'.png')) as im:
            a=np.asarray(im).copy()
            if im.mode!='L' or a.shape!=gt.shape or not np.isin(a,[0,255]).all():raise ValueError('native_binary_mask_required')
        pred=a==255
        if hashlib.sha256(pred.tobytes()).hexdigest()!=record['mask_pixel_sha256']:raise ValueError('prediction_hash_mismatch')
        row=dict(sample_id=sid,annotation_status=annotation['status'],raw_metrics=mask_metrics(pred,gt),body_exterior_pixels=record['body_exterior_pixels'],deterministic=record['deterministic']);rows.append(row)
        with Image.open(item['source']) as im:overlay(im,gt,pred,output/(sid+'_overlay.private.png'))
    result=dict(model_sha256=audit['model_sha256'],rows=rows,aggregate=aggregate(rows,'raw_metrics'));(output/'GT7_final.private.json').write_text(json.dumps(result,indent=2));return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--roster',type=Path,required=True);p.add_argument('--predictions',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();evaluate(json.loads(a.roster.read_text()),a.predictions,a.output)
