import numpy as np

def select_observed_pitch(estimate):
    if estimate['status']=='estimated':
        return dict(status='observed',pitch=float(estimate['pitch']),source='existing_estimator',physical_dpi_known=False)
    credible=[m['pitch']for m in estimate.get('measurements',[])if m['correlation']>=.6 and m['coherence']>=.65 and m['profile_contrast']>=2]
    if len(credible)>=3:
        a=np.array(credible);median=float(np.median(a));spread=float((np.quantile(a,.75)-np.quantile(a,.25))/median)
        if 4<=median<=24 and spread<=.15:
            return dict(status='observed_partial',pitch=median,source='at least3 coherent periodic patches',
                        count=len(credible),relative_iqr=spread,physical_dpi_known=False,
                        original_estimator_status=estimate['status'],full_roi_pitch_verified=False)
    return dict(status='unavailable',pitch=None,credible_patch_count=len(credible),physical_dpi_known=False)
