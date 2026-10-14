"""Frame/context/appearance observations; never classifies or changes a pad."""
import hashlib
import cv2
import numpy as np
from scipy import ndimage
from scipy.ndimage import gaussian_filter1d
import photo_terminal_branch_candidates_v1 as geometry
import photo_terminal_branch_candidates_v2 as branch
from proximal_boundary_evidence import observe_proximal_boundary
from photo_resize_safety_v1 import validate_resize

VERSION='photo_terminal_context_diagnostic_v1'


def _pixel_sha(array):return hashlib.sha256(array.tobytes()).hexdigest()


def _frame(mask):
    counts={name:int(values.sum()) for name,values in zip(['top','bottom','left','right'],
                                                         [mask[0],mask[-1],mask[:,0],mask[:,-1]])}
    return dict(touches=any(counts.values()),pixels_per_side=counts,
                coordinate_system='encoded_source_pixels',anatomy_classification='unknown')


def _contexts(body,result):
    height,width=body.shape;shape=result['working_shape']
    small=cv2.resize(body.astype(np.uint8),(shape[1],shape[0]),interpolation=cv2.INTER_NEAREST)>0
    labels,_=ndimage.label(small)
    grouped={}
    for parent in result['regions']:
        if parent.get('mask') is not None:grouped.setdefault(parent['component'],[]).append(parent)
    for component_id,parents in grouped.items():
        component=labels==component_id
        distance=cv2.distanceTransform(np.pad(component.astype(np.uint8),1),cv2.DIST_L2,5)[1:-1,1:-1]
        skeleton,_=geometry.prune_junction_contained_spurs(geometry.skeletonize(component),distance)
        coords,graph=geometry.skeleton_graph(skeleton)
        paths=geometry.terminal_paths(coords,graph)
        nearest_all=ndimage.distance_transform_edt(~skeleton)
        for parent in parents:
            index=int(parent['candidate_id'].rsplit('-',1)[1])-1
            path=paths[index];points=path['points'];arc=path['arc']
            if points[0].tolist()!=parent['endpoint_working_yx']:
                raise ValueError('terminal_context_identity_mismatch')
            chosen=np.ones(len(points),bool)
            if path['ends_at_junction']:chosen[-1]=False
            else:chosen=arc<.5*arc[-1]
            selected=np.zeros(component.shape,bool);seeds=points[chosen]
            if not len(seeds):raise ValueError('terminal_context_seeds_unavailable')
            selected[seeds[:,0],seeds[:,1]]=True
            support=component&(ndimage.distance_transform_edt(~selected)==nearest_all)
            geometry.validate_candidate_context_allocation(height,width,len(result['regions'])+1)
            native=cv2.resize(support.astype(np.uint8),(width,height),interpolation=cv2.INTER_NEAREST)>0
            native&=body
            yield parent,native


def _axis_mapping(bbox,shape,axis_native_yx):
    """Encoded source pixel centers -> rounded resized ROI -> axial image."""
    x0,y0,x1,y1=bbox;source_h,source_w=y1-y0,x1-x0
    sy,sx=shape[0]/source_h,shape[1]/source_w
    axis=np.asarray(axis_native_yx)
    if (axis.shape!=(2,) or not np.issubdtype(axis.dtype,np.number) or np.iscomplexobj(axis) or
            not np.isfinite(axis).all() or not np.any(axis)):
        raise ValueError('terminal_axis_contract_mismatch')
    if np.max(np.abs(axis))>np.finfo(np.float64).max:
        raise ValueError('terminal_axis_contract_mismatch')
    axis=axis.astype(np.float64);axis/=np.max(np.abs(axis));axis*=[sy,sx]
    axis/=np.linalg.norm(axis)
    resize=np.array([[sx,0,sx*(.5-x0)-.5],[0,sy,sy*(.5-y0)-.5],[0,0,1.]],np.float64)
    # Columns are x/y; axial direction is stored in y/x.
    rotate=np.array([[axis[0],-axis[1],0],[axis[1],axis[0],0],[0,0,1.]],np.float64)
    return resize,rotate


def observe_context_boundary(rgb,support,axis_native_yx):
    if (not isinstance(rgb,np.ndarray) or rgb.dtype!=np.uint8 or rgb.ndim!=3 or rgb.shape[2]!=3 or
            not isinstance(support,np.ndarray) or support.dtype!=np.bool_ or support.shape!=rgb.shape[:2]):
        raise ValueError('terminal_boundary_context_contract_mismatch')
    validate_resize(*support.shape,1.)
    if not support.any():raise ValueError('terminal_boundary_context_contract_mismatch')
    y,x=np.where(support);bbox=[int(x.min()),int(y.min()),int(x.max())+1,int(y.max())+1]
    x0,y0,x1,y1=bbox;source_h,source_w=y1-y0,x1-x0
    ratio=min(1.,720/max(source_h,source_w))
    shape,audit=validate_resize(source_h,source_w,ratio)
    resized_rgb=cv2.resize(rgb[y0:y1,x0:x1],(shape[1],shape[0]),interpolation=cv2.INTER_AREA)
    resized_support=cv2.resize(support[y0:y1,x0:x1].astype(np.uint8),(shape[1],shape[0]),interpolation=cv2.INTER_NEAREST)>0
    resize,rotate=_axis_mapping(bbox,shape,axis_native_yx)
    if not resized_support.any():
        return dict(status='unobserved',reason='context_support_lost_at_resize',mapping=dict(
            source_bbox_xyxy=bbox,resized_ROI_shape=list(shape),
            actual_resize_yx=[shape[0]/source_h,shape[1]/source_w],resize_audit=audit,
            axial_mapping_available=False))
    ry,rx=np.where(resized_support)
    points=np.column_stack([rx,ry]);rotated=points@rotate[:2,:2].T
    lo=rotated.min(axis=0)-2.;hi=rotated.max(axis=0)
    rotate[:2,2]=-lo
    size=(int(np.ceil(hi[0]-lo[0]))+3,int(np.ceil(hi[1]-lo[1]))+3)
    _,warp_audit=validate_resize(size[1],size[0],1.)
    mask=cv2.warpAffine(resized_support.astype(np.uint8),rotate[:2],size,flags=cv2.INTER_NEAREST)>0
    gray=cv2.cvtColor(cv2.warpAffine(resized_rgb,rotate[:2],size,flags=cv2.INTER_LINEAR),cv2.COLOR_RGB2GRAY).astype(np.float32)
    widths=np.array([np.ptp(np.flatnonzero(row))+1 if row.any() else 0 for row in mask],float)
    valid=np.flatnonzero(widths)
    affine=rotate@resize;inverse=np.linalg.inv(affine)
    mapping=dict(source_bbox_xyxy=bbox,resized_ROI_shape=list(shape),axial_shape=list(mask.shape),
        actual_resize_yx=[shape[0]/source_h,shape[1]/source_w],
        encoded_source_to_axial_affine=affine.tolist(),axial_to_encoded_source_affine=inverse.tolist(),
        coordinate_rule='pixel centers (x+.5)*actual_resize-.5; no nominal-scale inverse',
        resize_audit=audit,warp_audit=warp_audit)
    if not len(valid):
        return dict(status='unobserved',reason='context_support_lost_at_warp',mapping=mapping)
    start,end=int(valid[0]),int(valid[-1]);length=end-start+1
    if start==end:
        return dict(status='unobserved',reason='context_axial_extent_unavailable',mapping=mapping)
    reference=widths[start+round(.15*length):start+round(.55*length)]
    reference=reference[reference>0]
    if not len(reference) or np.median(reference)<12:
        return dict(status='unobserved',reason='context_width_unavailable',mapping=mapping)
    width=float(np.median(reference))
    smooth=cv2.GaussianBlur(gray,(0,0),max(1.,.025*width))
    response=cv2.GaussianBlur(smooth,(1,0),sigmaX=0,sigmaY=max(2.,.18*width))-smooth
    crease,coverage=np.zeros(len(widths)),np.zeros(len(widths))
    for row in range(start,end+1):
        xx=np.flatnonzero(mask[row])
        if not len(xx):continue
        a,b=np.percentile(xx,[20,80]).astype(int);values=response[row,a:b+1]
        crease[row]=float(np.median(values));coverage[row]=float(np.mean(values>2))
    crease=gaussian_filter1d(crease,max(1.,.015*width))
    evidence=observe_proximal_boundary(gray,mask,widths,start,end,width,crease,coverage)
    selected=evidence['selected_row'];line=None
    if selected is not None:
        endpoints=np.array([[0,selected,1.],[size[0]-1,selected,1.]])@inverse.T
        line=endpoints[:,:2].tolist()
    return dict(status='observed' if evidence['observed'] else 'unobserved',reason=evidence['reject_reason'],
        mapping=mapping,analysis_width=width,selected_boundary_source_xy_endpoints=line,
        boundary_line_semantics='selected axial-row reference transect; not fitted crease line; endpoints may be outside support',
        evidence=evidence,boundary_semantics='existing crease/appearance cue agreement, not anatomical GT')


def diagnose(rgb,body,tip):
    if (not isinstance(rgb,np.ndarray) or rgb.dtype!=np.uint8 or rgb.ndim!=3 or rgb.shape[2]!=3 or
            not isinstance(body,np.ndarray) or body.dtype!=np.bool_ or body.shape!=rgb.shape[:2] or
            not isinstance(tip,np.ndarray) or tip.dtype!=np.bool_ or tip.shape!=body.shape):
        raise ValueError('terminal_diagnostic_RGB_shape_mismatch')
    validate_resize(*body.shape,1.)
    before=[_pixel_sha(a) for a in [rgb,body,tip]]
    result=branch.estimate(body,tip);original_pad_sha=_pixel_sha(result['mask']);rows=[]
    for parent,support in _contexts(body,result):
        actual=np.asarray(parent['actual_resize_yx'],float)
        inward=-np.asarray(parent['outward_direction_yx'],float)/actual
        inward/=np.linalg.norm(inward)
        row=dict(candidate_id=parent['candidate_id'],pad_frame=_frame(parent['mask']),
            context_frame=_frame(support),ray_frame_cut=parent['frame_cut'],
            context_pixels=int(support.sum()),pad_outside_context_pixels=int((parent['mask']&~support).sum()),
            context_semantics='inclusive nearest full terminal support; no-junction arc<midpoint; not anatomical/renderer ownership',
            inward_axis_encoded_source_yx=inward.tolist(),anatomy_classification='unknown')
        if not support.any():row['boundary']=dict(status='unobserved',reason='context_unavailable')
        else:row['boundary']=observe_context_boundary(rgb,support,inward.tolist())
        rows.append(row)
    if before!=[_pixel_sha(a) for a in [rgb,body,tip]] or original_pad_sha!=_pixel_sha(result['mask']):
        raise RuntimeError('terminal_diagnostic_inputs_or_pad_changed')
    return dict(schema_version=VERSION,rows=rows,pad_mask_pixel_sha256=original_pad_sha,
        candidate_count=len(rows),coordinate_system='encoded_source_pixels',
        anatomy_classification='unknown',pad_mask_changed=False,renderer_binding_allowed=False,
        protection_applied=False,default_pipeline_changed=False)
