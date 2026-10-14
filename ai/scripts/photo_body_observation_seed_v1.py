"""Observe same-owner RGB beyond a thin permission mask; never expand output.

Seed centers come from predicted pixels, every seed pixel must be inside the
same observed body, and the unchanged frozen observer chooses actual pitch.
The fixed observation budget is engineering-only, not calibrated confidence.
"""
import hashlib
import cv2
import numpy as np
from scipy import ndimage
import photo_region_pipeline_v1 as shared

VERSION='body_supported_observation_seeds_v1_experimental'
MAX_SEEDS=8


def seeds(mask,body):
    if mask.dtype!=np.bool_ or body.dtype!=np.bool_ or mask.shape!=body.shape or mask.ndim!=2 or not mask.any() or np.any(mask&~body):
        raise ValueError('body_observation_mask_contract')
    shared.validate_resize(*mask.shape,1.)
    distances=cv2.distanceTransform(np.pad(body.astype(np.uint8),1),cv2.DIST_L2,5)[1:-1,1:-1]
    labels,count=ndimage.label(mask);rows=[]
    # Choose observation anchors from every fragment, prioritizing available
    # body support. This changes neither prediction pixels nor their ownership.
    for component,window in enumerate(ndimage.find_objects(labels),1):
        candidate=labels[window]==component;values=np.where(candidate,distances[window],-1.)
        y,x=np.unravel_index(np.argmax(values),values.shape);y+=window[0].start;x+=window[1].start
        half=int(distances[y,x]/np.sqrt(2)*.9)
        if half<4:continue
        box=[int(x-half),int(y-half),int(x+half),int(y+half)]
        a,b,c,d=box
        if 0<=a<c<=mask.shape[1] and 0<=b<d<=mask.shape[0] and body[b:d,a:c].all():
            rows.append(dict(box=box,center_yx=[int(y),int(x)],side=c-a,fragment=component,fully_inside_observed_body=True))
    rows.sort(key=lambda r:(-r['side'],r['box'][1],r['box'][0],r['fragment']))
    selected=[];seen=set()
    for row in rows:
        key=tuple(row['box'])
        if key not in seen:selected.append(row);seen.add(key)
        if len(selected)>=MAX_SEEDS:break
    return selected


def prepare_region(rgb,gray,mask,body,orientation,source_sha,plan,association,*,_proposals=None,_width_preflight=False):
    scale=plan['working_scale'];upright=shared.orient(rgb,orientation)
    shape,audit=shared.validate_resize(*upright.shape[:2],scale)
    axis=shared.orient_axis(association['axis_native_yx'],orientation,[shape[0]/upright.shape[0],shape[1]/upright.shape[1]])
    working=cv2.resize(upright,(shape[1],shape[0]),interpolation=cv2.INTER_AREA if scale<1 else cv2.INTER_CUBIC)
    working_mask=cv2.resize(shared.orient(mask.astype(np.uint8),orientation),(shape[1],shape[0]),interpolation=cv2.INTER_NEAREST)>0
    working_body=cv2.resize(shared.orient(body.astype(np.uint8),orientation),(shape[1],shape[0]),interpolation=cv2.INTER_NEAREST)>0
    proposals=seeds(working_mask,working_body) if _proposals is None else _proposals(working_mask,working_body,mask.shape,orientation,shape,association)
    attempts=[];chosen=None;width_failure=False
    for proposal in proposals:
        box=proposal['box']
        width=None
        if _width_preflight:
            from contactless_finger_width_body_v1 import estimate_finger_width_body
            width=estimate_finger_width_body(working,box,axis,working_body)
            if width['status']!='estimated':
                attempts.append(proposal|dict(width_preflight=width,observed_pitch_working=None));width_failure=True;continue
        pitch,measurement,_=shared.observed_seed_pitch(working,box)
        attempts.append(proposal|dict(observed_pitch_working=pitch,measurement=measurement,
                        seed_RGB_sha256=hashlib.sha256(working[box[1]:box[3],box[0]:box[2]].tobytes()).hexdigest()))
        if width is not None:attempts[-1]['width_preflight']=width
        if pitch is not None and 2<=pitch<=50:chosen=(proposal,pitch,measurement);break
    geometry=dict(working_scale=scale,working_shape=list(shape),axis_working_yx=axis,
        actual_resize_yx=[shape[0]/upright.shape[0],shape[1]/upright.shape[1]],resize_audit=audit,
        observation_policy=VERSION,observation_seed_attempts=attempts,permission_mask_expanded=False)
    if chosen is None:return None,geometry|dict(reject_reason='original_width_unavailable' if width_failure and len(attempts)==1
        else 'body_supported_pitch_unobserved' if proposals else 'body_supported_seed_unavailable')
    proposal,pitch,measurement=chosen;seed=proposal['box']
    y,x=np.where(mask);_,quality=shared.ridge_evidence(gray[y.min():y.max()+1,x.min():x.max()+1],mask[y.min():y.max()+1,x.min():x.max()+1])
    quality|=dict(pitch_native=float(pitch/scale),pitch_source='frozen_observed_seed_pitch_body_supported_seed',
                 confidence_semantics='ridge credible-window fraction; unapproved mask and observation geometry')
    roi=shared.canonical_roi(gray,mask,source_sha,'PHOTO',quality,VERSION);roi.validate(rgb,source_sha)
    scope,padding=shared.square_scope(working_mask)
    _,padding_audit=shared.validate_resize(shape[0]+padding['bottom'],shape[1]+padding['right'],1.)
    audit['square_padding_allocation']=padding_audit
    entry=dict(roi=roi,working_seed=seed,working_scope=scope,padding=padding,pitch_measurement=measurement,component=plan['component'])
    artifact=dict(source_sha256=source_sha,source_rgb_sha256=hashlib.sha256(rgb.tobytes()).hexdigest(),exif_orientation=orientation,
        working_shape=shape,working_scale=scale,regions=[entry],coarse_mask=mask,body=body)
    return artifact,geometry|dict(reject_reason=None,working_seed=seed,observed_pitch_working=pitch,observed_pitch_native=float(pitch/scale))
