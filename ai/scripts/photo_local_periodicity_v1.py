"""Native 64px local-periodicity experiment; not fingerprint identity/pitch API.

Retains existing support/coherence/contrast/ACF/FFT/agreement criteria. Shorter
profiles require two complete cycles and are sampled at half-profile stride.
Overlapping windows are explicitly not independent biometric evidence.
"""
import hashlib,math
import cv2
import numpy as np
from scipy.signal import find_peaks
from external_pitch_evidence import MIN_PATCHES,MAX_RELATIVE_DIFFERENCE
from highres_ridge_quality import orientation_field,RidgeQualityConfig
from ridge_evidence_frontend import axial_summary
from photo_resize_safety_v1 import validate_resize

VERSION='photo_local_periodicity_v1_experimental'
PROFILE_LENGTH=64
TANGENTIAL_HEIGHT=24
STRIDE=PROFILE_LENGTH//2
MARGIN=math.ceil(math.hypot(PROFILE_LENGTH/2,TANGENTIAL_HEIGHT/2))+1
MAX_PERIOD=min(50.,(PROFILE_LENGTH-1)/2)


def observe(gray,mask):
    if (not isinstance(gray,np.ndarray) or gray.ndim!=2 or gray.dtype!=np.uint8 or min(gray.shape)<1 or
            not isinstance(mask,np.ndarray) or mask.dtype!=np.bool_ or mask.shape!=gray.shape):
        raise ValueError('local_periodicity_image_mask_contract_mismatch')
    validate_resize(*gray.shape,1.)
    pixel_sha=lambda array:hashlib.sha256(array.tobytes()).hexdigest()
    before=[pixel_sha(gray),pixel_sha(mask)]
    centers=[(y,x) for y in range(MARGIN,gray.shape[0]-MARGIN,STRIDE)
                     for x in range(MARGIN,gray.shape[1]-MARGIN,STRIDE)]
    counts=dict(grid_capacity=len(centers),central_mask=0,orientation=0,profile_mask=0,contrast=0,ACF=0,accepted=0)
    records=[];support=np.zeros_like(mask)
    if centers and mask.any():
        tangent,coherence=orientation_field(gray,RidgeQualityConfig(tensor_sigma=5))
        normal=tangent-np.pi/2;frame=gray.astype(np.float32);allowed=mask.astype(np.uint8)
        u,v=np.meshgrid(np.arange(-PROFILE_LENGTH//2,PROFILE_LENGTH//2,dtype=np.float32),
                        np.arange(-TANGENTIAL_HEIGHT//2,TANGENTIAL_HEIGHT//2,dtype=np.float32))
        for y,x in centers:
            region=np.s_[y-24:y+24,x-24:x+24];row=dict(x=x,y=y,accepted=False)
            records.append(row)
            if mask[region].mean()<.95:row['reject_reason']='central_mask_support';continue
            counts['central_mask']+=1;co=float(coherence[region].mean());row['coherence']=co
            if co<.65:row['reject_reason']='local_coherence';continue
            axis=axial_summary(normal[region]);theta=axis['orientation']
            row['local_axial_resultant']=axis['resultant']
            if theta is None:row['reject_reason']='local_axis_numerically_unobserved';continue
            counts['orientation']+=1;row['normal_orientation_degrees']=float(np.degrees(theta))
            mx=(x+u*np.cos(theta)-v*np.sin(theta)).astype(np.float32)
            my=(y+u*np.sin(theta)+v*np.cos(theta)).astype(np.float32)
            coverage=float(cv2.remap(allowed,mx,my,cv2.INTER_NEAREST,borderMode=cv2.BORDER_CONSTANT).mean())
            row['actual_profile_mask_coverage']=coverage
            if coverage<.95:row['reject_reason']='actual_profile_mask_support';continue
            counts['profile_mask']+=1
            profile=cv2.remap(frame,mx,my,cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT).mean(0)
            axis_x=np.arange(PROFILE_LENGTH);profile-=np.polyval(np.polyfit(axis_x,profile,1),axis_x)
            contrast=float(profile.std());row['profile_contrast']=contrast
            if contrast<2:row['reject_reason']='profile_contrast';continue
            counts['contrast']+=1
            ac=np.array([np.dot(profile[:-lag],profile[lag:])/max(float(np.linalg.norm(profile[:-lag])*np.linalg.norm(profile[lag:])),1e-9)
                         for lag in range(1,math.ceil(MAX_PERIOD)+2)])
            peaks,_=find_peaks(ac,prominence=.15)
            peaks=[k for k in peaks if 2<=k+1<=MAX_PERIOD and ac[k]>=.6]
            if not peaks:row['reject_reason']='ACF_periodicity';continue
            counts['ACF']+=1;k=peaks[0];den=ac[k-1]-2*ac[k]+ac[k+1]
            ap=float(k+1+(.5*(ac[k-1]-ac[k+1])/den if abs(den)>1e-9 else 0))
            spectrum=np.abs(np.fft.rfft(profile*np.hanning(PROFILE_LENGTH)))**2
            frequency=np.fft.rfftfreq(PROFILE_LENGTH);valid=(frequency>=1/50)&(frequency<=1/2)
            indices=np.flatnonzero(valid);j=int(indices[np.argmax(spectrum[valid])])
            energy=float(spectrum[max(1,j-1):j+2].sum()/max(1e-9,spectrum[valid].sum()))
            log=np.log(spectrum+1e-12);den=log[j-1]-2*log[j]+log[j+1] if j+1<len(log) else 0
            delta=.5*(log[j-1]-log[j+1])/den if abs(den)>1e-9 else 0
            fp=float(PROFILE_LENGTH/(j+delta));difference=abs(ap-fp)/((ap+fp)/2)
            accepted=bool(2<=ap<=MAX_PERIOD and 2<=fp<=MAX_PERIOD and energy>=.5 and difference<=MAX_RELATIVE_DIFFERENCE)
            row.update(autocorrelation=ap,FFT=fp,correlation=float(ac[k]),spectral_energy_fraction=energy,
                relative_cue_difference=difference,accepted=accepted,
                reject_reason=None if accepted else 'cue_energy_range_or_agreement')
            if accepted:
                counts['accepted']+=1
                px=np.rint(mx).astype(int);py=np.rint(my).astype(int)
                inside=(px>=0)&(px<gray.shape[1])&(py>=0)&(py<gray.shape[0])
                support[py[inside],px[inside]]=True
    support&=mask
    accepted=[r for r in records if r['accepted']]
    ap=float(np.median([r['autocorrelation'] for r in accepted])) if accepted else None
    fp=float(np.median([r['FFT'] for r in accepted])) if accepted else None
    pitches=np.array([(r['autocorrelation']+r['FFT'])/2 for r in accepted])
    spread=float((np.percentile(pitches,75)-np.percentile(pitches,25))/np.median(pitches)) if len(pitches) else None
    enough=len(accepted)>=MIN_PATCHES
    agreement=bool(enough and abs(ap-fp)/((ap+fp)/2)<=MAX_RELATIVE_DIFFERENCE and spread<=MAX_RELATIVE_DIFFERENCE)
    status='observed_local_periodicity' if agreement else 'local_periodicity_unstable' if enough else 'insufficient_local_patches' if accepted else 'not_testable_geometry' if not centers else 'no_accepted_local_periodicity'
    if before!=[pixel_sha(gray),pixel_sha(mask)]:raise RuntimeError('local_periodicity_inputs_changed')
    return dict(schema_version=VERSION,status=status,stage_counts=counts,patches=records,
        accepted_patch_count=len(accepted),relative_IQR=spread,
        periodic_spacing_native_pixels=(ap+fp)/2 if agreement else None,
        support_mask=support,support_mask_pixel_sha256=pixel_sha(support),
        image_pixel_sha256=before[0],mask_pixel_sha256=before[1],
        coordinate_system='native_observed_crop_pixels',profile_length=PROFILE_LENGTH,
        tangential_height=TANGENTIAL_HEIGHT,stride=STRIDE,margin=MARGIN,
        maximum_period_two_complete_cycles=MAX_PERIOD,
        global_orientation_assumed=False,patches_overlap=True,independent_biometric_evidence=False,
        anatomy_classification='unknown',renderer_binding_allowed=False,protection_applied=False)
