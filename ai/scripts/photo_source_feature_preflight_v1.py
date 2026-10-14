"""Observe original seed features before rendering; never a privacy test.

Use the existing original-width RGB normalization and unchanged frozen normal
feature predicate. All input pixels and template dimensions are hash-bound.
"""
import hashlib,tempfile,uuid
from pathlib import Path
import numpy as np
from PIL import Image
from protect_rgb_fingerprint import validate_roi
from evaluate_query_width_protection import width_frame
from fingerprint_structure_check import assess_structure
from sourceafis_matcher import run_matcher_job


def observe(rgb,seed,width):
    rgb,box=validate_roi(rgb,seed)
    if width.get('status')!='estimated':return dict(eligible=False,reason='original_width_unavailable')
    value=width.get('width')
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not np.isfinite(value) or value<=0:
        raise ValueError('source_feature_width_contract')
    a,b,c,d=box;size=int(np.clip(round((c-a)*400/value),128,768))
    before=hashlib.sha256(rgb.tobytes()).hexdigest();crop=rgb[b:d,a:c]
    frame=width_frame(crop,size);folder=Path(tempfile.mkdtemp(prefix='blurfing_original_features_'))
    path=folder/'Original_frame.png';Image.fromarray(frame).save(path)
    result=run_matcher_job({'Original':path},[],run_name='original_features_'+uuid.uuid4().hex[:8])
    if len(result['images'])!=1:raise RuntimeError('source_feature_extractor_output_contract')
    row=result['images'][0]
    if row.get('key')!='Original' or row.get('status') not in ['ok','no_minutiae']:
        raise RuntimeError('source_feature_extractor_failed')
    template=row['template']
    if template['width']!=size or template['height']!=size:raise RuntimeError('source_feature_frame_contract')
    xs,ys,types=template['positionsX'],template['positionsY'],template['types']
    if len(xs)!=len(ys) or len(xs)!=len(types):raise RuntimeError('source_feature_template_contract')
    points=[]
    for x,y,kind in zip(xs,ys,types):
        if not np.isfinite([x,y]).all() or not 0<=x<size or not 0<=y<size or kind not in ['E','B']:
            raise RuntimeError('source_feature_template_contract')
        points.append(dict(x=float(x)*512/size,y=float(y)*512/size,type='ending' if kind=='E' else 'bifurcation'))
    if row['status']=='no_minutiae' and points:raise RuntimeError('source_feature_template_contract')
    normal=assess_structure(points,points,0.)['normal_features']
    if hashlib.sha256(rgb.tobytes()).hexdigest()!=before:raise RuntimeError('source_feature_RGB_changed')
    return dict(eligible=normal,reason=None if normal else 'insufficient_features',before_feature_count=len(points),
        canonical_size=size,source_RGB_sha256=before,seed_RGB_sha256=hashlib.sha256(crop.tobytes()).hexdigest(),
        frame_pixel_sha256=hashlib.sha256(frame.tobytes()).hexdigest(),frame_color_space='CLAHE_grayscale',seed_roi=list(box),
        purpose='pre-render original availability; frozen normal_features predicate',
        generated_features_inspected=False,identity_matching_performed=False,privacy_validated=False)
