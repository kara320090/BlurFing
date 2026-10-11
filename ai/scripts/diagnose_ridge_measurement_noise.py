import cv2

import numpy as np

from contactless_ridge_pitch import estimate_ridge_pitch

def credible_estimate(estimate):
    values=np.array([m['pitch']for m in estimate.get('measurements',[])if m['correlation']>=.6 and m['coherence']>=.65 and m['profile_contrast']>=2])
    if len(values)<3:return dict(status='insufficient',pitch=None,credible_patches=len(values))
    median=float(np.median(values));iqr=float((np.quantile(values,.75)-np.quantile(values,.25))/median)
    if not 4<=median<=24 or iqr>.15:return dict(status='inconsistent',pitch=None,credible_patches=len(values),relative_iqr=iqr)
    return dict(status='credible_partial',pitch=median,credible_patches=len(values),relative_iqr=iqr)

def two_scale_measurement(raw,mask):
    estimates=[]
    for sigma in [1.2,1.8]:
        estimate=estimate_ridge_pitch(cv2.GaussianBlur(raw,(0,0),sigma),mask)
        estimates.append(dict(sigma=sigma,estimate=estimate,selection=credible_estimate(estimate)))
    pitches=[e['selection']['pitch']for e in estimates]
    if any(p is None for p in pitches):return dict(status='unavailable',pitch=None,scales=estimates,physical_dpi_known=False)
    difference=float(abs(pitches[0]-pitches[1])/np.mean(pitches))
    if difference>.10:return dict(status='scale_disagreement',pitch=None,relative_difference=difference,scales=estimates,physical_dpi_known=False)
    return dict(status='observed_partial_two_scale',pitch=float(np.mean(pitches)),relative_difference=difference,
        scales=estimates,physical_dpi_known=False,real_pitch_ground_truth=False)
