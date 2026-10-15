"""Local permission evidence without deleting fragments or changing thresholds."""
import hashlib
import cv2
import numpy as np
from scipy import ndimage
from photo_owner_partition_v1 import partition
from photo_learned_pad_pipeline_v1 import MAX_COMPONENTS
from fingerprint_poc_core import prepare_fingerprint
from protect_contactless_delta import normalize_contactless
from contactless_ridge_pitch import estimate_ridge_pitch
from single_ridge_naturalizer_v2 import select_observed_pitch
from diagnose_ridge_measurement_noise import credible_estimate
from highres_ridge_quality import orientation_field,RidgeQualityConfig


def connected_partition(mask,contexts):
    grouped=partition(mask,contexts)
    labels=np.zeros(mask.shape,np.uint16);records=[]
    for parent in grouped['records']:
        local,count=ndimage.label(grouped['labels']==parent['plan']['component'])
        if len(records)+count>MAX_COMPONENTS:raise ValueError('connected_permission_resource_limit')
        for part,window in enumerate(ndimage.find_objects(local),1):
            native=local[window]==part;component=len(records)+1
            labels[window][native]=component
            identity=(parent.get('candidate_id') or 'unassigned')+f':permission-{part:04d}'
            association=parent['association']
            if association is not None:
                association=association|dict(candidate_id=identity,permission_component=part,
                    authorization_policy='each_connected_permission_component_requires_own_evidence')
            records.append(parent|dict(candidate_id=identity,association=association,
                plan=parent['plan']|dict(component=component,mask_pixels=int(native.sum()))))
    if not np.array_equal(labels>0,mask):raise ValueError('connected_permission_pixel_loss')
    return dict(labels=labels,records=records)


def profile_supported(permission,normal,cx,cy):
    """Require the actual bilinear remap footprint and tensor window inside."""
    if not permission[cy-24:cy+24,cx-24:cx+24].all():return False
    window=np.s_[cy-24:cy+24,cx-24:cx+24]
    theta=.5*np.arctan2(float(np.mean(np.sin(2*normal[window]))),float(np.mean(np.cos(2*normal[window]))))
    uu,vv=np.meshgrid(np.arange(-32,32,dtype=np.float32),np.arange(-12,12,dtype=np.float32))
    mx=(cx+uu*np.cos(theta)-vv*np.sin(theta)).astype(np.float32)
    my=(cy+uu*np.sin(theta)+vv*np.cos(theta)).astype(np.float32)
    x0=np.floor(mx).astype(int);x1=np.ceil(mx).astype(int);y0=np.floor(my).astype(int);y1=np.ceil(my).astype(int)
    if x0.min()<0 or y0.min()<0 or x1.max()>=permission.shape[1] or y1.max()>=permission.shape[0]:return False
    return bool(permission[y0,x0].all() and permission[y0,x1].all() and permission[y1,x0].all() and permission[y1,x1].all())


def estimate_local_pitch(gray,roi,permission):
    measured=estimate_ridge_pitch(gray,roi)
    tangent,_=orientation_field(gray,RidgeQualityConfig(tensor_sigma=5));normal=tangent-np.pi/2
    accepted=[m for m in measured['measurements'] if profile_supported(permission,normal,m['x'],m['y'])]
    # Same frozen reducer and numeric criteria, after geometric support checks.
    if len(accepted)<6:
        return dict(status='insufficient_periodic_patches',pitch=None,count=len(accepted),measurements=accepted,physical_dpi_known=False)
    pitches=np.array([m['pitch'] for m in accepted]);median=float(np.median(pitches));mad=float(np.median(np.abs(pitches-median)))
    inliers=pitches[np.abs(pitches-median)<=max(2,3*mad)]
    return dict(status='estimated',pitch=float(np.median(inliers)),count=len(accepted),inlier_count=len(inliers),
                pitch_mad=mad,measurements=accepted,physical_dpi_known=False,identity_matcher_selection_used=False)


def two_scale_local(raw,mask,permission):
    estimates=[]
    for sigma in [1.2,1.8]:
        estimate=estimate_local_pitch(cv2.GaussianBlur(raw,(0,0),sigma),mask,permission)
        estimates.append(dict(sigma=sigma,estimate=estimate,selection=credible_estimate(estimate)))
    pitches=[e['selection']['pitch'] for e in estimates]
    if any(p is None for p in pitches):return dict(status='unavailable',pitch=None,scales=estimates,physical_dpi_known=False)
    difference=float(abs(pitches[0]-pitches[1])/np.mean(pitches))
    if difference>.10:return dict(status='scale_disagreement',pitch=None,relative_difference=difference,scales=estimates,physical_dpi_known=False)
    return dict(status='observed_partial_two_scale',pitch=float(np.mean(pitches)),relative_difference=difference,
                scales=estimates,physical_dpi_known=False,real_pitch_ground_truth=False)


def observed_component_pitch(original,box,permission):
    if (original.dtype!=np.uint8 or original.ndim!=3 or original.shape[2]!=3 or
            permission.dtype!=np.bool_ or permission.shape!=original.shape[:2]):
        raise ValueError('component_pitch_RGB_permission_contract')
    a,b,c,d=box
    if not 0<=a<c<=original.shape[1] or not 0<=b<d<=original.shape[0] or c-a!=d-b:
        raise ValueError('component_pitch_square_contract')
    gray=cv2.cvtColor(original[b:d,a:c],cv2.COLOR_RGB2GRAY)
    raw=cv2.resize(gray,(512,512),interpolation=cv2.INTER_CUBIC if len(gray)<512 else cv2.INTER_AREA)
    allowed=cv2.resize(permission[b:d,a:c].astype(np.uint8),(512,512),interpolation=cv2.INTER_NEAREST)>0
    provenance=dict(observation_permission_restricted=True,
        permission512_sha256=hashlib.sha256(allowed.tobytes()).hexdigest(),
        permission512_pixels=int(allowed.sum()),thresholds_changed=False,profile_sampling_inside_permission_required=True,
        preprocessing_context_independence_claimed=False)
    try:mask=prepare_fingerprint(normalize_contactless(raw))[0]['roi']&allowed
    except ValueError as exc:
        if not any(s in str(exc) for s in ['No fingerprint ROI found','No ridge skeleton found','No refined ridge skeleton found']):raise
        return None,provenance|dict(status='no_ridges',reason=str(exc)),raw
    attempts=[]
    for label,frame in [('Raw',raw),('Bilateral5_8_3',cv2.bilateralFilter(raw,5,8,3))]:
        measurement=estimate_local_pitch(frame,mask,allowed);selected=select_observed_pitch(measurement)
        attempts.append(dict(preprocessing=label,measurement=measurement,selection=selected))
        if selected['pitch'] is not None:
            return selected['pitch']*(c-a)/512,provenance|dict(attempts=attempts,selected=label,pitch512=selected['pitch']),raw
    measurement=two_scale_local(raw,mask,allowed);attempts.append(dict(preprocessing='TwoScaleGaussian1.2_1.8',measurement=measurement))
    pitch=measurement['pitch']
    return (None if pitch is None else pitch*(c-a)/512,
            provenance|dict(attempts=attempts,selected=None if pitch is None else 'TwoScaleGaussian1.2_1.8',pitch512=pitch),raw)
