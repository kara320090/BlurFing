"""Generated ridge interruptions and bounded coarse contour color continuation."""
import cv2
import numpy as np
from scipy import ndimage
from scipy.interpolate import PchipInterpolator
from scipy.spatial import cKDTree
from organic_ridge_profile import smooth_random
from photo_synthetic_replacement_v6 import smoothstep
from photo_synthetic_replacement_v2 import geometry,color_cells


def irregular_coordinates(shape,pitch,seed):
    if shape!=(512,512) or not np.isfinite(pitch) or not 4<=pitch<=16:
        raise ValueError('organic_canonical_geometry_contract')
    rng=np.random.default_rng(seed ^ 0x1919)
    offsets=[]
    for _ in range(2):
        broad=smooth_random(shape,11,pitch*1.2,rng)*pitch*.45
        local=smooth_random(shape,37,max(1.,pitch*.45),rng)*pitch*.22
        offsets.append(broad+local)
    dy,dx=offsets;ay,ax=np.gradient(dy);by,bx=np.gradient(dx)
    norm=np.sqrt(ay*ay+ax*ax+by*by+bx*bx)
    factor=min(1.,.32/max(float(norm.max()),1e-6));dy*=factor;dx*=factor
    return dy,dx,dict(displacement_jacobian_frobenius_bound=float(norm.max()*factor),
        mapping_minimum_singular_value_bound=.68,source_input=False)


def interrupted_profile(profile,geometry_mask,pitch,seed):
    if (profile.shape!=(512,512) or not np.isfinite(profile).all()
            or geometry_mask.shape!=profile.shape or geometry_mask.dtype!=np.bool_):
        raise ValueError('organic_profile_contract')
    dy,dx,warp=irregular_coordinates(profile.shape,pitch,seed)
    y,x=np.mgrid[:512,:512]
    result=ndimage.map_coordinates(profile,[y+dy,x+dx],order=3,mode='reflect',prefilter=True)
    # A generated structure tensor defines each synthetic ridge's direction.
    gy,gx=np.gradient(result)
    a=cv2.GaussianBlur(gx*gx-gy*gy,(0,0),pitch*.35)
    b=cv2.GaussianBlur(2*gx*gy,(0,0),pitch*.35)
    angle=.5*np.arctan2(b,a)
    interior=ndimage.distance_transform_edt(np.pad(geometry_mask,1))[1:-1,1:-1]>2*pitch
    candidates=np.column_stack(np.nonzero(interior & (result>.85)))
    rng=np.random.default_rng(seed ^ 0xE019)
    count=min(48,max(1,int(geometry_mask.sum()/(80*pitch*pitch))))
    centers=[]
    for index in rng.permutation(len(candidates))[:4096]:
        cy,cx=map(int,candidates[index])
        if any((cy-py)**2+(cx-px)**2<(4*pitch)**2 for py,px in centers):continue
        centers.append((cy,cx))
        radius=int(np.ceil(2*pitch))
        top,bottom=max(0,cy-radius),min(512,cy+radius+1)
        left,right=max(0,cx-radius),min(512,cx+radius+1)
        yy,xx=np.mgrid[top:bottom,left:right];theta=float(angle[cy,cx])
        cross=(xx-cx)*np.cos(theta)+(yy-cy)*np.sin(theta)
        along=-(xx-cx)*np.sin(theta)+(yy-cy)*np.cos(theta)
        width=pitch*rng.uniform(.16,.23);span=pitch*rng.uniform(.45,.85)
        cut=np.exp(-.5*(cross/width)**2-.5*(along/span)**4)
        part=result[top:bottom,left:right]
        cut*=smoothstep((part+.1)/.9)*rng.uniform(.85,1.)
        result[top:bottom,left:right]=part*(1-cut)-cut
        if len(centers)>=count:break
    result-=float(result.mean());result/=max(float(result.std()),1e-6)
    return result.astype(np.float32),dict(method='generated_local_warp_and_sparse_ridge_tapered_interruptions',
        warp=warp,generated_interruptions=len(centers),maximum_interruptions=48,
        minimum_center_spacing_canonical_pixels=4*pitch,original_ridge_phase_input=False,
        original_ridge_orientation_input=False,other_finger_donor=False)


def guard_contour_correction(generated,candidate,pixels,local):
    """Compare coarse boundary mixtures after actual RGB8 rounding, not phase."""
    y,x,u,v,width,length=geometry(local)
    groups,_,_=color_cells(u,v,width,length)
    edge=ndimage.distance_transform_edt(np.pad(local,1))[1:-1,1:-1][local]<=3
    old=np.clip(np.floor(generated+.5),0,255);new=np.clip(np.floor(candidate+.5),0,255)
    before=after=weight=0.
    for group in np.unique(groups[edge]):
        take=edge & (groups==group);n=int(take.sum())
        if n<8:continue
        target=pixels[take].mean(axis=0)
        before+=float(abs(old[take].mean(axis=0)-target).mean())*n
        after+=float(abs(new[take].mean(axis=0)-target).mean())*n
        weight+=n
    accepted=bool(weight and after<before)
    return (candidate if accepted else generated),dict(
        accepted=accepted,before_RGB_error=before/max(1.,weight),
        proposed_RGB_error=after/max(1.,weight),supported_pixels=int(weight),
        actual_RGB8_rounding_used=True,scope='coarse_inside_boundary_RGB_mixture_not_naturalness')


def contour_continuation(generated,pixels,local,width):
    """Positive-weight PCHIP of aggregated inside-contour RGB corrections.

    No external pixel, source residual raster or original alpha is used.
    Shape-preserving interpolation prevents the Hermite slope overshoot that
    can create bright boundary rims. Only a bounded inside ribbon is changed.
    """
    if (generated.shape!=pixels.shape or generated.ndim!=2 or generated.shape[1]!=3
            or local.ndim!=2 or local.dtype!=np.bool_ or local.size>8*1024*1024
            or len(pixels)>4*1024*1024 or int(local.sum())!=len(pixels)
            or not len(pixels) or not np.isfinite(pixels).all()
            or not np.isfinite(generated).all() or not np.isfinite(width) or width<=0):
        raise ValueError('organic_contour_contract')
    distance=ndimage.distance_transform_edt(np.pad(local,1))[1:-1,1:-1][local]
    contours,_=cv2.findContours(local.astype(np.uint8),cv2.RETR_LIST,cv2.CHAIN_APPROX_NONE)
    outline=np.concatenate([c[:,0] for c in contours])
    count=min(192,max(4,round(len(outline)/max(24.,.07*width))))
    nodes=np.unique(outline[np.linspace(0,len(outline)-1,count,dtype=int)],axis=0)
    y,x=np.nonzero(local);points=np.column_stack((x,y));owner=cKDTree(nodes).query(points,k=1)[1]
    transition=max(8.,.06*width);band=max(1.5,.006*width)
    knots=np.array([1.,1.+transition*.28,1.+transition*.64,1.+transition])
    centers=[];values=[]
    for node in range(len(nodes)):
        owned=owner==node;data=[];supported=True
        for j,knot in enumerate(knots[:-1]):
            take=owned & (abs(distance-knot)<=band)
            if take.sum()<24:supported=False;break
            # Means retain the antialiased skin/background mixture; separate
            # source/generated aggregation exports no paired pixel residual.
            delta=np.mean(pixels[take],axis=0)-np.mean(generated[take],axis=0)
            data.append(np.clip(delta,-16.,16.))
        if not supported:continue
        centers.append(nodes[node]);values.append(data+[np.zeros(3)])
    meta=dict(method='coarse_inside_contour_mixture_mean_shape_preserving_color_continuation',
        maximum_nodes=192,populated_nodes=len(centers),minimum_band_support=24,
        sample_depths=knots.tolist(),transition_width=transition,maximum_RGB_correction=16.,
        original_pixel_alpha=0.,source_filtered_raster_exported=False,source_outside_permission_used=False,
        mask_geometry_changed=False,interpolation_overshoot_allowed=False)
    if len(centers)<4:return generated,meta|dict(applied=False)
    interpolator=PchipInterpolator(knots,np.array(values),axis=1,extrapolate=False)
    # Explicit zero derivative at the inner join without extrapolating slopes.
    tree=cKDTree(centers);result=generated.copy();active=np.flatnonzero(distance<knots[-1])
    for start in range(0,len(active),4096):
        take=active[start:start+4096]
        delta,indices=tree.query(points[take],k=min(4,len(centers)))
        weights=1/(delta*delta+4.)**1.5;weights/=weights.sum(axis=1,keepdims=True)
        # Evaluate only selected nodes: <=4096 queries, never nodes x all pixels.
        t=np.clip(distance[take],knots[0],knots[-1]);correction=np.zeros((len(take),3))
        for j in range(indices.shape[1]):
            interval=np.clip(np.searchsorted(knots,t,side='right')-1,0,len(knots)-2)
            # Pchip moves the interpolation axis first: degree, interval, node, RGB.
            coeff=interpolator.c[:,interval,indices[:,j],:]
            dt=(t-knots[interval])[:,None]
            evaluated=((coeff[0]*dt+coeff[1])*dt+coeff[2])*dt+coeff[3]
            correction+=evaluated*weights[:,j,None]
        end=smoothstep((knots[-1]-distance[take])/(transition*.36))
        result[take]+=np.clip(correction,-16.,16.)*end[:,None]
    if not np.isfinite(result).all():raise ValueError('organic_contour_nonfinite')
    result,decision=guard_contour_correction(generated,result,pixels,local)
    return result,meta|dict(applied=decision['accepted'],boundary_guard=decision)
