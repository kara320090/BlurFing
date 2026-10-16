"""Experimental multirate raw-profile observations; never a renderer gate.

An external orientation is a proposal, not observed spacing. Only samples
from the supplied image contribute to profiles. FFT/ACF share those samples
and are not independent biometric evidence. No default period is generated.
"""
import hashlib
import cv2,numpy as np
from scipy.signal import find_peaks
from photo_pitch_spectrum_diagnostic_v1 import diagnose_profile

VERSION='multirate_raw_profile_pitch_v2_diagnostic'
SAMPLE_STEPS=tuple(float(2**(k/2)) for k in range(-2,5))


def _hash(value):return hashlib.sha256(value.tobytes()).hexdigest()


def observe(raw,permission,tangent):
    """512-square gray/permission, radians of undirected tangent in image x/y.

    Return canonical image pixels only. The caller must explicitly bind any
    native conversion to the actual square size. At least two sampling rates
    must independently supply six distinct patch centers and agree; changing
    rate does not create independent images or independent biological evidence.
    """
    if (not isinstance(raw,np.ndarray) or raw.dtype!=np.uint8 or raw.shape!=(512,512) or
            not isinstance(permission,np.ndarray) or permission.dtype!=np.bool_ or permission.shape!=raw.shape or
            not isinstance(tangent,np.ndarray) or tangent.shape!=raw.shape or tangent.dtype.kind!='f' or
            not np.isfinite(tangent).all()):raise ValueError('raw_profile_pitch_input_contract')
    pins=tuple(_hash(a) for a in (raw,permission,tangent));rates=[]
    normal=tangent-np.pi/2
    uu,vv=np.meshgrid(np.arange(-32,32,dtype=np.float32),np.arange(-12,12,dtype=np.float32))
    for step in SAMPLE_STEPS:
        image=raw.astype(np.float32)
        sigma=.5*np.sqrt(step*step-1) if step>1 else 0.
        if sigma>0:image=cv2.GaussianBlur(image,(0,0),float(sigma))
        rows=[];reasons={}
        for cy in range(48,465,48):
            for cx in range(48,465,48):
                patch=normal[cy-24:cy+24,cx-24:cx+24]
                sn=float(np.sin(2*patch).mean());cs=float(np.cos(2*patch).mean())
                if np.hypot(sn,cs)<.65:
                    reasons['direction_inconsistent']=reasons.get('direction_inconsistent',0)+1;continue
                theta=.5*np.arctan2(sn,cs)
                mx=(cx+step*(uu*np.cos(theta)-vv*np.sin(theta))).astype(np.float32)
                my=(cy+step*(uu*np.sin(theta)+vv*np.cos(theta))).astype(np.float32)
                x0=np.floor(mx).astype(int);x1=np.ceil(mx).astype(int);y0=np.floor(my).astype(int);y1=np.ceil(my).astype(int)
                # Include the Gaussian's finite OpenCV support before sampling;
                # source context outside permission cannot supply this evidence.
                radius=(int(round(4*float(sigma)))+1) if sigma>0 else 0
                left,right=x0.min()-radius,x1.max()+radius;top,bottom=y0.min()-radius,y1.max()+radius
                if (left<0 or top<0 or right>=512 or bottom>=512 or
                        not permission[top:bottom+1,left:right+1].all()):
                    reasons['profile_support_unavailable']=reasons.get('profile_support_unavailable',0)+1;continue
                profile=cv2.remap(image,mx,my,cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT).mean(0).astype(np.float64)
                axis=np.arange(64);profile-=np.polyval(np.polyfit(axis,profile,1),axis)
                if profile.std()<2:continue
                acf=np.array([np.dot(profile[:-lag],profile[lag:])/max(float(np.linalg.norm(profile[:-lag])*np.linalg.norm(profile[lag:])),1e-6) for lag in range(1,29)])
                peaks,_=find_peaks(acf,prominence=.15)
                peaks=[int(p) for p in peaks if 4<=p+1<=24 and acf[p]>=.6]
                if not peaks:continue
                k=peaks[0];period=float(k+1)
                if 0<k<len(acf)-1:
                    den=float(acf[k-1]-2*acf[k]+acf[k+1])
                    if abs(den)>1e-5:period+=float(np.clip(.5*(acf[k-1]-acf[k+1])/den,-.5,.5))
                spectral=diagnose_profile(profile,period)
                if spectral.get('dominant_bin') is None or abs(spectral['candidate_bin_offset'])>1:
                    reasons['spectral_disagreement']=reasons.get('spectral_disagreement',0)+1;continue
                rows.append(dict(x=cx,y=cy,period_samples=period,period_image_pixels=period*step,correlation=float(acf[k]),
                    spectral_bin=spectral['dominant_bin']))
        values=np.array([r['period_image_pixels'] for r in rows]);median=float(np.median(values)) if len(values) else None
        spread=float(np.subtract(*np.percentile(values,[75,25]))/median) if median else None
        valid=bool(len(rows)>=6 and spread<=.15)
        rates.append(dict(sample_step=step,anti_alias_sigma=float(sigma),distinct_centers=len(rows),
            period_image_pixels=median if valid else None,relative_IQR=spread,rows=rows,reasons=reasons))
    values=[r['period_image_pixels'] for r in rates if r['period_image_pixels'] is not None]
    agreed=bool(len(values)>=2 and (max(values)-min(values))/np.mean(values)<=.10)
    if tuple(_hash(a) for a in (raw,permission,tangent))!=pins:raise RuntimeError('raw_profile_inputs_changed')
    return dict(version=VERSION,status='diagnostic_observed_periodicity' if agreed else 'unavailable',
        period_image_pixels=float(np.median(values)) if agreed else None,rates=rates,
        raw_sha256=pins[0],permission_sha256=pins[1],tangent_sha256=pins[2],
        diagnostic_only=True,renderer_gate_modified=False,default_pitch_generated=False,
        physical_DPI_known=False,fundamental_ground_truth=False,independent_biometric_evidence=False,
        neural_enhanced_pixels_used=False,orientation_context_independence_claimed=False,default_enabled=False)
