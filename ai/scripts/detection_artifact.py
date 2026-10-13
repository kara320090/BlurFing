"""Portable hash-bound detection artifact and fail-closed frozen consumer.

Private images, masks, previews and actual artifacts must not be committed.
New graph-cut proposals are deliberately review-gated, not silently approved.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path
import tempfile
import threading
import time
import numpy as np
from PIL import Image,ImageOps
from automatic_boundary_v1 import detect_boundaries

SCHEMA='blurfing-detection-v1'
_LOCK=threading.RLock()


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_input(path):
    path=Path(path).resolve(strict=True);before=digest(path)
    with Image.open(path) as im:
        orientation=im.getexif().get(274,1);rgb=np.asarray(ImageOps.exif_transpose(im).convert('RGB'))
    if digest(path)!=before:raise ValueError('source_changed_during_read')
    return rgb,before,orientation not in (None,1)


def write_detection(source,output):
    rgb,source_hash,exif=read_input(source);start=time.perf_counter();result=detect_boundaries(rgb)
    folder=Path(output);folder.mkdir(parents=True,exist_ok=False);union=np.zeros(rgb.shape[:2],bool);regions=[]
    for i,region in enumerate(result['regions']):
        if region['status']!='accepted':continue
        mask=region['mask'];overlap=union&mask
        if overlap.any():continue
        name=f'region_{i:03d}_mask.png';Image.fromarray(mask.astype(np.uint8)*255).save(folder/name)
        union|=mask
        regions.append(dict(region_id=f'region-{i:03d}',roi_xyxy=region['scope'],seed_roi=region['candidate']['seed_roi'],
            pitch_native=region['pitch_native'],mask_path=name,mask_sha256=digest(folder/name),quality=region['quality'],method=region['method']))
    Image.fromarray(union.astype(np.uint8)*255).save(folder/'fingerprint_mask.png')
    reasons=[r['reject_reason'] for r in result['regions'] if r['reject_reason']]+[r.get('reject_reason') for r in result['rejected']]
    data=dict(schema_version=SCHEMA,detector_version=result['detector_version'],source_sha256=source_hash,
        decoded_rgb_sha256=hashlib.sha256(rgb.tobytes()).hexdigest(),image_width=rgb.shape[1],image_height=rgb.shape[0],
        exif_orientation_applied=exif,status='accepted' if regions else 'rejected',reject_reason=None if regions else (reasons[0] if reasons else 'no_fingertip'),
        roi_xyxy=regions[0]['roi_xyxy'] if len(regions)==1 else None,pitch_native=regions[0]['pitch_native'] if len(regions)==1 else None,
        mask_path='fingerprint_mask.png',mask_sha256=digest(folder/'fingerprint_mask.png'),regions=regions,
        quality=dict(ground_truth_validated=False,new_proposals_require_review=True),rejection_reasons=reasons)
    (folder/'detection_timing.json').write_text(json.dumps(dict(detection_and_boundary_seconds=result['detection_seconds'],detection_seconds=result.get('candidate_generation_seconds',result['detection_seconds']),boundary_seconds=result.get('boundary_and_pitch_seconds',0.),artifact_seconds=time.perf_counter()-start),indent=2),encoding='utf-8')
    (folder/'detection.json').write_text(json.dumps(data,indent=2,sort_keys=True),encoding='utf-8')
    return folder/'detection.json'


def _box(value,w,h,square=False):
    if not isinstance(value,list) or len(value)!=4 or any(type(x)!=int for x in value):raise ValueError('invalid_roi')
    a,b,c,d=value
    if not 0<=a<c<=w or not 0<=b<d<=h or square and c-a!=d-b:raise ValueError('roi_out_of_bounds')
    return value


def _mask(folder,filename,expected,w,h):
    if not isinstance(filename,str) or not re.fullmatch(r'[A-Za-z0-9_-]+[.]png',filename):raise ValueError('non_relative_mask_path')
    path=folder/filename
    if path.is_symlink() or digest(path)!=expected:raise ValueError('mask_hash_mismatch')
    with Image.open(path) as im:
        if im.format!='PNG' or im.mode!='L' or im.size!=(w,h):raise ValueError('invalid_mask_shape_or_format')
        data=np.asarray(im)
    if not np.isin(data,[0,255]).all():raise ValueError('nonbinary_mask')
    return data==255


def validate_artifact(source,detection):
    rgb,source_hash,exif=read_input(source);path=Path(detection).resolve(strict=True);data=json.loads(path.read_text(encoding='utf-8'));h,w=rgb.shape[:2]
    if data.get('schema_version')!=SCHEMA:raise ValueError('schema_mismatch')
    if data.get('source_sha256')!=source_hash:raise ValueError('source_hash_mismatch')
    if type(data.get('image_width'))!=int or type(data.get('image_height'))!=int or (data['image_width'],data['image_height'])!=(w,h):raise ValueError('image_dimension_mismatch')
    if type(data.get('exif_orientation_applied'))!=bool or data['exif_orientation_applied']!=exif:raise ValueError('exif_mismatch')
    if data.get('decoded_rgb_sha256')!=hashlib.sha256(rgb.tobytes()).hexdigest():raise ValueError('decoded_rgb_mismatch')
    mask=_mask(path.parent,data['mask_path'],data['mask_sha256'],w,h);union=np.zeros((h,w),bool);regions=data.get('regions')
    if not isinstance(regions,list):raise ValueError('invalid_regions')
    if data.get('status')=='accepted' and (not regions or not mask.any()):raise ValueError('empty_accepted_mask')
    if data.get('status') not in ['accepted','rejected']:raise ValueError('invalid_status')
    if data['status']=='rejected' and (regions or mask.any()):raise ValueError('rejected_artifact_has_mask')
    for r in regions:
        box=_box(r['roi_xyxy'],w,h,True);_box(r['seed_roi'],w,h,True);pitch=r['pitch_native']
        if isinstance(pitch,bool) or not isinstance(pitch,(int,float)) or not np.isfinite(pitch) or not 2<=pitch<=50:raise ValueError('pitch_invalid')
        part=_mask(path.parent,r['mask_path'],r['mask_sha256'],w,h);a,b,c,d=box;outside=part.copy();outside[b:d,a:c]=False
        if not part.any() or outside.any() or (part&union).any():raise ValueError('invalid_region_mask_bounds_or_overlap')
        seed=r['seed_roi'];sx=(seed[0]+seed[2])//2;sy=(seed[1]+seed[3])//2
        if not part[sy,sx]:raise ValueError('seed_outside_mask')
        from scipy.ndimage import label
        if label(part)[1]!=1:raise ValueError('disconnected_region_mask')
        union|=part
    if not np.array_equal(union,mask):raise ValueError('mask_union_mismatch')
    return rgb,data,mask


def transform_artifact(source,detection,strength=.5):
    if isinstance(strength,bool) or strength not in (0.,.5):raise ValueError('invalid_strength')
    rgb,data,allowed=validate_artifact(source,detection)
    if strength==0 or data['status']=='rejected':return rgb.copy(),dict(applied=False,status='zero_strength' if strength==0 else 'rejected_artifact_unchanged',changed_pixels=0,outside_all_masks_preserved=True)
    import transform_automatic_fingerprint_poc_v4 as frozen
    import whole_pad_skin_relief as renderer
    import fingerprint_structure_check as structure
    import sourceafis_matcher as matcher
    from transform_automatic_fingerprint_poc_v4_boundaryblend_02 import transform_fingerprint_photo
    from protect_visible_pad_checked_v2 import observed_seed_pitch
    scoped={tuple(r['seed_roi']):r for r in data['regions']}
    for seed,r in scoped.items():
        pitch,_,_=observed_seed_pitch(rgb,list(seed))
        if pitch is None or abs(pitch-r['pitch_native'])>1e-6:raise ValueError('pitch_observation_mismatch')
    def scope(original,seed):
        if original.shape!=rgb.shape or not np.array_equal(original,rgb):raise ValueError('source_pixels_changed')
        r=scoped.get(tuple(seed))
        if r is None:raise ValueError('unknown_seed')
        part=_mask(Path(detection).resolve().parent,r['mask_path'],r['mask_sha256'],rgb.shape[1],rgb.shape[0]);a,b,c,d=r['roi_xyxy']
        return r['roi_xyxy'],part[b:d,a:c],r['quality']|dict(automatic_boundary_accepted=True,status='artifact_validated')
    with _LOCK:
        old=(frozen.detect_fingertips,frozen.propose_visible_pad,renderer.propose_visible_pad,structure.OUT,structure.run_matcher_job)
        try:
            frozen.detect_fingertips=lambda image:dict(candidates=[dict(seed_roi=r['seed_roi'],candidate_id=r['region_id']) for r in data['regions']],method=data['detector_version'])
            frozen.propose_visible_pad=scope;renderer.propose_visible_pad=scope
            structure.OUT=Path(tempfile.mkdtemp(prefix='blurfing_artifact_transform_'));structure.run_matcher_job=matcher.run_matcher_job
            start=time.perf_counter();returned,details=transform_fingerprint_photo(rgb,strength);details['transform_seconds']=time.perf_counter()-start
        finally:
            frozen.detect_fingertips,frozen.propose_visible_pad,renderer.propose_visible_pad,structure.OUT,structure.run_matcher_job=old
    if not np.array_equal(returned[~allowed],rgb[~allowed]):raise RuntimeError('boundary_exterior_changed')
    if digest(source)!=data['source_sha256']:raise RuntimeError('source_changed')
    details.update(artifact_source_verified=True,artifact_mask_pixels=int(allowed.sum()),boundary_exterior_preserved=True)
    return returned,details


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    for command in ['detect','consume']:
        q=sub.add_parser(command);q.add_argument('--input',required=True,type=Path);q.add_argument('--output',required=True,type=Path)
        if command=='consume':q.add_argument('--detection',required=True,type=Path);q.add_argument('--strength',type=float,choices=[0.,.5],default=.5)
    args=p.parse_args()
    if args.command=='detect':print(write_detection(args.input,args.output));return
    returned,details=transform_artifact(args.input,args.detection,args.strength);args.output.mkdir(parents=True,exist_ok=False)
    Image.fromarray(returned).save(args.output/'returned.png');(args.output/'details.json').write_text(json.dumps(details,indent=2),encoding='utf-8');print(json.dumps({'applied':details['applied'],'status':details['status']}))

if __name__=='__main__':main()
