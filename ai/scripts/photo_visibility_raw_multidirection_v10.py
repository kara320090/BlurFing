"""Undetrended local trains without a whole-ring axial veto; diagnostic only.

Residuals propose periodicity, but must not substitute for actual alternating
intensity. Preserve V9 raw-extrema proof and constants; replace the ring veto with that proof. Very strong
shading may obscure real raw extrema; absence is never inferred from failure.
"""
import cv2
import numpy as np
from scipy import ndimage, signal
from photo_visibility_peak_train_probe_v4 import CONFIG
from photo_visibility_peak_train_probe_v5 import _probe_level


def peak_train(profile, proposed_period):
    raw=profile.astype(np.float64)
    residual=raw-ndimage.gaussian_filter1d(raw,proposed_period*1.5,mode='reflect')
    residual=ndimage.gaussian_filter1d(residual,.5,mode='reflect')
    std=float(residual.std())
    if std*std<=2./12.:return None
    prominence=max(2*np.sqrt(1./12.),CONFIG.prominence_std_fraction*std)
    distance=max(2,int(np.floor(proposed_period*.5)))
    smoothed_raw=ndimage.gaussian_filter1d(raw,.5,mode='reflect')
    peaks,_=signal.find_peaks(smoothed_raw,prominence=prominence,distance=distance)
    troughs,_=signal.find_peaks(-smoothed_raw,prominence=prominence,distance=distance)
    for count in range(len(peaks),CONFIG.min_peaks-1,-1):
        for start in range(len(peaks)-count+1):
            run=peaks[start:start+count];gaps=np.diff(run)
            period=float(np.median(gaps));cv=float(gaps.std()/gaps.mean())
            if abs(period-proposed_period)/proposed_period>CONFIG.max_period_disagreement or cv>CONFIG.max_spacing_cv:continue
            if any(not np.any((troughs>a)&(troughs<b)) for a,b in zip(run[:-1],run[1:])):continue
            return dict(period_pixels=period,peak_count=len(run),spacing_cv=cv,residual=residual,
                        run_start=int(run[0]),run_end=int(run[-1]),total_profile_peaks=len(peaks),
                        whole_profile_train=(len(run)==len(peaks)),extrema_witness='smoothed_undetrended_intensity')
    return None


def inspect_patch(patch,geometry):
    n=patch.shape[0];hann,fx,fy,radius,band=geometry
    residual=patch-cv2.GaussianBlur(patch,(0,0),n/8,borderType=cv2.BORDER_REFLECT_101)
    if float(np.mean(residual**2))<=2./12.:return None,'quantization_floor'
    power=np.abs(np.fft.fft2(residual*hann))**2
    floor=max(float(np.median(power[band])),np.finfo(float).eps*max(float(power.sum()),1.))
    candidates=[]
    for index in np.argsort(np.where(band,power,-1).ravel())[::-1]:
        pos=np.unravel_index(index,power.shape)
        if not band[pos] or power[pos]/floor<CONFIG.min_peak_to_noise:break
        vector=np.array([fx[pos],fy[pos]])
        if any(min(np.linalg.norm(vector-v),np.linalg.norm(vector+v))<=1./n for _,v in candidates):continue
        candidates.append((pos,vector))
        if len(candidates)==CONFIG.max_hypotheses:break
    direction_pass=0
    for pos,vector in candidates:
        f=float(radius[pos]);theta=float(np.arctan2(vector[1],vector[0]));ring=band&(np.abs(radius-f)<1./n)
        angles=np.arctan2(fy[ring],fx[ring]);weights=power[ring]
        axial=float(abs(np.sum(weights*np.exp(2j*angles)))/max(float(weights.sum()),1e-12))
        # V10: direction is proposed spectrally but certified in original strips.
        # A different crease direction in the full ring is not a veto.
        direction_pass+=1;profiles=[]
        u=np.arange(n-8,dtype=np.float32)-(n-9)/2
        for offset in (-2.,2.):
            v=np.array([offset-1,offset,offset+1],dtype=np.float32)[:,None]
            mx=(n-1)/2+u[None,:]*np.cos(theta)-v*np.sin(theta)
            my=(n-1)/2+u[None,:]*np.sin(theta)+v*np.cos(theta)
            values=cv2.remap(patch.astype(np.float32),mx.astype(np.float32),my.astype(np.float32),interpolation=cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
            result=peak_train(values.mean(axis=0),1./f)
            if result is None:break
            profiles.append(result)
        if len(profiles)!=2:continue
        periods=[r['period_pixels'] for r in profiles]
        if abs(periods[0]-periods[1])/max(periods)>CONFIG.max_period_disagreement:continue
        common_start=max(r['run_start'] for r in profiles);common_end=min(r['run_end'] for r in profiles)
        if common_end<=common_start:continue
        a,b=[r['residual'] for r in profiles];a=a-a.mean();b=b-b.mean()
        agreement=float(np.clip(a@b/max(np.linalg.norm(a)*np.linalg.norm(b),1e-12),-1.,1.))
        if agreement<CONFIG.min_strip_agreement:continue
        return dict(working_period_pixels=float(np.mean(periods)),normal_angle_radians=theta,
                    ring_axial=axial,strip_agreement=agreement,common_run_span=[common_start,common_end],
                    profiles=[{k:v for k,v in r.items() if k!='residual'} for r in profiles]),'accepted'
    return None,'raw_peak_train' if direction_pass else 'spectral_direction'


def probe_level(gray,support,max_side):
    result=_probe_level(gray,support,max_side,inspect_patch,'photo_visibility_raw_multidirection_v10')
    result['config'].pop('min_ring_axial')
    result['config']['ring_axial_used_as_gate']=False
    result['config']['raw_train_selection']='longest_contiguous_undetrended_run_min_four_crests_and_troughs'
    return result
