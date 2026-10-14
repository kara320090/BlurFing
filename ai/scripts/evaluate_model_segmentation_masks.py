"""Evaluate private external model predictions without running/training a model.

No model-specific preprocessing is guessed. The producer must supply encoded
native PNG masks and audited model provenance. This tool never authorizes a
protection artifact, even if four development masks score well.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import numpy as np
from PIL import Image
from evaluate_detector_ground_truth import metrics, component_matching, overlay, encoded


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def restore_probability_mask(probability,upright_size,orientation,threshold=.5):
    """Explicit alternative: interpolate probability, then threshold, then undo EXIF.

    This is NOT a claim of equivalence to any upstream binary-resize pipeline.
    Geometry only; no model input normalization or channel order is inferred.
    """
    import cv2
    p=np.asarray(probability)
    if p.ndim!=2 or not np.isfinite(p).all() or p.min()<0 or p.max()>1:raise ValueError('invalid_probability')
    if not 0<threshold<1 or len(upright_size)!=2 or min(upright_size)<=0:raise ValueError('invalid_mapping')
    if orientation not in range(1,9):raise ValueError('invalid_orientation')
    resized=cv2.resize(p.astype(np.float32),tuple(upright_size),interpolation=cv2.INTER_LINEAR)
    return encoded(resized>threshold,orientation)


def extended_metrics(pred,gt):
    m=metrics(pred,gt);tp=m['true_positive_pixels'];fp=m['false_positive_pixels'];fn=m['false_negative_pixels']
    m.update(dice=2*tp/(2*tp+fp+fn),gt_missed_pixel_ratio=fn/int(gt.sum()))
    c=component_matching(pred,gt)
    m.update(gt_component_count=c['gt_component_count'],predicted_component_count=c['predicted_component_count'],matched_gt_components=c['matched_nonzero_overlap'],missed_gt_components=c['gt_component_count']-c['matched_nonzero_overlap'],false_components=c['predicted_component_count']-c['matched_nonzero_overlap'],component_recall=c['matched_nonzero_overlap']/c['gt_component_count'])
    return m,c


def binary_png(path,size,expected_sha):
    if path.is_symlink() or digest(path)!=expected_sha:raise ValueError('mask_hash_mismatch')
    with Image.open(path) as im:
        if im.format!='PNG' or im.mode!='L' or im.size!=size:raise ValueError('mask_shape_or_mode_mismatch')
        pixels=np.asarray(im).copy()
    if not np.isin(pixels,[0,255]).all():raise ValueError('nonbinary_mask')
    return pixels==255


def validate_gt(folder,input_root):
    meta=json.loads((folder/'source.json').read_text());name=meta['source_filename']
    if Path(name).name!=name:raise ValueError('unsafe_source_filename')
    if meta.get('annotation_type')!='human_reviewed_fingerprint_pad' or meta.get('human_annotation') is not True:raise ValueError('not_human_GT')
    if meta.get('coordinate_system')!='encoded_original_pixels':raise ValueError('GT_coordinates_mismatch')
    source=input_root/name
    if digest(source)!=meta['source_sha256']:raise ValueError('source_hash_mismatch')
    with Image.open(source) as im:
        size=im.size;orientation=im.getexif().get(274,1)
    if size!=(meta['image_width'],meta['image_height']) or orientation!=meta.get('exif_orientation'):raise ValueError('GT_source_geometry_mismatch')
    gt=binary_png(folder/'ground_truth_mask.png',size,meta['mask_sha256'])
    if not gt.any():raise ValueError('empty_GT')
    return source,meta,gt,size


def evaluate(gt_root,input_root,prediction_root,manifest_path,weights,output,samples):
    model=json.loads(manifest_path.read_text())
    if not re.fullmatch('[0-9a-f]{64}',model.get('weights_sha256','')) or digest(weights)!=model['weights_sha256']:raise ValueError('weights_hash_mismatch')
    for key in ['model_name','model_version','upstream_repository','license','framework_version','preprocessing']:
        if not model.get(key):raise ValueError('missing_model_provenance_'+key)
    prepared=[]
    for sid in samples:
        if not re.fullmatch(r'DET-\d{2}',sid):raise ValueError('invalid_anonymous_sample_id')
        source,meta,gt,size=validate_gt(gt_root/sid,input_root)
        prediction=json.loads((prediction_root/sid/'prediction.json').read_text())
        if prediction.get('source_sha256')!=meta['source_sha256'] or prediction.get('weights_sha256')!=model['weights_sha256']:raise ValueError('prediction_provenance_mismatch')
        if prediction.get('coordinate_system')!='encoded_original_pixels' or prediction.get('image_width')!=size[0] or prediction.get('image_height')!=size[1]:raise ValueError('prediction_geometry_mismatch')
        if prediction.get('threshold')!=.5:raise ValueError('primary_threshold_must_be_0_5')
        variants=prediction.get('variants',{})
        if not variants or 'raw' not in variants or set(variants)-{'raw','safe'}:raise ValueError('invalid_prediction_variants')
        masks={}
        for name,value in variants.items():
            filename=value['mask_path']
            if not re.fullmatch(r'[A-Za-z0-9_-]+\.png',filename):raise ValueError('non_relative_mask_path')
            masks[name]=binary_png(prediction_root/sid/filename,size,value['mask_sha256'])
        prepared.append((sid,source,meta,gt,masks))
    output.mkdir(parents=True,exist_ok=False);rows=[]
    for sid,source,meta,gt,masks in prepared:
        folder=output/sid;folder.mkdir()
        for variant,pred in masks.items():
            m,c=extended_metrics(pred,gt);rows.append(dict(sample_id=sid,variant=variant,metrics=m,component_matching=c))
            with Image.open(source) as image:overlay(image,gt,pred,folder/(variant+'_overlay_private.png'))
        if digest(source)!=meta['source_sha256'] or digest(gt_root/sid/'ground_truth_mask.png')!=meta['mask_sha256']:raise ValueError('input_changed')
    aggregate={}
    for variant in ['raw','safe']:
        rs=[r for r in rows if r['variant']==variant]
        if not rs:continue
        aggregate[variant]={}
        for key in ['iou','dice','precision','recall','leakage_fraction','gt_missed_pixel_ratio','mask_area_ratio','component_recall']:
            values=[r['metrics'][key] for r in rs if r['metrics'][key] is not None]
            aggregate[variant][key]=dict(mean=float(np.mean(values)),median=float(np.median(values)),min=float(min(values)),max=float(max(values)),valid_samples=len(values)) if values else None
    result=dict(model_provenance=model,samples=rows,aggregate=aggregate,private=True,development_only=True,approved_for_protection=False,component_matching_basis='one-to-one maximum IoU with nonzero overlap; not confirmed anatomical identification',inference_performed_by_this_tool=False)
    (output/'evaluation.private.json').write_text(json.dumps(result,indent=2));return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['ground-truth-root','input-root','prediction-root','model-manifest','weights','output']:p.add_argument('--'+name,required=True,type=Path)
    p.add_argument('--samples',nargs='+',default=['DET-01','DET-03','DET-04','DET-05']);a=p.parse_args()
    r=evaluate(a.ground_truth_root,a.input_root,a.prediction_root,a.model_manifest,a.weights,a.output,a.samples)
    print(json.dumps(r['aggregate'],indent=2))

if __name__=='__main__':main()
