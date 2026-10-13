"""Scanner branch: no hand detector, SAM or MediaPipe. No input ridge copying."""
import cv2
import time
import numpy as np
from ridge_evidence_frontend import scanner_ridge_evidence
from canonical_fingerprint_roi import canonical_roi


def detect_scanner(rgb,sha):
    tick=time.perf_counter();gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY);support,q=scanner_ridge_evidence(gray);ridge_seconds=time.perf_counter()-tick;tick=time.perf_counter()
    if q['status']!='ridge_observed':return [],dict(status='rejected',reject_reason='ridge_evidence_insufficient',ridge_quality=q)
    n,labels,stats,_=cv2.connectedComponentsWithStats(support.astype(np.uint8),connectivity=4)
    if n<=1:return [],dict(status='rejected',reject_reason='empty_foreground')
    mask=labels==(1+int(np.argmax(stats[1:,cv2.CC_STAT_AREA])));mask=cv2.morphologyEx(mask.astype(np.uint8),cv2.MORPH_CLOSE,np.ones((9,9),np.uint8))>0
    # Fill enclosed holes while retaining connected ridge-evidence foreground.
    contours,_=cv2.findContours(mask.astype(np.uint8),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE);filled=np.zeros(mask.shape,np.uint8);cv2.drawContours(filled,contours,-1,1,cv2.FILLED);mask=filled>0
    if mask.mean()<.05 or (mask.mean()>.98 and q['credible_fraction']<.5):return [],dict(status='rejected',reject_reason='foreground_geometry_invalid')
    roi=canonical_roi(gray,mask,sha,'FINGERPRINT_IMAGE',q,'scanner_ridge_evidence');roi.validate(rgb,sha)
    return [roi],dict(status='detected_development_only',reject_reason=None,ridge_quality=q,timing=dict(ridge_validation=ridge_seconds,foreground_segmentation=time.perf_counter()-tick))
