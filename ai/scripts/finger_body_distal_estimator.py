"""GT-free experimental distal candidates from semantic finger-body masks.

Fixed engineering policy, not calibrated confidence or anatomical ground truth.
Only RGB-independent semantic geometry enters estimation; ridge is diagnostic.
"""
import heapq
import cv2
import numpy as np
from scipy import ndimage
from skimage.morphology import skeletonize
from skimage.segmentation import watershed
from photo_resize_safety_v1 import MAX_ESTIMATED_WORKING_BYTES, WORKING_BYTES_PER_PIXEL, ResizeSafetyError

VERSION='finger_body_distal_v2_experimental'
PAD_WIDTH_MULTIPLIER=1.35
PALM_WIDENING_RATIO=1.45
WORKING_SIDE=512


def validate_candidate_context_allocation(height,width,count):
    """Bound optional native mask retention before allocating the next owner.

    Planning estimate covers retained pad/body masks and temporary native
    planes plus the working geometry buffers. It is not a process RSS limit.
    """
    native_bytes=height*width*(8+2*count)
    geometry_bytes=WORKING_SIDE**2*WORKING_BYTES_PER_PIXEL
    audit=dict(candidate_count=count,native_shape=[height,width],
               estimated_native_mask_bytes=native_bytes,
               estimated_working_geometry_bytes=geometry_bytes,
               estimated_total_bytes=native_bytes+geometry_bytes,
               max_estimated_bytes=MAX_ESTIMATED_WORKING_BYTES)
    if audit['estimated_total_bytes']>MAX_ESTIMATED_WORKING_BYTES:
        raise ResizeSafetyError('candidate_context_memory_limit_exceeded',audit)
    return audit


def graph_path(skeleton,start):
    coords=np.argwhere(skeleton);lookup={tuple(p):i for i,p in enumerate(coords)};neighbors=[[] for _ in coords]
    for i,(y,x) in enumerate(coords):
        for dy in [-1,0,1]:
            for dx in [-1,0,1]:
                if dy==dx==0:continue
                j=lookup.get((y+dy,x+dx))
                if j is not None:neighbors[i].append((j,float(np.hypot(dx,dy))))
    endpoint=[i for i,n in enumerate(neighbors) if len(n)==1]
    if not endpoint:raise ValueError('skeleton_endpoints_unobserved')
    if start is None:start=endpoint[0]
    distances=np.full(len(coords),np.inf);parents=np.full(len(coords),-1,int);distances[start]=0;queue=[(0.,start)]
    while queue:
        d,i=heapq.heappop(queue)
        if d!=distances[i]:continue
        for j,cost in neighbors[i]:
            proposed=d+cost
            if proposed<distances[j]:distances[j]=proposed;parents[j]=i;heapq.heappush(queue,(proposed,j))
    end=max((i for i in endpoint if np.isfinite(distances[i])),key=lambda i:(distances[i],-i));path=[];i=end
    while i!=-1:path.append(i);i=parents[i]
    path=path[::-1]
    return coords,endpoint,np.asarray(path),distances[path]


def component_pad(component,tip):
    points=np.argwhere(component);mean=points.mean(axis=0);cov=np.cov(points.T);values,vectors=np.linalg.eigh(cov);axis=vectors[:,-1];anisotropy=float(values[-1]/max(values[0],1e-6));skeleton=skeletonize(component);distance=cv2.distanceTransform(component.astype(np.uint8),cv2.DIST_L2,5)
    coords,endpoints,skel_path,skel_arc=graph_path(skeleton,None)
    projections=(points-mean)@axis;low=float(projections.min());high=float(projections.max());length=high-low
    if length<12:raise ValueError('finger_too_short')
    if tip.any():
        tip_center=np.argwhere(tip).mean(axis=0);tip_t=float((tip_center-mean)@axis);distal_high=tip_t>(low+high)/2;source='semantic_class_2_and_major_axis_centerline';confidence=.75
    else:
        # A skeleton endpoint can stop a radius before the frame or end at a
        # boundary spur. Use actual component/frame intersection, not endpoint
        # distance to the frame, to identify truncation.
        h,w=component.shape;on_frame=(points[:,0]==0)|(points[:,1]==0)|(points[:,0]==h-1)|(points[:,1]==w-1)
        border_t=projections[on_frame]
        if not len(border_t) or anisotropy<1.5:raise ValueError('distal_endpoint_ambiguous_without_class_2')
        low_cut=float(np.quantile(border_t,.1))<low+.15*length;high_cut=float(np.quantile(border_t,.9))>high-.15*length
        if low_cut==high_cut:raise ValueError('distal_endpoint_ambiguous_without_class_2')
        distal_high=low_cut;source='actual_frame_cut_vs_free_major_axis_endpoint';confidence=.60
    axis=axis*(-1 if distal_high else 1);normal=np.array([-axis[1],axis[0]]);projections=(points-mean)@axis;origin=float(projections.min());longitudinal=(points-mean)@axis-origin;lateral=(points-mean)@normal
    # Robust centerline scanlines avoid degree-one skeleton spurs and preserve
    # 90-degree rotation equivariance. Skeleton endpoints remain diagnostic.
    bins=np.floor(longitudinal).astype(int);arc=[];widths=[];centers=[];scan_widths=[]
    for b in range(int(np.ceil(length))+1):
        part=points[bins==b];offsets=lateral[bins==b]
        if len(part)<2:continue
        mid=float(np.median(offsets));center=mean+axis*(origin+b+.5)+normal*mid;iy,ix=np.clip(np.rint(center).astype(int),[0,0],np.array(component.shape)-1)
        scan=float(np.quantile(offsets,.95)-np.quantile(offsets,.05)+1);dt=float(2*distance[iy,ix]);arc.append(b+.5);widths.append(scan);scan_widths.append(dt);centers.append(center)
    arc=np.asarray(arc);widths=np.asarray(widths);line=np.asarray(centers)
    region=(arc>=.10*length)&(arc<=.25*length)
    if not region.any():raise ValueError('width_profile_unstable')
    width=float(np.median(widths[region]))
    if width<4 or length/width<1.1:raise ValueError('finger_width_unstable')
    extent=min(length,PAD_WIDTH_MULTIPLIER*width);tip_extent=0.
    if tip.any():
        tip_points=np.argwhere(tip);tip_extent=float(np.quantile((tip_points-mean)@axis-origin,.99));extent=max(extent,min(length,tip_extent))
    wide=widths>PALM_WIDENING_RATIO*width;minimum_run=max(3,round(.05*length))
    # Include the last complete window; range(N-K) would skip its start N-K.
    for i in range(len(arc)-minimum_run+1):
        if arc[i]>.7*width and arc[i]>tip_extent and wide[i:i+minimum_run].all():extent=min(extent,float(arc[i]));break
    middle=np.interp(longitudinal,arc,(line-mean)@normal);chosen=(longitudinal<=extent)&(np.abs(lateral-middle)<=.75*width)
    pad=np.zeros(component.shape,bool);pad[points[chosen,0],points[chosen,1]]=True;pad|=tip&component
    start=min(endpoints,key=lambda i:(float(np.linalg.norm(coords[i]-line[0])),i))
    if not pad.any():raise ValueError('empty_distal_candidate')
    samples=np.linspace(0,len(line)-1,32).astype(int);metadata=dict(proximal_boundary_source='multi_cue_distal_geometry_candidate',distal_endpoint_source=source,confidence=confidence,confidence_semantics='fixed engineering evidence score; not probability',major_axis_yx=axis.tolist(),major_axis_anisotropy=anisotropy,skeleton_endpoints_yx=coords[endpoints].tolist(),distal_endpoint_yx=coords[start].tolist(),skeleton_length=float(skel_arc[-1]),finger_axis_length=length,reference_width=width,distal_extent=extent,width_profile=[dict(longitudinal=float(arc[i]),scanline_width=float(widths[i]),distance_transform_width=float(scan_widths[i])) for i in samples],contributing_cues=['major_axis','skeleton_geodesic_endpoints','scanline_width','distance_transform_width_diagnostic','proximal_widening']+(['semantic_class_2'] if tip.any() else ['actual_proximal_frame_intersection']),reject_reason=None)
    return pad,metadata


def estimate(body,tip,*,preserve_candidates=False):
    """Optionally retain watershed identity/body context before pad union.

    The default return contract and geometry are unchanged. Context masks are
    native encoded pixels intersected with observed body, never inferred fill.
    IDs identify this estimator run, not anatomical fingers across images.
    """
    if body.ndim!=2 or tip.shape!=body.shape:raise ValueError('semantic_mask_shape_mismatch')
    body=body.astype(bool);tip=tip.astype(bool)
    if (tip&~body).any():raise ValueError('tip_outside_finger_body')
    h,w=body.shape;scale=min(1.,WORKING_SIDE/max(h,w));size=(max(1,round(w*scale)),max(1,round(h*scale)))
    small=cv2.resize(body.astype(np.uint8),size,interpolation=cv2.INTER_NEAREST)>0;tips=cv2.resize(tip.astype(np.uint8),size,interpolation=cv2.INTER_NEAREST)>0;tips&=small
    labels,n=ndimage.label(small);regions=[];combined=np.zeros(body.shape,bool)
    for component_id in range(1,n+1):
        component=labels==component_id
        if component.sum()<.0001*small.size:continue
        markers,count=ndimage.label(tips&component)
        if count>1:
            parts=watershed(-cv2.distanceTransform(component.astype(np.uint8),cv2.DIST_L2,5),markers=markers,mask=component)
            candidates=[parts==i for i in range(1,count+1)]
        else:candidates=[component]
        for part_id,candidate in enumerate(candidates,1):
            local_tip=tips&candidate
            context={}
            if preserve_candidates:
                validate_candidate_context_allocation(h,w,len(regions)+1)
                native_body=cv2.resize(candidate.astype(np.uint8),(w,h),interpolation=cv2.INTER_NEAREST)>0
                native_body&=body
                context=dict(candidate_id=f'body-{component_id:04d}-part-{part_id:04d}',
                             watershed_part=part_id,body_mask=native_body,
                             context_coordinate_system='encoded_original_pixels')
            try:pad,metadata=component_pad(candidate,local_tip)
            except ValueError as e:regions.append(dict(component=component_id,reject_reason=str(e),confidence=0.)|context);continue
            native=cv2.resize(pad.astype(np.uint8),(w,h),interpolation=cv2.INTER_NEAREST)>0;native&=body
            # Preserve observed class-2 evidence in this component after resize.
            native_component=cv2.resize(candidate.astype(np.uint8),(w,h),interpolation=cv2.INTER_NEAREST)>0
            native|=tip&native_component;combined|=native;y,x=np.where(native);metadata.update(component=component_id,bbox=[int(x.min()),int(y.min()),int(x.max())+1,int(y.max())+1],working_scale=scale,metadata_coordinate_system='working_image_pixels',mask=native);regions.append(metadata|context)
    assert not (combined&~body).any()
    return dict(mask=combined,regions=regions,detector_version=VERSION,approved_for_use=False,body_exterior_pixels=0)
