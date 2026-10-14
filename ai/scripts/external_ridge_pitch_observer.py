"""GT-free local structure-tensor orientation + ACF/FFT observer v1.

Rules fixed before development inference: frozen coherence .65, contrast 2,
minimum six patches, existing relative IQR .15; ACF >=.6, prominence .15;
FFT peak +/- one bin holds >=50% in-band energy. Range 2..50 pixels is the
renderer contract, not a calibrated physical DPI claim. Cues share a profile
and are complementary estimators, not statistically independent evidence.
"""
import hashlib
import cv2,numpy as np
from scipy.signal import find_peaks
from external_pitch_evidence import ExternalPitchEvidence,MIN_PATCHES,MAX_RELATIVE_DIFFERENCE
from highres_ridge_quality import orientation_field,RidgeQualityConfig

def observe(image,mask,source_sha,image_scale=1.,coordinate_space='native_source_pixels'):
    gray=cv2.cvtColor(image,cv2.COLOR_RGB2GRAY) if image.ndim==3 else image
    if gray.dtype!=np.uint8 or mask.shape!=gray.shape or mask.dtype!=np.bool_ or not mask.any():raise ValueError('image_mask_contract')
    tangent,coherence=orientation_field(gray,RidgeQualityConfig(tensor_sigma=5));normal=tangent-np.pi/2;u,v=np.meshgrid(np.arange(-64,64,dtype=np.float32),np.arange(-12,12,dtype=np.float32));records=[];tested=0;oriented=0
    for y in range(80,gray.shape[0]-80,64):
        for x in range(80,gray.shape[1]-80,64):
            region=np.s_[y-24:y+24,x-24:x+24]
            if mask[region].mean()<.95:continue
            tested+=1
            if coherence[region].mean()<.65:continue
            oriented+=1;theta=.5*np.arctan2(np.sin(2*normal[region]).mean(),np.cos(2*normal[region]).mean());mx=(x+u*np.cos(theta)-v*np.sin(theta)).astype(np.float32);my=(y+u*np.sin(theta)+v*np.cos(theta)).astype(np.float32)
            coverage=cv2.remap(mask.astype(np.uint8),mx,my,cv2.INTER_NEAREST,borderMode=cv2.BORDER_CONSTANT).mean()
            if coverage<.95:continue
            profile=cv2.remap(gray.astype(np.float32),mx,my,cv2.INTER_LINEAR).mean(0);axis=np.arange(128);profile-=np.polyval(np.polyfit(axis,profile,1),axis)
            if profile.std()<2:continue
            ac=np.array([np.dot(profile[:-lag],profile[lag:])/max(float(np.linalg.norm(profile[:-lag])*np.linalg.norm(profile[lag:])),1e-9) for lag in range(1,52)]);peaks,_=find_peaks(ac,prominence=.15);peaks=[k for k in peaks if 2<=k+1<=50 and ac[k]>=.6]
            if not peaks:continue
            k=peaks[0];den=ac[k-1]-2*ac[k]+ac[k+1];ap=float(k+1+(.5*(ac[k-1]-ac[k+1])/den if abs(den)>1e-9 else 0))
            spectrum=abs(np.fft.rfft(profile*np.hanning(128)))**2;frequency=np.fft.rfftfreq(128);valid=(frequency>=1/50)&(frequency<=1/2);indices=np.flatnonzero(valid);j=int(indices[np.argmax(spectrum[valid])]);energy=float(spectrum[max(1,j-1):j+2].sum()/max(1e-9,spectrum[valid].sum()));log=np.log(spectrum+1e-12);den=log[j-1]-2*log[j]+log[j+1] if j+1<len(log) else 0;delta=.5*(log[j-1]-log[j+1])/den if abs(den)>1e-9 else 0;fp=float(128/(j+delta));difference=abs(ap-fp)/((ap+fp)/2)
            records.append(dict(x=x,y=y,autocorrelation=ap,fft=fp,correlation=float(ac[k]),spectral_energy_fraction=energy,coherence=float(coherence[region].mean()),orientation_deg=float(np.degrees(theta)),accepted=bool(2<=ap<=50 and 2<=fp<=50 and energy>=.5 and difference<=.15)))
    accepted=[r for r in records if r['accepted']];ap=float(np.median([r['autocorrelation'] for r in accepted])) if accepted else None;fp=float(np.median([r['fft'] for r in accepted])) if accepted else None;pitches=np.array([(r['autocorrelation']+r['fft'])/2 for r in accepted]);spread=float((np.percentile(pitches,75)-np.percentile(pitches,25))/np.median(pitches)) if len(pitches) else None;enough=len(accepted)>=MIN_PATCHES;agreement=bool(enough and abs(ap-fp)/((ap+fp)/2)<=.15 and spread<=.15);status='accepted' if agreement else 'cue_disagreement' if enough else 'insufficient_patches' if accepted else 'unstable_orientation' if tested and not oriented else 'no_periodicity'
    angle=float(np.degrees(.5*np.arctan2(np.mean([np.sin(np.radians(2*r['orientation_deg'])) for r in accepted]),np.mean([np.cos(np.radians(2*r['orientation_deg'])) for r in accepted])))) if accepted else 0.
    evidence=ExternalPitchEvidence((ap+fp)/2 if agreement else None,'pixels',coordinate_space,image_scale,angle,'acf_fft_ridge_patches','1.0',tested,len(accepted),dict(autocorrelation=dict(valid=ap is not None,pitch=ap),fft=dict(valid=fp is not None,pitch=fp),patches=records),dict(passed=agreement,orientation_consistent=bool(accepted),relative_IQR=spread), '',source_sha,hashlib.sha256(mask.tobytes()).hexdigest(),list(gray.shape),status)
    evidence.observed_image_pixel_sha256=hashlib.sha256(gray.tobytes()).hexdigest()
    return evidence.seal()
