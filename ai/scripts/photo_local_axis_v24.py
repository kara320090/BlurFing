"""Versioned recovery of unanchored distal candidates, without whole-hand PCA.

The remainder of the same owner supplies only a proximal direction. The pad
supplies its local axes and width. An observed crease is required before any
replacement of a failed proposal. Legacy geometry and thresholds stay fixed.
"""
import numpy as np
from photo_rounded_pad_v1 import _ray
from photo_crease_pad_v1 import observe_crease, silhouette
from finger_body_distal_estimator import PAD_WIDTH_MULTIPLIER


def local_geometry(owner, pad):
    if (owner.dtype != np.bool_ or pad.dtype != np.bool_ or owner.ndim != 2
            or owner.shape != pad.shape or np.any(pad & ~owner)):
        raise ValueError('local_axis_mask_contract')
    yy,xx=np.where(pad);py,px=np.where(owner & ~pad)
    if len(xx)<3 or len(px)<3:
        raise ValueError('local_axis_proximal_support_missing')
    pts=np.stack([xx,yy],axis=1)
    proximal=np.array([px.mean(),py.mean()])-pts.mean(0)
    norm=np.linalg.norm(proximal)
    if not np.isfinite(norm) or norm<1:
        raise ValueError('local_axis_direction_ambiguous')
    proximal/=norm
    values,vectors=np.linalg.eigh(np.cov(pts.T))
    alignment=np.abs(vectors.T@proximal)
    if min(values)<=0 or abs(values[1]-values[0])<=np.finfo(float).eps*max(values)*16:
        raise ValueError('local_axis_isotropic_pad')
    if abs(alignment[0]-alignment[1])<1e-6:
        raise ValueError('local_axis_direction_ambiguous')
    axis=vectors[:,np.argmax(alignment)]
    if axis@proximal<0: axis=-axis
    t=pts@axis;normal=np.array([-axis[1],axis[0]]);u=pts@normal
    width=float(np.ptp(u));top=float(t.min())
    if not np.isfinite(width) or width<2:
        raise ValueError('local_axis_width_unavailable')
    selected=(t>=top+.25*width)&(t<=top+.75*width)
    if not selected.any():
        raise ValueError('local_axis_section_unavailable')
    mid=float(np.median(u[selected]))
    depth=min(PAD_WIDTH_MULTIPLIER*width,float(np.ptp(t)))
    joint=axis*(top+depth)+normal*mid
    tip=axis*(top+.25*width)+normal*mid
    delta=tip-joint;length=float(np.linalg.norm(delta))
    if length<1:
        raise ValueError('local_axis_extent_unavailable')
    axis=delta/length;normal=np.array([-axis[1],axis[0]])
    sections=[(_ray(owner,joint+q*delta,-normal),_ray(owner,joint+q*delta,normal)) for q in (.25,.5,.75)]
    left,right=np.median(sections,axis=0)
    offset=float((right-left)/2)
    extension=_ray(owner,tip+normal*offset,axis)
    return dict(joint_xy=joint.tolist(),tip_xy=tip.tolist(),axis_xy=axis.tolist(),
                reference_width=float(left+right),distal_extent=length+extension,
                axis_source='local_pad_PCA_with_same_owner_proximal_centroid',
                local_width=width,whole_hand_major_axis_used=False)


def recover(rgb, baseline, refined, contexts, failed_ids):
    result=baseline.copy();boundary=refined.copy();rows=[]
    for context in contexts:
        identity=context['candidate_id']
        if identity not in failed_ids:
            continue
        owner=context['body'];pad=context['pad']
        row=dict(candidate_id=identity,recovered=False)
        try:
            if pad is None or not np.any(owner & baseline):
                raise ValueError('local_axis_candidate_missing')
            geometry=local_geometry(owner,pad)
            observation=observe_crease(rgb,owner,geometry)
            row.update(geometry=geometry,crease_observation=observation)
            if observation['status']!='observed':
                raise ValueError('local_axis_crease_unobserved')
            cap,detail=silhouette(owner,geometry,observation)
            if not np.any(cap & baseline):
                raise ValueError('local_axis_proposal_disjoint')
        except ValueError as error:
            row['reason']=str(error)
        else:
            result[owner]=cap[owner];boundary[owner]=cap[owner]
            row.update(recovered=True,geometry=geometry|detail,pixels=int(cap.sum()),reason=None)
        rows.append(row)
    return result,boundary,dict(version='local_axis_observed_crease_v24',regions=rows,
        independent_validation=False,anatomical_boundary_verified=False)
