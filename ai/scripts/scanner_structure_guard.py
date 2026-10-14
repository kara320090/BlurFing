"""Scanner experimental adapter reuses frozen structure criteria, not skin width."""
from pathlib import Path
import tempfile
import cv2
import numpy as np
from PIL import Image


def scanner_structure_guard(before,after):
    from sourceafis_matcher import run_matcher_job
    from fingerprint_structure_check import assess_structure
    from fingerprint_poc_core import prepare_fingerprint
    folder=Path(tempfile.mkdtemp(prefix='blurfing_scanner_structure_'));paths={};skeletons=[]
    for name,rgb in [('Original',before),('Modified',after)]:
        gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY);path=folder/(name+'.png');Image.fromarray(gray).save(path);paths[name]=path;canonical=cv2.resize(gray,(512,512),interpolation=cv2.INTER_AREA if max(gray.shape)>512 else cv2.INTER_CUBIC);stages,_,_=prepare_fingerprint(canonical);skeletons.append(stages['skeleton_full'])
    result=run_matcher_job(paths,[],run_name='scanner_structure_extract');points={};h,w=before.shape[:2]
    for row in result['images']:
        if row['status'] not in ['ok','no_minutiae']:raise RuntimeError('SourceAFIS_structure_extraction_failed')
        template=row['template'];points[row['key']]=[dict(x=float(x)*512/w,y=float(y)*512/h,type='ending' if t=='E' else 'bifurcation') for x,y,t in zip(template['positionsX'],template['positionsY'],template['types'])]
    union=skeletons[0]|skeletons[1];fraction=float(np.count_nonzero(skeletons[0]^skeletons[1])/max(1,np.count_nonzero(union)));assessment=assess_structure(points['Original'],points['Modified'],fraction);assessment.update(adapter='scanner_native_extraction_to_existing_512_structure_criteria',point_extractor='unchanged SourceAFIS',output_folder=str(folder),matcher_audit=result['output_folder']);return assessment
