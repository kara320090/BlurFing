"""V12 local direction after constant lighting-gradient removal; diagnostic only.

Keep raw extrema unchanged. Subtract the median gradient only for the direction
statistic, since a broad lighting slope is not the ridge normal. This is not
threshold tuning or permission to infer invisible fingerprints.
"""
import cv2
import numpy as np
from photo_visibility_peak_train_probe_v4 import CONFIG
from photo_visibility_peak_train_probe_v5 import _probe_level
from photo_visibility_joint_witness_v11 import proposals, raw_strips, joint_train


def local_direction(patch, theta, span):
    n=patch.shape[0];y,x=np.indices(patch.shape,dtype=float)
    x-=(n-1)/2;y-=(n-1)/2
    u=x*np.cos(theta)+y*np.sin(theta)+(n-9)/2
    v=-x*np.sin(theta)+y*np.cos(theta)
    selected=(u>=span[0])&(u<=span[1])&(np.abs(v)<=3.)
    smooth=cv2.GaussianBlur(patch.astype(np.float64),(0,0),.5,borderType=cv2.BORDER_REFLECT_101)
    gy,gx=np.gradient(smooth)
    dx=gx[selected];dy=gy[selected]
    if not len(dx):
        return dict(local_direction_alignment=0.,direction_support_pixels=0,removed_gradient_xy=[0.,0.])
    bx=float(np.median(dx));by=float(np.median(dy));dx=dx-bx;dy=dy-by
    normal=dx*np.cos(theta)+dy*np.sin(theta);tangent=-dx*np.sin(theta)+dy*np.cos(theta)
    en=float(normal@normal);et=float(tangent@tangent)
    return dict(local_direction_alignment=(en-et)/max(en+et,1e-12),direction_support_pixels=int(selected.sum()),
                removed_gradient_xy=[bx,by])


def inspect_patch(patch,geometry):
    reason='spectral_proposal'
    for period,theta,axial in proposals(patch,geometry):
        reason='joint_raw_train';result=joint_train(*raw_strips(patch,theta),period)
        if result is None:continue
        direction=local_direction(patch,theta,result['common_run_span'])
        if direction['local_direction_alignment']<CONFIG.min_ring_axial:
            reason='light_compensated_local_direction';continue
        return dict(**result,**direction,normal_angle_radians=theta,ring_axial=axial,ring_axial_used_as_gate=False),'accepted'
    return None,reason


def probe_level(gray,support,max_side):
    result=_probe_level(gray,support,max_side,inspect_patch,'photo_visibility_light_direction_v13')
    result['config'].update(raw_train_selection='matched_consecutive_raw_crests',correlation_scope='shared_train',
                            ring_axial_used_as_gate=False,direction_statistic='median_centered_local_gradient_alignment',
                            raw_extrema_lighting_compensated=False)
    return result
