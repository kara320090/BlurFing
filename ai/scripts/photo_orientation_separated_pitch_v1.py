"""Experimental fallback only: filtered orientation references; original raw profiles."""
import cv2,numpy as np
from scipy.signal import find_peaks
from highres_ridge_quality import orientation_field,RidgeQualityConfig
from photo_component_local_evidence_v1 import profile_supported

VERSION='photo_orientation_separated_pitch_v1_experimental'
SIGMAS=(2.,4.)

def measure(raw,roi,permission,sigma):
    if raw.dtype!=np.uint8 or raw.shape!=(512,512) or roi.dtype!=np.bool_ or permission.dtype!=np.bool_ or roi.shape!=raw.shape or permission.shape!=raw.shape:
        raise ValueError('oriented_raw_input_contract')
    if sigma not in SIGMAS:raise ValueError('unsupported_orientation_reference_sigma')
    if np.any(roi&~permission):raise ValueError('measurement_ROI_outside_permission')
    ref=cv2.GaussianBlur(raw.astype(np.float32),(0,0),sigma)
    tangent,coherence=orientation_field(ref,RidgeQualityConfig(tensor_sigma=5));normal=tangent-np.pi/2
    uu,vv=np.meshgrid(np.arange(-32,32,dtype=np.float32),np.arange(-12,12,dtype=np.float32));rows=[]
    for cy in range(48,465,48):
        for cx in range(48,465,48):
            region=np.s_[cy-24:cy+24,cx-24:cx+24]
            coh=float(coherence[region].mean())
            if float(roi[region].mean())<.95 or coh<.65:continue
            if not profile_supported(permission,normal,cx,cy):continue
            theta=.5*np.arctan2(float(np.mean(np.sin(2*normal[region]))),float(np.mean(np.cos(2*normal[region]))))
            mx=(cx+uu*np.cos(theta)-vv*np.sin(theta)).astype(np.float32);my=(cy+uu*np.sin(theta)+vv*np.cos(theta)).astype(np.float32)
            profile=cv2.remap(raw.astype(np.float32),mx,my,cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT_101).mean(axis=0)
            axis=np.arange(64);profile-=np.polyval(np.polyfit(axis,profile,1),axis);contrast=float(profile.std())
            if contrast<2:continue
            acf=np.array([np.dot(profile[:-lag],profile[lag:])/max(float(np.linalg.norm(profile[:-lag])*np.linalg.norm(profile[lag:])),1e-6) for lag in range(1,29)])
            peaks,_=find_peaks(acf,prominence=.15)
            # Keep the existing first credible periodic peak; do not search by outcome.
            peaks=[int(p) for p in peaks if 4<=p+1<=24 and acf[p]>=.25]
            if not peaks:continue
            k=peaks[0];pitch=float(k+1)
            if 0<k<len(acf)-1:
                den=float(acf[k-1]-2*acf[k]+acf[k+1])
                if abs(den)>1e-5:pitch+=float(np.clip(.5*(acf[k-1]-acf[k+1])/den,-.5,.5))
            if float(acf[k])<.6:continue
            rows.append(dict(x=cx,y=cy,pitch=pitch,correlation=float(acf[k]),coherence=coh,profile_contrast=contrast))
    pitches=np.array([r['pitch'] for r in rows]);median=float(np.median(pitches)) if len(pitches) else None
    spread=float((np.quantile(pitches,.75)-np.quantile(pitches,.25))/median) if median else None
    accepted=bool(len(rows)>=3 and 4<=median<=24 and spread<=.15)
    return dict(status='accepted' if accepted else 'insufficient' if len(rows)<3 else 'inconsistent',
        pitch=median if accepted else None,credible_patches=len(rows),relative_IQR=spread,rows=rows,sigma=sigma)

def observe(raw,roi,permission):
    refs=[measure(raw,roi,permission,sigma) for sigma in SIGMAS]
    if any(r['pitch'] is None for r in refs):return None,dict(status='reference_unavailable',references=refs)
    pitches=[r['pitch'] for r in refs];difference=float(abs(pitches[0]-pitches[1])/np.mean(pitches))
    if difference>.10:return None,dict(status='reference_disagreement',relative_difference=difference,references=refs)
    return float(np.mean(pitches)),dict(status='observed_raw_with_filtered_orientation',relative_difference=difference,references=refs,
        profile_from_original_raw=True,independent_biometric_evidence=False,numeric_thresholds_relaxed=False)

def observed_component_pitch(original,box,permission):
    import hashlib
    from fingerprint_poc_core import prepare_fingerprint
    from protect_contactless_delta import normalize_contactless
    if (original.dtype!=np.uint8 or original.ndim!=3 or original.shape[2]!=3 or
            permission.dtype!=np.bool_ or permission.shape!=original.shape[:2]):
        raise ValueError('component_pitch_RGB_permission_contract')
    if len(box)!=4 or any(isinstance(v,(bool,np.bool_)) or not isinstance(v,(int,np.integer)) for v in box):
        raise ValueError('component_pitch_square_contract')
    a,b,c,d=box
    if not 0<=a<c<=original.shape[1] or not 0<=b<d<=original.shape[0] or c-a!=d-b:
        raise ValueError('component_pitch_square_contract')
    gray=cv2.cvtColor(original[b:d,a:c],cv2.COLOR_RGB2GRAY)
    raw=cv2.resize(gray,(512,512),interpolation=cv2.INTER_CUBIC if len(gray)<512 else cv2.INTER_AREA)
    allowed=cv2.resize(permission[b:d,a:c].astype(np.uint8),(512,512),interpolation=cv2.INTER_NEAREST)>0
    meta=dict(observer_version=VERSION,observation_permission_restricted=True,
        permission512_sha256=hashlib.sha256(allowed.tobytes()).hexdigest(),permission512_pixels=int(allowed.sum()),
        profile_sampling_inside_permission_required=True,profile_from_original_raw=True,
        preprocessing_context_independence_claimed=False,numeric_thresholds_relaxed=False,
        orientation_reference_sigmas=list(SIGMAS),frozen_gate_equivalence=False,physical_dpi_known=False)
    try:roi=prepare_fingerprint(normalize_contactless(raw))[0]['roi']&allowed
    except ValueError as error:
        if not any(s in str(error) for s in ['No fingerprint ROI found','No ridge skeleton found','No refined ridge skeleton found']):raise
        return None,meta|dict(status='no_ridges',reason=str(error)),raw
    pitch,report=observe(raw,roi,allowed)
    return (None if pitch is None else pitch*(c-a)/512),meta|report|dict(pitch512=pitch),raw
