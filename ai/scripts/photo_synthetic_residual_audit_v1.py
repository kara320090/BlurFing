"""Development copy-residual diagnostic; not recognition or coverage proof.

Same-position normalized high-pass correlation can flag accidentally retained
source texture. Negative tests cannot establish unlinkability, detect a missed
finger, or rule out shifted/rotated original texture. There is no pass verdict.
"""
import cv2
import numpy as np
from scipy import ndimage


def inspect_region(original, returned, mask):
    if (not isinstance(original, np.ndarray) or original.dtype != np.uint8 or original.ndim != 3 or
            original.shape[2] != 3 or not isinstance(returned, np.ndarray) or
            returned.dtype != np.uint8 or returned.shape != original.shape or
            not isinstance(mask, np.ndarray) or mask.dtype != np.bool_ or mask.shape != original.shape[:2]):
        raise ValueError('residual_RGB_mask_contract')
    if mask.size > 32*1024*1024:
        raise ValueError('residual_raster_limit')
    yy, xx = np.nonzero(mask)
    if not len(yy):
        return dict(status='no_region', windows=[], privacy_validated=False)
    x0, y0, x1, y1 = int(xx.min()), int(yy.min()), int(xx.max())+1, int(yy.max())+1
    local = mask[y0:y1, x0:x1]
    width = min(local.shape)
    sigma = max(1., width/80.)
    inner = ndimage.distance_transform_edt(np.pad(local, 1))[1:-1, 1:-1] > max(3., sigma*3)
    weight = local.astype(np.float32)
    denom = cv2.GaussianBlur(weight, (0, 0), sigma, borderType=cv2.BORDER_REFLECT_101)
    fields = []
    for image in (original, returned):
        gray = cv2.cvtColor(image[y0:y1, x0:x1], cv2.COLOR_RGB2GRAY).astype(np.float32)
        broad = cv2.GaussianBlur(gray*weight, (0, 0), sigma, borderType=cv2.BORDER_REFLECT_101)
        fields.append(gray-broad/np.maximum(denom, 1e-6))
    step = int(np.clip(width/4, 32, 128)); rows = []
    for y in range(0, local.shape[0], step):
        for x in range(0, local.shape[1], step):
            take = inner[y:y+step, x:x+step]
            if take.sum() < max(64, step*step//2):
                continue
            a, b = [f[y:y+step, x:x+step][take].astype(float) for f in fields]
            a -= a.mean(); b -= b.mean()
            sa, sb = float(a.std()), float(b.std())
            usable = sa >= 1. and sb >= .25
            correlation = float(np.mean(a*b)/(sa*sb)) if usable else None
            rows.append(dict(bbox=[x+x0, y+y0, min(x+step, local.shape[1])+x0,
                min(y+step, local.shape[0])+y0], pixels=int(take.sum()),
                source_std=sa, result_std=sb, correlation=correlation,
                copy_review_flag=bool(usable and abs(correlation) >= .65)))
    values = [abs(r['correlation']) for r in rows if r['correlation'] is not None]
    return dict(status='diagnostic_only', windows=rows, usable_windows=len(values),
        insufficient_detail_windows=len(rows)-len(values), review_flags=sum(r['copy_review_flag'] for r in rows),
        max_abs_correlation=max(values) if values else None, highpass_sigma_native=sigma,
        review_correlation_threshold=.65, threshold_is_uncalibrated_development_heuristic=True,
        coverage_verified=False, privacy_validated=False,
        interpretation='Flags request inspection; no flags do not establish protection.')
