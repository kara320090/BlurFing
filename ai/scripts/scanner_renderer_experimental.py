"""Independent scanner-style grayscale renderer; frozen photo renderer untouched."""
import cv2
import numpy as np
from ridge_structure_field import field_snapshots


def render_scanner(rgb,roi,strength=.5):
    if not np.isfinite(strength) or not 0<=strength<=1:raise ValueError('strength must be in [0,1]')
    roi.validate(rgb,roi.source_sha256)
    if roi.source_type!='FINGERPRINT_IMAGE':raise ValueError('scanner renderer only')
    if strength==0:return rgb.copy(),dict(applied=False,reason='strength_zero',exterior_preserved=True)
    mask=roi.binary_mask>0;h,w=mask.shape;scale=512/max(h,w);small=cv2.resize(mask.astype(np.uint8),(round(w*scale),round(h*scale)),interpolation=cv2.INTER_NEAREST)>0;canvas=np.zeros((512,512),bool);x=(512-small.shape[1])//2;y=(512-small.shape[0])//2;canvas[y:y+small.shape[0],x:x+small.shape[1]]=small;pitch=roi.pitch*scale
    if not 2<=pitch<=50: return rgb.copy(),dict(applied=False,reason='scanner_canonical_pitch_outside_range',exterior_preserved=True)
    seed=int(roi.source_sha256[:8],16);field,recipe=field_snapshots(canvas,pitch,seed,(2,))[2];field=field[y:y+small.shape[0],x:x+small.shape[1]];field=cv2.resize(field,(w,h),interpolation=cv2.INTER_CUBIC)
    gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY).astype(float);low,high=np.percentile(gray[mask],[10,90]);synthetic=(low+high)/2+(high-low)/2*np.tanh(field);distance=cv2.distanceTransform(mask.astype(np.uint8),cv2.DIST_L2,5);t=np.clip(distance/(2*roi.pitch),0,1);weight=t*t*(3-2*t)*strength
    rendered=np.clip(np.rint(gray*(1-weight)+synthetic*weight),0,255).astype(np.uint8);out=rgb.copy();out[mask]=np.repeat(rendered[:,:,None],3,axis=2)[mask];assert np.array_equal(out[~mask],rgb[~mask])
    return out,dict(applied=bool((out!=rgb).any()),renderer='experimental_scanner_independent_field_v1',exterior_preserved=True,changed_pixels=int(np.any(out!=rgb,axis=2).sum()),recipe=recipe,requires_structure_check=True,privacy_verified=False)
