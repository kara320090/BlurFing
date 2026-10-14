"""Private experimental inference/evaluation. GT enters after inference only."""
import argparse,json,time
from pathlib import Path
import numpy as np
from PIL import Image
from sam_pad_detector import load_finger_masks,digest
from distal_pad_estimator_experimental import estimate


def evaluate(roster,output,ground_truth_root=None):
    output.mkdir(parents=True,exist_ok=False);rows=[]
    for item in roster:
        sid=item['sample_id']
        if Path(sid).name!=sid:raise ValueError('invalid_sample_id')
        source=Path(item['source']);tick=time.perf_counter();rgb,masks,meta=load_finger_masks(source,Path(item['manifest']));hints=[r.get('tip_hint_native') for r in meta['input_manifest']['masks']];result=estimate(rgb,masks,hints);elapsed=time.perf_counter()-tick
        row=dict(sample_id=sid,source_sha256=digest(source),seconds=elapsed,regions=[{k:v for k,v in r.items() if k not in ['mask','diagnostic_geometry_mask']} for r in result['regions']],approved_for_use=False)
        if ground_truth_root is not None:
            from evaluate_model_segmentation_masks import validate_gt,extended_metrics
            from evaluate_detector_ground_truth import overlay
            _,_,gt,_=validate_gt(ground_truth_root/sid,source.parent);metric,matching=extended_metrics(result['mask'],gt);row['metrics']=metric;row['component_coverage']=sum(r['metrics']['iou']>=.5 for r in matching['components'])
        folder=output/sid;folder.mkdir();Image.fromarray(result['mask'].astype(np.uint8)*255).save(folder/'experimental_pad_mask.png')
        # Rejected geometry is separate, never disguised as accepted prediction.
        diagnostic=np.logical_or.reduce([r['diagnostic_geometry_mask'] for r in result['regions']]) if result['regions'] else np.zeros(rgb.shape[:2],bool)
        Image.fromarray(diagnostic.astype(np.uint8)*255).save(folder/'diagnostic_only_mask.png')
        if ground_truth_root is not None:
            with Image.open(source) as im:overlay(im,gt,result['mask'],folder/'overlay_private.png')
        (folder/'details.private.json').write_text(json.dumps(row,indent=2));rows.append(row);print(sid,'reviewable regions',sum(r['distal_estimator']['reject_reason'] is None for r in result['regions']),flush=True)
    (output/'summary.private.json').write_text(json.dumps(rows,indent=2));return rows

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--roster',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--ground-truth-root',type=Path);a=p.parse_args();evaluate(json.loads(a.roster.read_text()),a.output,a.ground_truth_root)
