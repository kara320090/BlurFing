import cv2

import numpy as np

from skimage.morphology import skeletonize

def smooth_random(shape,grid,sigma,rng):
    field=cv2.resize(rng.standard_normal((grid,grid)).astype(np.float32),shape[::-1],interpolation=cv2.INTER_CUBIC)
    field=cv2.GaussianBlur(field,(0,0),sigma)
    field-=float(field.mean());field/=max(float(field.std()),1e-6)
    return np.clip(field,-2.5,2.5)

def render_photographic_profile(field,mask,pitch,seed):
    if field.shape!=(512,512) or mask.shape!=field.shape or not mask.any():raise ValueError('Nonempty 512 field/mask required')
    ridge=(field<0)&mask;valley=(field>=0)&mask
    center=skeletonize(ridge);other=skeletonize(valley)
    if not center.any() or not other.any():raise ValueError('Both synthetic centers required')
    dr=cv2.distanceTransform((~center).astype(np.uint8),cv2.DIST_L2,cv2.DIST_MASK_PRECISE)
    dv=cv2.distanceTransform((~other).astype(np.uint8),cv2.DIST_L2,cv2.DIST_MASK_PRECISE)
    ratio=np.clip(dr/np.maximum(dr+dv,1e-5),0,1)
    rng=np.random.default_rng(seed ^ 0x09A71C)
    grid=int(np.clip(round(512/max(pitch*3,12)),10,36))
    width=smooth_random(field.shape,grid,max(1.,pitch*.45),rng)
    width_shift=np.clip(width*.035,-.075,.075)
    ratio=np.clip(ratio+width_shift*4*ratio*(1-ratio),0,1)
    shoulder=smooth_random(field.shape,10,max(1.,pitch),rng)
    power=np.clip(1.05+shoulder*.13,.75,1.4)
    profile=np.cos(np.pi*np.power(ratio,power))
    profile=cv2.GaussianBlur(profile,(0,0),max(.5,pitch*.065))
    contrast=np.clip(1+smooth_random(field.shape,grid,max(1.,pitch*.65),rng)*.14,.65,1.25)
    profile*=contrast
    profile-=float(profile[mask].mean());profile/=max(float(profile[mask].std()),1e-6)
    return profile.astype(np.float32),dict(method='independent variable ridge widths, shoulders and local relief',
        local_width_shift_range=[float(width_shift.min()),float(width_shift.max())],
        shoulder_power_range=[float(power.min()),float(power.max())],
        local_contrast_range=[float(contrast.min()),float(contrast.max())],
        centers_count=int(center.sum()),valley_centers_count=int(other.sum()),
        original_phase_input=False,original_ridge_highpass_transferred=False,
        another_fingerprint_donor=False,human_naturalness_validated=False)
