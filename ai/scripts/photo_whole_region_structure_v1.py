"""Experimental whole-permission-region structure observation, not seed scope.

Uses the existing functional predicate and original-width frame normalization.
Extracted points and skeletons outside the exact permission mask cannot count.
This changes the assessed ROI/coordinate domain and is NOT frozen-gate
equivalence. Original frozen functions, numeric criteria and renderer stay intact.
"""
import hashlib,tempfile,uuid
from pathlib import Path
import cv2,numpy as np
from PIL import Image
from fingerprint_structure_check import assess_structure
from fingerprint_poc_core import prepare_fingerprint
from protect_contactless_delta import normalize_contactless
from protect_rgb_fingerprint import validate_roi
from evaluate_query_width_protection import width_frame
from sourceafis_matcher import run_matcher_job


def assess(original,candidate,scope,permission,width):
    original,box=validate_roi(original,scope);candidate,_=validate_roi(candidate,scope)
    if (candidate.shape!=original.shape or permission.dtype!=np.bool_ or permission.shape!=original.shape[:2] or
            not permission.any() or not np.array_equal(original[~permission],candidate[~permission])):
        raise ValueError('whole_region_RGB_permission_contract')
    a,b,c,d=box
    if int(permission[b:d,a:c].sum())!=int(permission.sum()):raise ValueError('whole_region_scope_drops_permission')
    if width.get('status')!='estimated':return dict(structure_change_passed=False,reason='original_width_unavailable',privacy_validated=False)
    value=width.get('width')
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not np.isfinite(value) or value<=0:
        raise ValueError('whole_region_width_contract')
    size=int(np.clip(round((c-a)*400/value),128,768));native_mask=permission[b:d,a:c]
    mask512=cv2.resize(native_mask.astype(np.uint8),(512,512),interpolation=cv2.INTER_NEAREST)>0
    frame_mask=cv2.resize(native_mask.astype(np.uint8),(size,size),interpolation=cv2.INTER_NEAREST)>0
    identity=[hashlib.sha256(x.tobytes()).hexdigest() for x in [original,candidate,permission]]
    folder=Path(tempfile.mkdtemp(prefix='blurfing_whole_region_structure_'));images={};skeletons=[]
    for name,image in [('Original',original),('Modified',candidate)]:
        crop=image[b:d,a:c];frame=width_frame(crop,size);path=folder/(name+'_frame.png');Image.fromarray(frame).save(path);images[name]=path
        gray=cv2.resize(cv2.cvtColor(crop,cv2.COLOR_RGB2GRAY),(512,512),interpolation=cv2.INTER_CUBIC if c-a<512 else cv2.INTER_AREA)
        stages,_,_=prepare_fingerprint(normalize_contactless(gray));skeleton=stages['skeleton_full']&mask512
        skeletons.append(skeleton);Image.fromarray(skeleton.astype(np.uint8)*255).save(folder/(name+'_masked_skeleton.png'))
    result=run_matcher_job(images,[],run_name='whole_region_structure_'+uuid.uuid4().hex[:8]);points={};counts={}
    if len(result['images'])!=2:raise RuntimeError('whole_region_extractor_output_contract')
    for row in result['images']:
        key=row.get('key')
        if key not in images or key in points or row.get('status') not in ['ok','no_minutiae']:
            raise RuntimeError('whole_region_extractor_failed')
        template=row['template']
        if template['width']!=size or template['height']!=size:raise RuntimeError('whole_region_frame_contract')
        xs,ys,types=template['positionsX'],template['positionsY'],template['types']
        if len(xs)!=len(ys) or len(xs)!=len(types):raise RuntimeError('whole_region_template_contract')
        selected=[]
        for x,y,kind in zip(xs,ys,types):
            if not np.isfinite([x,y]).all() or not 0<=x<size or not 0<=y<size or kind not in ['E','B']:
                raise RuntimeError('whole_region_template_contract')
            if frame_mask[int(y),int(x)]:selected.append(dict(x=float(x)*512/size,y=float(y)*512/size,type='ending' if kind=='E' else 'bifurcation'))
        if row['status']=='no_minutiae' and xs:raise RuntimeError('whole_region_template_contract')
        points[key]=selected;counts[key]=dict(total_extracted=len(xs),inside_permission=len(selected),outside_permission=len(xs)-len(selected))
    union=skeletons[0]|skeletons[1];fraction=float(np.count_nonzero(skeletons[0]^skeletons[1])/max(1,np.count_nonzero(union)))
    evidence=assess_structure(points['Original'],points['Modified'],fraction)
    if [hashlib.sha256(x.tobytes()).hexdigest() for x in [original,candidate,permission]]!=identity:
        raise RuntimeError('whole_region_observation_inputs_changed')
    evidence.update(version='whole_permission_region_structure_v1_experimental',scope=list(box),canonical_size=size,
        coordinate_system='whole_permission_square_normalized_512_pixels',feature_scope_changed_from_frozen_seed=True,
        frozen_gate_equivalence=False,points_outside_permission_counted=False,counts=counts,result_folder=str(folder))
    return evidence
