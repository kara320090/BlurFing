import tempfile
import json

from pathlib import Path

from uuid import uuid4

import cv2

import numpy as np

from PIL import Image

from fingerprint_poc_core import prepare_fingerprint, point_similarity, minutiae_overlay

from protect_contactless_delta import normalize_contactless

from protect_rgb_fingerprint import validate_roi

from contactless_finger_width import estimate_finger_width

from evaluate_query_width_protection import width_frame

from sourceafis_matcher_linux import run_matcher_job

ROOT=Path(__file__).resolve().parents[1]

OUT=Path(tempfile.mkdtemp(prefix='blurfing_structure_', dir='/tmp'))

def assess_structure(before,after,skeleton_changed_fraction):
    similarity=point_similarity(before,after)
    normal=min(len(before),len(after))>=10
    changed=similarity['added']+similarity['removed']>=2 and similarity['similarity'] is not None and similarity['similarity']<=.9
    passed=normal and changed and skeleton_changed_fraction>=.05
    return dict(structure_change_passed=passed,normal_features=normal,minutiae=similarity,
        skeleton_changed_fraction=skeleton_changed_fraction,
        reason='changed_structure_observed' if passed else 'insufficient_features' if not normal else 'structure_change_not_demonstrated',
        identity_matching_performed=False,privacy_validated=False,human_naturalness_validated=False,
        criterion='both >=10 extracted points; same-coordinate same-type Dice <=0.9; >=2 point changes; skeleton XOR/union >=0.05',
        thresholds_are_functional_prototype_only=True)

def check_structure_change(original,candidate,seed_roi):
    original,box=validate_roi(original,seed_roi);candidate,_=validate_roi(candidate,box)
    if candidate.shape!=original.shape:raise ValueError('Dimensions changed')
    measurement=estimate_finger_width(original,box)
    if measurement['status']!='estimated':return dict(structure_change_passed=False,reason='original_width_unavailable',privacy_validated=False)
    folder=OUT/('structure_function_'+uuid4().hex[:8]);folder.mkdir()
    a,b,c,d=box;size=int(np.clip(round((c-a)*400/measurement['width']),128,768));frames=[];skeletons=[];images={}
    for label,photo in [('Original',original),('Modified',candidate)]:
        crop=photo[b:d,a:c];frame=width_frame(crop,size);path=folder/(label+'_frame.png');Image.fromarray(frame).save(path);images[label]=path
        gray=cv2.resize(cv2.cvtColor(crop,cv2.COLOR_RGB2GRAY),(512,512),interpolation=cv2.INTER_CUBIC if c-a<512 else cv2.INTER_AREA)
        stages,_,_=prepare_fingerprint(normalize_contactless(gray));skeleton=stages['skeleton_full'];skeletons.append(skeleton);frames.append(gray)
        Image.fromarray(skeleton.astype(np.uint8)*255).save(folder/(label+'_skeleton.png'))
    result=run_matcher_job(images,[],run_name='structure_extract_'+uuid4().hex[:8]);points=[]
    for row in result['images']:
        if row['status'] not in ['ok','no_minutiae']:raise RuntimeError('Structure extractor failed')
        t=row['template'];assert t['width']==size and t['height']==size
        points.append([dict(x=float(x)*512/size,y=float(y)*512/size,type='ending' if kind=='E' else 'bifurcation') for x,y,kind in zip(t['positionsX'],t['positionsY'],t['types'])])
    # Index by image key; extractor ordering is not an association assumption.
    mapped=dict(zip([r['key'] for r in result['images']],points));points=[mapped['Original'],mapped['Modified']]
    union=skeletons[0]|skeletons[1];fraction=float(np.count_nonzero(skeletons[0]^skeletons[1])/max(1,np.count_nonzero(union)))
    evidence=assess_structure(*points,fraction)
    for label,gray,skeleton,features in zip(['Original','Modified'],frames,skeletons,points):
        integer=[p|dict(x=int(round(p['x'])),y=int(round(p['y']))) for p in features]
        Image.fromarray(minutiae_overlay(gray,skeleton,integer)).save(folder/(label+'_overlay.png'))
    evidence.update(result_folder=str(folder),seed_roi=list(box),canonical_size=size,point_extractor='SourceAFIS at frozen original-width normalization; no match scores',
        points_before=points[0],points_after=points[1],skeleton_processing='existing 512 PoC preprocessing')
    (folder/'assessment.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
    return evidence
