"""GT-free native body cross-section scale, independent of pad fragment width.

Pixel cells are traversed exactly along the observed axis normal. A source
frame edge cannot supply the missing body boundary. This is an unapproved
semantic geometry observation, not physical DPI or anatomical ground truth.
"""
import cv2
import numpy as np
from photo_resize_safety_v1 import validate_resize,ResizeSafetyError
from photo_region_scale_plan_v1 import NORMALIZED_WIDTH

VERSION='native_body_cross_section_scale_v1_experimental'


def _exit(body,point,direction):
    cell=np.asarray(point,int).copy();origin=np.asarray(point,np.float64);height,width=body.shape
    for _ in range(height+width+2):
        times=np.array([(cell[k]+(.5 if direction[k]>0 else -.5)-origin[k])/direction[k]
                        if direction[k]!=0 else np.inf for k in range(2)])
        distance=float(times.min());crossed=np.abs(times-distance)<=1e-9
        cell[crossed]+=np.sign(direction[crossed]).astype(int)
        if np.any(cell<0) or cell[0]>=height or cell[1]>=width:return distance,True
        if not body[tuple(cell)]:return distance,False
    raise ValueError('native_body_ray_step_bound_exceeded')


def observe_width(pad,body,axis_yx,*,anchor_yx=None):
    if (not isinstance(pad,np.ndarray) or not isinstance(body,np.ndarray) or pad.dtype!=np.bool_ or
            body.dtype!=np.bool_ or pad.ndim!=2 or pad.shape!=body.shape or min(pad.shape)<1 or
            not pad.any() or np.any(pad & ~body)):
        raise ValueError('native_pad_body_contract')
    validate_resize(*pad.shape,1.)
    try:axis=np.asarray(axis_yx,np.float64)
    except (ValueError,TypeError):raise ValueError('native_body_axis_contract') from None
    if axis.shape!=(2,) or not np.isfinite(axis).all():raise ValueError('native_body_axis_contract')
    with np.errstate(over='ignore'):magnitude=float(np.linalg.norm(axis))
    if not np.isfinite(magnitude) or not magnitude>0:
        raise ValueError('native_body_axis_contract')
    axis=axis/magnitude;normal=np.array([-axis[1],axis[0]])
    y,x=np.where(pad);y0,x0,y1,x1=int(y.min()),int(x.min()),int(y.max())+1,int(x.max())+1
    distance=cv2.distanceTransform(np.pad(pad[y0:y1,x0:x1].astype(np.uint8),1),cv2.DIST_L2,5)[1:-1,1:-1]
    ay,ax=np.unravel_index(np.argmax(distance),distance.shape);anchor=[int(ay+y0),int(ax+x0)]
    if anchor_yx is not None:
        if (not isinstance(anchor_yx,(list,tuple)) or len(anchor_yx)!=2 or
                any(type(v) is not int for v in anchor_yx) or
                not 0<=anchor_yx[0]<pad.shape[0] or not 0<=anchor_yx[1]<pad.shape[1] or not pad[tuple(anchor_yx)]):
            raise ValueError('native_body_anchor_contract')
        anchor=list(anchor_yx)
    positive,pc=_exit(body,anchor,normal);negative,nc=_exit(body,anchor,-normal);width=positive+negative
    if not np.isfinite(width) or width<=0:raise ValueError('native_body_width_invalid')
    return dict(version=VERSION,anchor_native_yx=anchor,axis_native_yx=axis.tolist(),normal_native_yx=normal.tolist(),
                observed_native_body_width=width,positive_boundary_distance=positive,negative_boundary_distance=negative,
                boundary_unobserved=bool(pc or nc),coordinate_system='encoded_original_pixels',
                candidate_inscribed_diameter=2*float(distance.max()),
                width_semantics='contiguous associated semantic body interval at native pixel-cell boundaries',
                anchor_policy=('row-major first maximum-inscribed candidate pixel; no candidate filtering' if anchor_yx is None
                    else 'explicit predicted-pixel observation anchor shared with renderer seed'),physical_DPI_known=False)


def plan_scale(pad,body,axis_yx,component):
    observation=observe_width(pad,body,axis_yx);scale=NORMALIZED_WIDTH/observation['observed_native_body_width']
    plan=dict(component=component,mask_pixels=int(pad.sum()),working_scale=scale,normalization=observation,
              target_working_body_width=NORMALIZED_WIDTH,scale_policy=VERSION,component_filtering=False)
    if observation['boundary_unobserved']:
        return plan|dict(status='rejected',reject_reason='native_body_width_boundary_unobserved',working_shape=None)
    try:
        shape,audit=validate_resize(*pad.shape,scale)
        return plan|dict(status='planned',reject_reason=None,working_shape=list(shape),resize_audit=audit)
    except ResizeSafetyError as error:
        return plan|dict(status='rejected',reject_reason=error.reason,working_shape=None,resize_audit=error.audit)
