import cv2

import numpy as np

from visible_pad_scope_v3 import propose_visible_pad

from irregular_synthetic_ridge_field import independent_irregular_field

from organic_ridge_profile import render_photographic_profile

from independent_skin_relief import independent_skin_relief

def synthetic_boundary_taper(mask,pitch_native):
    if mask.ndim!=2 or mask.dtype!=np.bool_ or not mask.any():raise ValueError('Nonempty Boolean mask required')
    if not np.isfinite(pitch_native) or not 2<=pitch_native<=50:raise ValueError('Observed pitch required')
    padded=np.pad(mask.astype(np.uint8),1,constant_values=0)
    distance=cv2.distanceTransform(padded,cv2.DIST_L2,cv2.DIST_MASK_PRECISE)[1:-1,1:-1]
    t=np.clip((distance-.5)/max(1.,pitch_native*1.25),0,1)
    return (t*t*(3-2*t))*mask

def render_whole_pad_candidate(original,seed_roi,*,pitch_native,seed):
    if not np.isfinite(pitch_native) or not 2<=pitch_native<=50:raise ValueError('Observed native pitch required')
    scope,mask,meta=propose_visible_pad(original,seed_roi)
    if scope is None:return original.copy(),dict(status=meta['status'],scope=meta,rendered=False)
    a,b,c,d=scope;crop=original[b:d,a:c];n=c-a;pitch512=pitch_native*512/n
    mask512=cv2.resize(mask.astype(np.uint8),(512,512),interpolation=cv2.INTER_NEAREST)>0
    field,recipe=independent_irregular_field(mask512,pitch512,seed)
    profile,profile_meta=render_photographic_profile(field,mask512,pitch512,seed)
    native=cv2.resize(profile,(n,n),interpolation=cv2.INTER_CUBIC if n>512 else cv2.INTER_AREA)
    m=mask.astype(np.float32);sigma=max(1.,pitch_native*1.2);support=cv2.GaussianBlur(m,(0,0),sigma)
    low=np.stack([cv2.GaussianBlur(crop[:,:,k].astype(np.float32)*m,(0,0),sigma)/np.maximum(support,1e-5) for k in range(3)],axis=2)
    gray=cv2.cvtColor(crop,cv2.COLOR_RGB2GRAY).astype(np.float32);low_gray=np.sum(low*np.array([.299,.587,.114],np.float32),axis=2)
    x0,y0,x1,y1=seed_roi;seed_gray=cv2.cvtColor(original[y0:y1,x0:x1],cv2.COLOR_RGB2GRAY).astype(np.float32)
    seed_low=cv2.GaussianBlur(seed_gray,(0,0),sigma);reference_rms=max(1.,float(np.sqrt(np.mean((seed_gray-seed_low)**2))))
    variance=cv2.GaussianBlur((gray-low_gray)**2*m,(0,0),max(2.,pitch_native*2))/np.maximum(cv2.GaussianBlur(m,(0,0),max(2.,pitch_native*2)),1e-5)
    amplitude=np.clip(np.sqrt(variance),reference_rms*.5,reference_rms*1.5)*1.0
    noise,noise_meta=independent_skin_relief(mask,pitch_native,seed)
    rms=float(np.sqrt(np.mean(noise[mask]**2)))
    if rms>0:noise*=reference_rms*.45/rms
    taper=synthetic_boundary_taper(mask,pitch_native)
    generated=np.rint(np.clip(low+((amplitude*.85*native+noise)*taper)[...,None],0,255)).astype(np.uint8)
    rendered=crop.copy();rendered[mask]=generated[mask];candidate=original.copy();candidate[b:d,a:c]=rendered
    assert np.array_equal(rendered[~mask],crop[~mask])
    return candidate,dict(status='unvalidated_skin_relief_candidate',rendered=True,scope=meta,roi_xyxy=scope,
        pitch_native=pitch_native,pitch512=pitch512,seed_pitch_extrapolated=True,seed=seed,
        field=recipe,profile=profile_meta,texture=noise_meta,reference_rms=reference_rms,ridge_contrast_gain=.85,
        synthetic_boundary_taper_pitch=1.25,taper_uses_padded_mask=True,
        original_highpass_boundary_blend=False,original_highpass_retained_inside_mask=False,original_rgb_highpass_input=False,
        masked_normalized_rgb_lowpass=True,original_outside_mask_preserved=True,
        strength='fixed_full_replacement_prototype',human_naturalness_validated=False,privacy_validated=False,
        automatically_adopted=False,scope_human_verified=False)
