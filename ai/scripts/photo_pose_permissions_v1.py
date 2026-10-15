"""Unapproved observed-pose search permissions; never anatomical ground truth.

Closed IP/DIP-to-TIP segments partition the observed semantic BODY. Distal
half-planes propose pixels, and only the 4-connected component containing
that digit's observed TIP is bound. Unbound pixels remain explicit diagnostics.
A connected wrong-neighbor bridge survives this topology rule.
"""
import hashlib
import numpy as np
from scipy import ndimage
from photo_resize_safety_v1 import validate_resize

VERSION='observed_pose_tip_connected_permissions_v1_experimental'
DIGITS=('thumb','index','middle','ring','little')
PAIRS=((4,3),(8,7),(12,11),(16,15),(20,19))
_CONNECTIVITY4=np.array([[0,1,0],[1,1,1],[0,1,0]],np.uint8)


def _shape(shape):
    if (not isinstance(shape,(tuple,list)) or len(shape)!=2 or
            any(isinstance(v,(bool,np.bool_)) or not isinstance(v,(int,np.integer)) or v<1 for v in shape)):
        raise ValueError('pose_native_shape_contract')
    height,width=map(int,shape)
    _,audit=validate_resize(height,width,1.,channels=1,itemsize=1)
    return height,width,audit


def _points(value):
    try:raw=np.asarray(value)
    except (ValueError,TypeError):raise ValueError('pose_finite_numeric_21_xy_required') from None
    if raw.shape!=(21,2) or raw.dtype.kind not in 'iuf':
        raise ValueError('pose_finite_numeric_21_xy_required')
    with np.errstate(over='ignore',invalid='ignore'):
        points=np.array(raw,np.float64,copy=True)
    if not np.isfinite(points).all():raise ValueError('pose_finite_numeric_21_xy_required')
    return points


def normalized_landmarks_to_native(normalized_xy,native_shape,exif_orientation=1):
    """Map normalized upright edge coordinates to native pixel-center indices.

Center index (x,y) normalizes as ((x+.5)/width,(y+.5)/height).
Finite out-of-frame points are retained, never clamped: cropped-hand wrist
predictions can be outside the frame. pose_permissions separately requires
all ten used IP/DIP/TIP axis endpoints to lie inside native center bounds.
"""
    height,width,_=_shape(native_shape)
    if (isinstance(exif_orientation,(bool,np.bool_)) or
            not isinstance(exif_orientation,(int,np.integer)) or not 1<=exif_orientation<=8):
        raise ValueError('pose_EXIF_orientation_contract')
    points=_points(normalized_xy)
    uh,uw=(width,height) if exif_orientation>=5 else (height,width)
    with np.errstate(over='ignore',invalid='ignore'):
        upright=points*np.array([uw,uh],np.float64)-.5
    if not np.isfinite(upright).all():raise ValueError('pose_finite_numeric_21_xy_required')
    u,v=upright[:,0],upright[:,1]
    if exif_orientation==1:native=np.stack([u,v],axis=1)
    elif exif_orientation==2:native=np.stack([width-1-u,v],axis=1)
    elif exif_orientation==3:native=np.stack([width-1-u,height-1-v],axis=1)
    elif exif_orientation==4:native=np.stack([u,height-1-v],axis=1)
    elif exif_orientation==5:native=np.stack([v,u],axis=1)
    elif exif_orientation==6:native=np.stack([v,height-1-u],axis=1)
    elif exif_orientation==7:native=np.stack([width-1-v,height-1-u],axis=1)
    else:native=np.stack([width-1-v,u],axis=1)
    if not np.isfinite(native).all():raise ValueError('pose_finite_numeric_21_xy_required')
    return native


def _body_contract(body):
    if not isinstance(body,np.ndarray) or body.dtype!=np.bool_ or body.ndim!=2:
        raise ValueError('pose_native_boolean_BODY_contract')
    _,_,audit=_shape(body.shape) # Guard before any raster scan/allocation.
    if not body.any():raise ValueError('pose_nonempty_BODY_required')
    return audit


def tip_connected_component(permission,tip_xy):
    """Bind the exact TIP component, never the largest or nearest component."""
    _body_contract(permission)
    try:p=np.asarray(tip_xy)
    except (TypeError,ValueError):raise ValueError('pose_native_tip_contract') from None
    if p.shape!=(2,) or p.dtype.kind not in 'iuf':raise ValueError('pose_native_tip_contract')
    with np.errstate(over='ignore',invalid='ignore'):p=np.array(p,np.float64,copy=True)
    height,width=permission.shape
    if not np.isfinite(p).all():raise ValueError('pose_native_tip_contract')
    if not 0<=p[0]<=width-1 or not 0<=p[1]<=height-1:raise ValueError('pose_native_tip_out_of_frame')
    x,y=np.floor(p+.5).astype(np.int64)
    if not permission[y,x]:raise ValueError('pose_tip_not_inside_permission')
    labels,count=ndimage.label(permission,structure=_CONNECTIVITY4)
    selected=int(labels[y,x]);bound=labels==selected;rejected=permission&~bound
    return bound,rejected,dict(connectivity=4,connected_components=int(count),tip_component_label=selected,
        accepted_pixels=int(bound.sum()),rejected_unbound_pixels=int(rejected.sum()),
        association='exact native pixel containing observed TIP; no distance or area threshold')


def pose_permissions(body,native_xy):
    """Return fixed digit labels, axes and explicit unbound diagnostics.

Returned owners exactly partition BODY. proposed_labels contain each owner's
IP/DIP distal half-plane; permission_labels and rejected_labels partition
those proposals. No input arrays are modified or geometry pixels added.
Caller must bind source/model/landmark identity before any downstream use.
"""
    audit=_body_contract(body);points=_points(native_xy);height,width=body.shape
    axes=[];segments=[]
    for label,((tip_id,dip_id),digit) in enumerate(zip(PAIRS,DIGITS),1):
        tip=points[tip_id];dip=points[dip_id]
        if any(not (0<=p[0]<=width-1 and 0<=p[1]<=height-1) for p in (tip,dip)):
            raise ValueError('pose_axis_endpoint_out_of_frame')
        delta=tip-dip;squared=float(delta@delta)
        if not np.isfinite(squared) or squared<=0:raise ValueError('pose_positive_finite_axis_required')
        midpoint=(tip+dip)/2;members=[]
        for name,point in [('midpoint',midpoint),('tip',tip)]:
            x,y=np.floor(point+.5).astype(np.int64)
            if not body[y,x]:raise ValueError('pose_axis_'+name+'_outside_BODY')
            members.append(dict(point=name,native_xy=point.tolist(),nearest_native_pixel_xy=[int(x),int(y)],body=True))
        axis=delta/np.sqrt(squared)
        axes.append(dict(label=label,digit=digit,tip_id=tip_id,DIP_or_IP_id=dip_id,
            tip_native_xy=tip.tolist(),DIP_or_IP_native_xy=dip.tolist(),axis_native_xy=axis.tolist(),
            axis_native_yx=axis[::-1].tolist(),length_native_pixels=float(np.sqrt(squared)),
            endpoint_and_midpoint_checks=members,anatomical_axis_ground_truth=False))
        segments.append((dip,delta,squared))
    owners=np.zeros(body.shape,np.uint8);proposed=np.zeros_like(owners)
    # This chunk size bounds temporary memory only; changing it does not
    # alter the per-pixel distance calculation or authorization rule.
    for y0 in range(0,height,128):
        y1=min(height,y0+128);ys,xs=np.nonzero(body[y0:y1]);ys=ys+y0
        native=np.stack([xs,ys],axis=1).astype(np.float64)
        best=np.full(len(native),np.inf);winner=np.zeros(len(native),np.uint8)
        for i,(dip,delta,squared) in enumerate(segments):
            t=np.clip(((native-dip)@delta)/squared,0.,1.)
            residual=native-(dip+t[:,None]*delta)
            distance=np.einsum('ij,ij->i',residual,residual)
            update=distance<best # Exact ties retain lower fixed digit label.
            best[update]=distance[update];winner[update]=i+1
        owners[ys,xs]=winner
        for i,(dip,delta,squared) in enumerate(segments):
            allowed=(winner==i+1)&(((native-dip)@delta)>=0.)
            proposed[ys[allowed],xs[allowed]]=i+1
    permission=np.zeros_like(owners);rejected=np.zeros_like(owners)
    for i,((tip,dip),row) in enumerate(zip(PAIRS,axes),1):
        bound,unbound,details=tip_connected_component(proposed==i,points[tip])
        permission[bound]=i;rejected[unbound]=i
        row.update(details,owner_pixels=int((owners==i).sum()),proposed_pixels=int((proposed==i).sum()))
    if (not np.array_equal(owners>0,body) or np.any((proposed>0)&(proposed!=owners)) or
            np.any((permission>0)&(rejected>0)) or
            not np.array_equal((permission>0)|(rejected>0),proposed>0)):
        raise ValueError('pose_partition_or_subset_contract')
    metadata=dict(version=VERSION,coordinate_system='encoded_original_native_integer_pixel_center_indices',
        owner_policy='nearest_closed_finite_IP_DIP_to_TIP_segments_in_native_pixels; exact ties lower digit label',
        proposal_policy='owner & observed_BODY & dot(pixel-IP_or_DIP,TIP-IP_or_DIP)>=0',
        permission_policy='observed_TIP_containing_4_connected_proposal_component',
        memory_audit=audit,source_identity_binding_required=True,
        body_pixel_sha256=hashlib.sha256(body.tobytes(order='C')).hexdigest(),
        landmark_native_xy_sha256=hashlib.sha256(points.astype('<f8').tobytes(order='C')).hexdigest(),
        BODY_uncertainty_retained=True,landmark_uncertainty_retained=True,connected_neighbor_spill_possible=True,
        physical_DPI_known=False,GT_used=False,numeric_distance_or_area_thresholds=False,
        anatomical_wholepad_verified=False,approved_for_protection=False,default_pipeline_enabled=False)
    return dict(owner_labels=owners,proposed_labels=proposed,permission_labels=permission,
        rejected_labels=rejected,axes=axes,metadata=metadata)
