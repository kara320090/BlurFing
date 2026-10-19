"""GT-assisted visibility measurements, without classification or protection changes.

MCLFIQ is a quality score, not a visibility probability. This adapter measures
raw pitch first, uses an explicit experimental preprocessing, and never supplies
a default pitch. Missing/failed scores stay null. No threshold is calibrated here.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import tempfile
import time

import cv2
import numpy as np
from PIL import Image
from photo_pad_annotation_v1 import digest, write_json
from photo_visibility_annotation_v1 import Project, component_map
from photo_candidate_ridge_diagnostic_v1 import observe_candidate
from photo_resize_safety_v1 import validate_resize

VERSION='visibility_quality_diagnostic_v1'


def bind_upright_coordinates(observation, offset_xy):
    """The reused observer names its caller's array 'encoded'; our caller is upright."""
    ox,oy=offset_xy
    b=observation.pop('bbox_encoded_source_xyxy')
    observation['bbox_upright_native_xyxy']=[b[0]+ox,b[1]+oy,b[2]+ox,b[3]+oy]
    observation['source_frame']='upright_base_frame_after_EXIF'
    for level in observation['levels']:
        pitch=level.get('pitch',{})
        if 'coordinate_origin_encoded_source_xy' in pitch:
            x,y=pitch.pop('coordinate_origin_encoded_source_xy')
            pitch['coordinate_origin_upright_native_xy']=[x+ox,y+oy]
        for patch in pitch.get('patch_native_coordinates',[]):
            x,y=patch.pop('center_encoded_source_xy')
            patch['center_upright_native_xy']=[x+ox,y+oy]
    return observation


def pitch_consensus(observation):
    """All accepted resolutions, not the most favorable one. No new gate tuning."""
    values=[]
    for level in observation['levels']:
        item=level.get('pitch',{})
        if item.get('status')!='observed': continue
        patches=item.get('patch_native_coordinates',[])
        if not patches: continue
        values.append(float(np.median([(p['autocorrelation_perpendicular_native_pixels']+
                       p['fft_perpendicular_native_pixels'])/2 for p in patches])))
    if not values: return dict(status='unavailable',native_pitch=None,reason='raw_pitch_unobserved')
    if not all(math.isfinite(v) and v>0 for v in values): raise ValueError('invalid_observed_pitch')
    middle=float(np.median(values))
    # Same 15% relative tolerance as the existing observer, not fitted to this set.
    if (max(values)-min(values))/middle>.15:
        return dict(status='unavailable',native_pitch=None,reason='cross_resolution_pitch_disagreement',values=values)
    return dict(status='observed',native_pitch=middle,resolution_values=values,physical_DPI_known=False)


def preprocess(rgb,mask,pitch):
    if not math.isfinite(pitch) or pitch<=0: raise ValueError('positive_observed_pitch_required')
    if rgb.dtype!=np.uint8 or mask.dtype!=np.bool_ or rgb.shape[:2]!=mask.shape or not mask.any(): raise ValueError('image_mask_contract')
    ys,xs=np.where(mask); x0,x1=int(xs.min()),int(xs.max())+1; y0,y1=int(ys.min()),int(ys.max())+1
    rgb=rgb[y0:y1,x0:x1];mask=mask[y0:y1,x0:x1]
    h,w=mask.shape
    # PCA makes the anatomical long axis vertical; its sign cannot establish the
    # fingertip direction. Both 180-degree alternatives are retained, never maxed.
    yy,xx=np.where(mask);cov=np.cov(np.stack([xx,yy])) if len(xx)>2 else np.eye(2)
    _,vec=np.linalg.eigh(cov);axis=vec[:,-1];angle=math.degrees(math.atan2(axis[1],axis[0]))-90
    matrix=cv2.getRotationMatrix2D(((w-1)/2,(h-1)/2),angle,1.)
    cw=int(math.ceil(abs(matrix[0,0])*w+abs(matrix[0,1])*h));ch=int(math.ceil(abs(matrix[0,1])*w+abs(matrix[0,0])*h))
    validate_resize(ch,cw,1.)
    matrix[:,2]+=np.array([(cw-w)/2,(ch-h)/2])
    gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
    # Whitening before interpolation prevents neighboring fingers/background from entering the ROI.
    gray=gray.copy();gray[~mask]=255
    rotated=cv2.warpAffine(gray,matrix,(cw,ch),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT,borderValue=255)
    support=cv2.warpAffine(mask.astype(np.uint8),matrix,(cw,ch),flags=cv2.INTER_NEAREST,borderMode=cv2.BORDER_CONSTANT)>0
    yy,xx=np.where(support)
    if not len(xx): raise ValueError('rotation_lost_mask')
    sl=np.s_[yy.min():yy.max()+1,xx.min():xx.max()+1];rotated=rotated[sl];support=support[sl]
    size,audit=validate_resize(*rotated.shape,9./pitch)
    interpolation=cv2.INTER_AREA if 9./pitch<1 else cv2.INTER_LINEAR
    scaled=cv2.resize(rotated,(size[1],size[0]),interpolation=interpolation)
    scaled_mask=cv2.resize(support.astype(np.uint8),(size[1],size[0]),interpolation=cv2.INTER_NEAREST)>0
    enhanced=cv2.createCLAHE(clipLimit=2.,tileGridSize=(8,8)).apply(scaled)
    enhanced[~scaled_mask]=255
    # This is an experimental adapter, not an exact reproduction of the paper's
    # iterative enhancement (not fully parameterized in the publication).
    return enhanced,dict(version='mclfiq_preprocessing_experimental_v1',target_pitch=9.,actual_resize_yx=[size[0]/rotated.shape[0],size[1]/rotated.shape[1]],
        physical_DPI_known=False,PNG_DPI_is_nominal_compatibility_tag=500,rotation_degrees=angle,
        distal_direction_verified=False,CLAHE=dict(clipLimit=2.,tileGridSize=[8,8]),shape=list(size),resource_audit=audit,
        paper_preprocessing_equivalence_verified=False,raw_pitch_before_enhancement=True)


class MCLFIQ:
    def __init__(self,config):
        self.config=json.loads(Path(config).read_text(encoding='utf-8-sig'))
        for name in ['executable','model','model_info']:
            path=Path(self.config[name]);expected=self.config[name+'_sha256']
            if not path.is_absolute() or path.is_symlink() or digest(path.read_bytes())!=expected: raise ValueError('runtime_identity_mismatch_'+name)
        content=Path(self.config['model_info']).read_text(encoding='utf-8')
        fields=dict(re.findall(r'^\s*(\w+)\s*=\s*(.*?)\s*$',content,re.M))
        if Path(fields.get('Path','')).resolve()!=Path(self.config['model']).resolve() or fields.get('Hash')!=hashlib.md5(Path(self.config['model']).read_bytes()).hexdigest():
            raise ValueError('custom_model_binding_mismatch')
        self.md5=fields['Hash']

    def score(self,image):
        started=time.perf_counter()
        with tempfile.TemporaryDirectory(prefix='blurfing-mclfiq-') as directory:
            path=Path(directory)/'input.png';Image.fromarray(image).save(path,dpi=(500,500))
            try:
                result=subprocess.run([self.config['executable'],'-F','-d','-m',self.config['model_info'],str(path)],
                    capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=60,stdin=subprocess.DEVNULL)
            except subprocess.TimeoutExpired:
                return dict(status='unavailable',score=None,reason='runtime_timeout',seconds=time.perf_counter()-started)
        output=result.stdout+'\n'+result.stderr
        # NFIQ2 can return exit code 0 for feature extraction errors.
        if 'Model Hash: '+self.md5 not in output:
            return dict(status='unavailable',score=None,reason='custom_model_not_confirmed',seconds=time.perf_counter()-started)
        errors=[line for line in output.splitlines() if re.search(r'\berror\b',line,re.I)]
        scores=re.findall(r'^\s*(\d{1,3})\s*$',output,re.M)
        if result.returncode!=0 or errors or len(scores)!=1 or not 0<=int(scores[0])<=100:
            return dict(status='unavailable',score=None,reason='quality_runtime_or_feature_failure',
                detail=errors[:2],returncode=result.returncode,seconds=time.perf_counter()-started)
        return dict(status='scored',score=int(scores[0]),custom_model_confirmed=True,seconds=time.perf_counter()-started)


def run(roster,state,output,config):
    output=Path(output)
    if output.exists(): raise FileExistsError('fresh_diagnostic_output_required')
    output.mkdir(parents=True);project=Project(roster,state);runtime=MCLFIQ(config);rows=[];start=time.perf_counter()
    for sid,source in project.sources.items():
        rgb,mask=project.arrays(sid);labels,_=component_map(mask);annotation=project.current(sid)
        for index,group in enumerate(annotation['groups'],1):
            mask=np.isin(labels,group['component_ids']);ys,xs=np.where(mask);sl=np.s_[ys.min():ys.max()+1,xs.min():xs.max()+1]
            local_rgb=rgb[sl].copy();local_mask=mask[sl].copy();t=time.perf_counter()
            row=dict(source_id=sid,component_ids=group['component_ids'],source_sha256=source['source_sha256'],mask_sha256=source['mask_sha256'],
                split_role=source['split_role'],acquisition_group=source.get('acquisition_group'),
                human_label=group['label'] if annotation['human_GT'] else None,annotation_revision=annotation['revision'],
                observer_scope='GT_assisted_anatomical_ROI_not_end_to_end_detection',automatic_visibility='uncertain')
            observation=bind_upright_coordinates(observe_candidate(local_rgb,local_mask,local_mask,source['source_sha256']),
                [int(xs.min()),int(ys.min())])
            row['raw_observations']=observation
            row['pitch']=pitch_consensus(observation)
            row['ridge_signal_observed']=any(l.get('ridge_quality',{}).get('status')=='ridge_observed' for l in observation['levels'])
            if row['pitch']['status']=='observed':
                try:
                    image,metadata=preprocess(local_rgb,local_mask,row['pitch']['native_pitch'])
                    row['preprocessing']=metadata
                    Image.fromarray(image).save(output/f'{sid}_{index:03d}_mclfiq_input.private.png',dpi=(500,500))
                    row['mclfiq']={str(angle):runtime.score(image if angle==0 else image[::-1,::-1].copy()) for angle in [0,180]}
                except ValueError as error:
                    row['mclfiq']=dict(status='unavailable',score=None,reason='preprocessing_rejected',detail=str(error))
            else: row['mclfiq']=dict(status='unavailable',score=None,reason=row['pitch']['reason'])
            row['seconds']=time.perf_counter()-t;rows.append(row)
            write_json(output/f'{sid}_{index:03d}.private.json',row)
        print(json.dumps(dict(source=sid,completed_regions=len(rows))),flush=True)
    scored=sum(any(isinstance(s,dict) and s.get('status')=='scored' for s in r['mclfiq'].values()) for r in rows)
    summary=dict(version=VERSION,sources=len(project.sources),regions=len(rows),raw_ridge_signal_regions=sum(r['ridge_signal_observed'] for r in rows),
        normalized_pitch_regions=sum(r['pitch']['status']=='observed' for r in rows),mclfiq_scored_regions=scored,
        human_labeled_regions=sum(r['human_label'] is not None for r in rows),visibility_accuracy=None,
        accuracy_reason='no_fitted_or_validated_visibility_classifier',independent_validation=False,
        GT_assisted_diagnostic=True,protection_behavior_changed=False,thresholds_changed=False,
        absence_inferred_from_failure=False,runtime_identity=runtime.config,seconds=time.perf_counter()-start)
    write_json(output/'summary.private.json',summary)
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['roster','state','output','runtime-config']: p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();print(json.dumps(run(a.roster,a.state,a.output,a.runtime_config),indent=2))
