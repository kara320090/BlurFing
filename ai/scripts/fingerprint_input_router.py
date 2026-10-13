"""Content-based experimental routing. Never routes using filenames."""
import cv2
import numpy as np
from ridge_evidence_frontend import scanner_ridge_evidence


def route_input(rgb):
    if rgb.dtype!=np.uint8 or rgb.ndim!=3 or rgb.shape[2]!=3:raise ValueError('RGB uint8 required')
    thumb=cv2.resize(rgb,(min(512,rgb.shape[1]),min(512,rgb.shape[0])),interpolation=cv2.INTER_AREA);chroma=thumb.max(axis=2).astype(float)-thumb.min(axis=2).astype(float);color_fraction=float((chroma>8).mean())
    if color_fraction>.05:return dict(input_type='PHOTO',reason='color_photo_content',color_fraction=color_fraction)
    gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY);mask,q=scanner_ridge_evidence(gray);background_fraction=float((gray>235).mean());border=np.r_[gray[0],gray[-1],gray[:,0],gray[:,-1]].astype(float);border_mad=float(np.median(np.abs(border-np.median(border))))
    if q['credible_windows']>=8 and q['credible_fraction']>=.10 and (background_fraction>=.10 or border_mad<=12 or mask.mean()>.5):return dict(input_type='FINGERPRINT_IMAGE',reason='achromatic_periodic_ridges_simple_background',color_fraction=color_fraction,background_fraction=background_fraction,border_mad=border_mad,foreground_occupancy=float(mask.mean()),ridge_quality=q)
    return dict(input_type='UNKNOWN',reason='input_type_ambiguous_or_no_ridges',color_fraction=color_fraction,background_fraction=background_fraction,border_mad=border_mad,foreground_occupancy=float(mask.mean()),ridge_quality=q)
