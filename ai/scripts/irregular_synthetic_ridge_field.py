import cv2

import numpy as np

from ridge_structure_field import field_snapshots

def deform_synthetic_field(field,pitch,seed):
    if field.shape!=(512,512) or not np.isfinite(field).all():raise ValueError('Finite 512 field required')
    if not np.isfinite(pitch) or pitch<=0:raise ValueError('Positive observed pitch required')
    rng=np.random.default_rng(seed ^ 0xF109D)
    displacement=[]
    for _ in range(2):
        fine=cv2.resize(rng.standard_normal((13,13)).astype(np.float32),(512,512),interpolation=cv2.INTER_CUBIC)
        coarse=cv2.resize(rng.standard_normal((5,5)).astype(np.float32),(512,512),interpolation=cv2.INTER_CUBIC)
        d=cv2.GaussianBlur(fine,(0,0),7)*.7+cv2.GaussianBlur(coarse,(0,0),16)*.3
        d*=pitch*2/max(float(np.max(np.abs(d))),1e-6);displacement.append(d)
    dx,dy=displacement
    gx,gy=np.gradient(dx,axis=1),np.gradient(dx,axis=0);hx,hy=np.gradient(dy,axis=1),np.gradient(dy,axis=0)
    norm=np.sqrt(gx*gx+gy*gy+hx*hx+hy*hy);scale=min(1.,.18/max(float(norm.max()),1e-6));dx*=scale;dy*=scale
    gx,gy=np.gradient(dx,axis=1),np.gradient(dx,axis=0);hx,hy=np.gradient(dy,axis=1),np.gradient(dy,axis=0)
    jac=(1+gx)*(1+hy)-gy*hx
    assert float(jac.min())>.65
    yy,xx=np.mgrid[:512,:512].astype(np.float32)
    deformed=cv2.remap(field,xx+dx,yy+dy,cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT_101)
    return deformed,dict(method='two-scale nonperiodic elastic variation of synthetic field',
        max_displacement_pixels=float(max(np.max(np.abs(dx)),np.max(np.abs(dy)))),
        max_displacement_gradient=float(np.sqrt(gx*gx+gy*gy+hx*hx+hy*hy).max()),
        min_jacobian=float(jac.min()),max_jacobian=float(jac.max()),
        spacing_variation_gradient_limit=.18,original_ridge_field_used=False,periodic_modulation=False,
        source_fingerprint_warped=False,human_naturalness_validated=False)

def independent_irregular_field(mask,pitch,seed):
    field,recipe=field_snapshots(mask,pitch,seed,(2,))[2]
    field,deformation=deform_synthetic_field(field,pitch,seed)
    return field,recipe|dict(deformation=deformation)
