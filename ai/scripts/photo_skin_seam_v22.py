"""Experimental low-order material continuation after V21 silhouette correction.

An object silhouette and an internal permission seam are different boundaries.
Leave sharp color steps to V21; add only a bounded low-order RGB correction on
smooth material arcs or one broad fold. Source tangent means enter nine color
coefficients and at most two fold parameters, never an image residual/alpha.
This is not a skin classifier or a biometric privacy proof.
"""
import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree
from scipy.optimize import least_squares
from photo_silhouette_appearance_v21 import _curve, _sample, _fit_profile
from photo_synthetic_replacement_v6 import smoothstep

VERSION='coarse_material_continuation_v22_experimental'
MAX_CROP_PIXELS=8*1024*1024
MAX_PERMISSION_PIXELS=4*1024*1024


def refine_complete(source,v19,applied,labels):
    from photo_silhouette_appearance_v21 import refine_regions as silhouette
    intermediate,rim=silhouette(source,v19,applied,labels,texture_mode='interior_envelope')
    returned,material=refine_regions(source,intermediate,applied,labels)
    return returned,dict(version='generated_envelope_and_material_v22',silhouette=rim,material=material,
        permission_geometry_changed=False,default_promoted=False,privacy_validated=False)


def _quadratic(profile,t,radius):
    z=t/radius;design=np.column_stack((np.ones(len(z)),z,z*z))
    coefficients=np.linalg.lstsq(design,profile,rcond=None)[0]
    predicted=design@coefficients
    # Fixed absolute RGB reconstruction budget, not fitted to a photo/label.
    # A large step, narrow fold, or repeated high-amplitude profile abstains.
    rmse=float(np.sqrt(np.mean((predicted-profile)**2)))
    if rmse>2. or np.max(abs(predicted-profile))>6.:
        return None
    return coefficients,rmse


def _design(t,radius):
    z=t/radius
    return np.column_stack((np.ones(len(z)),z,z*z))


def _material(profile,t,radius):
    smooth=_quadratic(profile,t,radius)
    if smooth is not None:
        return dict(kind='quadratic',coeff=smooth[0],RMSE=smooth[1])
    affine=np.column_stack((np.ones(len(t)),t/radius))
    linear=affine@np.linalg.lstsq(affine,profile,rcond=None)[0]
    baseline=float(np.mean((linear-profile)**2))
    if baseline<1.:return None
    minimum_sigma=max(4.,.18*radius)
    def solve(q):
        design=np.column_stack((affine,np.exp(-.5*((t-q[0])/q[1])**2)))
        coeff=np.linalg.lstsq(design,profile,rcond=None)[0]
        return design@coeff,coeff
    initial=np.clip(t[np.argmin((profile-linear).mean(axis=1))],-.5*radius,.5*radius)
    fitted=least_squares(lambda q:(solve(q)[0]-profile).ravel(),[initial,minimum_sigma*1.2],
        bounds=([-.6*radius,minimum_sigma],[.6*radius,.65*radius]),max_nfev=60)
    predicted,coeff=solve(fitted.x)
    error=float(np.sqrt(np.mean((predicted-profile)**2)))
    # A single broad dark fold, not a periodic ridge train or sharp crease.
    # Reuse the existing macro-fold depth ceiling, without changing that renderer.
    if (not fitted.success or error>2. or np.max(abs(predicted-profile))>6.
            or 1.-error**2/baseline<.9 or np.any(coeff[2]>0.)
            or float(-coeff[2].mean())<4.
            or float(-coeff[2].min())>24. or fitted.x[1]<=minimum_sigma*1.01):
        return None
    return dict(kind='broad_fold',coeff=coeff,RMSE=error,
        center=float(fitted.x[0]),sigma=float(fitted.x[1]))


def _material_design(t,radius,model):
    if model['kind']=='quadratic':return _design(t,radius)
    return np.column_stack((np.ones(len(t)),t/radius,np.exp(-.5*((t-model['center'])/model['sigma'])**2)))


def refine(source,generated,permission,width):
    if (not isinstance(permission,np.ndarray) or permission.dtype!=np.bool_ or permission.ndim!=2
            or permission.size>MAX_CROP_PIXELS or max(permission.shape,default=0)>32768
            or not isinstance(source,np.ndarray) or not isinstance(generated,np.ndarray)
            or source.dtype!=np.uint8 or generated.dtype!=np.uint8
            or source.shape!=permission.shape+(3,) or generated.shape!=source.shape
            or not np.isfinite(width) or width<=0):
        raise ValueError('material_seam_RGB8_geometry_contract')
    count=int(permission.sum())
    if not count or count>MAX_PERMISSION_PIXELS:raise ValueError('material_seam_permission_size')
    radius=max(16.,.06*width)
    if radius>256.:raise ValueError('material_seam_extent')
    if ndimage.label(permission)[1]!=1:raise ValueError('material_seam_single_component')
    result=generated.copy()
    meta=dict(version=VERSION,applied=False,correction_depth=radius,permission_geometry_changed=False,
        source_pixel_alpha=0.,source_context_used=True,source_filtered_raster_exported=False,
        source_dependency='tangent_RGB_means_nine_low_order_color_coefficients_optional_two_broad_fold_parameters',
        generated_ridge_phase_replaced=False,privacy_validated=False,natural_appearance_validated=False)
    curve=_curve(permission,width)
    if curve is None:return result,meta|dict(reason='unsupported_contour')
    nodes,normals,tangents,half=curve;half=max(24.,half)
    t=np.linspace(-radius,radius,65);along=np.linspace(-half,half,max(49,int(2*half)+1))
    src=source.astype(np.float32);gen=generated.astype(np.float32);allowed=permission.astype(float)
    models=[];steps=[];h,w=permission.shape
    for node,normal,tangent in zip(nodes,normals,tangents):
        pos=node+t[:,None,None]*normal+along[None,:,None]*tangent
        if pos[...,0].min()<0 or pos[...,1].min()<0 or pos[...,0].max()>w-1 or pos[...,1].max()>h-1:
            models.append(None);steps.append(False);continue
        samples=_sample(src,pos);profile=samples.mean(axis=1)
        step=_fit_profile(profile,t,radius) is not None;steps.append(step)
        fitted=None if step else _material(profile,t,radius)
        if fitted is None:models.append(None);continue
        coeff,error=fitted['coeff'],fitted['RMSE']
        usable=ndimage.map_coordinates(allowed,np.stack((pos[...,1],pos[...,0])),order=0,mode='constant')>.5
        counts=usable.sum(axis=1)
        good=(t>=1.)&(counts>=.75*len(along))
        if good.sum()<12:models.append(None);continue
        original=(samples*usable[...,None]).sum(axis=1)/np.maximum(counts[:,None],1)
        current=(_sample(gen,pos)*usable[...,None]).sum(axis=1)/np.maximum(counts[:,None],1)
        design=_material_design(t[good],radius,fitted)
        generated_coeff=np.linalg.lstsq(design,current[good],rcond=None)[0]
        delta=coeff-generated_coeff
        observed=original[good]-current[good]
        lower=np.minimum(0.,observed.min(axis=0));upper=np.maximum(0.,observed.max(axis=0))
        correction=np.clip(design@delta,lower,upper)
        fade=1.-smoothstep((t[good]-radius*.4)/(radius*.6))
        before=float(np.mean((current[good]-original[good])**2))
        after=float(np.mean((current[good]+correction*fade[:,None]-original[good])**2))
        if after>=before:models.append(None);continue
        models.append(dict(delta=delta,lower=lower,upper=upper,material=fitted,source_fit_RMSE=error,
            predicted_before_MSE=before,predicted_after_MSE=after))
    valid=np.array([m is not None for m in models]);step=np.array(steps)
    # Keep the existing silhouette and its transition neighbors completely out
    # of the new node set. Unsupported arcs carry zero interpolation weight.
    valid&=~(step|np.roll(step,1)|np.roll(step,-1))
    isolated=valid.copy()
    valid&=(np.roll(isolated,1)&np.roll(isolated,-1))|(
        np.roll(isolated,1)&np.roll(isolated,2))|(np.roll(isolated,-1)&np.roll(isolated,-2))
    meta.update(nodes=len(nodes),supported_nodes=int(valid.sum()),step_nodes=int(step.sum()),
        broad_fold_nodes=int(sum(valid[i] and m['material']['kind']=='broad_fold' for i,m in enumerate(models) if m is not None)),
        minimum_consecutive_nodes=3,source_fit_max_RGB_RMSE=2.,maximum_query_chunk=4096)
    if not valid.any():return result,meta|dict(reason='no_supported_continuous_material_arc')
    distance=ndimage.distance_transform_edt(np.pad(permission,1))[1:-1,1:-1]
    active=permission&(distance<radius);y,x=np.nonzero(active);points=np.column_stack((x,y));tree=cKDTree(nodes)
    for start in range(0,len(y),4096):
        sl=slice(start,start+4096);p=points[sl]
        distances,ids=tree.query(p,k=min(4,len(nodes)))
        weights=(distances**2+4.)**-1.5;weights/=weights.sum(axis=1,keepdims=True)
        correction=np.zeros((len(p),3));closest=normals[ids[:,0]]
        for j in range(ids.shape[1]):
            for i in np.unique(ids[:,j]):
                if not valid[i]:continue
                take=ids[:,j]==i;m=models[i]
                projection=np.clip((p[take]-nodes[i])@normals[i],1.,radius)
                value=np.clip(_material_design(projection,radius,m['material'])@m['delta'],m['lower'],m['upper'])
                agree=np.clip(closest[take]@normals[i],0.,1.)**4
                correction[take]+=value*(weights[take,j]*agree)[:,None]
        fade=1.-smoothstep((distance[y[sl],x[sl]]-radius*.4)/(radius*.6))
        result[y[sl],x[sl]]=np.clip(np.floor(generated[y[sl],x[sl]]+correction*fade[:,None]+.5),0,255).astype(np.uint8)
    # Actual quantized-result check, using matched support on both images.
    before=[];after=[];weights=[];out=result.astype(np.float32);active_float=active.astype(float)
    for i in np.flatnonzero(valid):
        pos=nodes[i]+t[:,None,None]*normals[i]+along[None,:,None]*tangents[i]
        use=ndimage.map_coordinates(active_float,np.stack((pos[...,1],pos[...,0])),order=0,mode='constant')>.5
        counts=use.sum(axis=1);good=(t>=1)&(counts>=.75*len(along))
        if not good.any():continue
        means=[(_sample(a,pos)*use[...,None]).sum(axis=1)/np.maximum(counts[:,None],1) for a in (src,gen,out)]
        before.append(float(np.mean((means[0][good]-means[1][good])**2)))
        after.append(float(np.mean((means[0][good]-means[2][good])**2)))
        weights.append(int(counts[good].sum()))
    accepted=bool(before and np.average(after,weights=weights)<np.average(before,weights=weights))
    meta.update(applied=accepted,reason='material_profile_improved' if accepted else 'material_profile_not_improved',
        proposed_changed_pixels=int(np.any(result!=generated,axis=2).sum()),
        profile_guard=dict(before_MSE=float(np.average(before,weights=weights)) if before else None,
            after_MSE=float(np.average(after,weights=weights)) if after else None,
            per_node_before_MSE=before,per_node_after_MSE=after,accepted=accepted,
            scope='coarse_material_RGB_not_naturalness_or_privacy'))
    return (result if accepted else generated.copy()),meta


def refine_regions(source,generated,applied,labels):
    """Bounded native-coordinate adapter; never changes authorizations."""
    from photo_resize_safety_v1 import validate_resize
    from photo_synthetic_replacement_v2 import geometry
    if (not isinstance(source,np.ndarray) or source.dtype!=np.uint8 or source.ndim!=3 or source.shape[-1]!=3
            or not isinstance(generated,np.ndarray) or generated.dtype!=np.uint8 or generated.shape!=source.shape
            or not isinstance(applied,np.ndarray) or applied.dtype!=np.bool_ or applied.shape!=source.shape[:2]
            or not isinstance(labels,np.ndarray) or labels.dtype!=np.uint16 or labels.shape!=applied.shape):
        raise ValueError('material_region_adapter_contract')
    validate_resize(*applied.shape,1.)
    if np.any(applied&(labels==0)):raise ValueError('material_region_adapter_permission')
    ids=np.unique(labels[applied])
    if len(ids)>256:raise ValueError('material_region_adapter_count')
    from photo_parallel_regions_v32 import split_regions
    parallel=split_regions(refine_regions,source,generated,applied,labels)
    if parallel is not None:return parallel
    result=generated.copy();rows=[];total=0
    for rid,sl in enumerate(ndimage.find_objects(labels),1):
        if sl is None or rid not in ids:continue
        parts,count=ndimage.label(applied[sl]&(labels[sl]==rid));total+=count
        if total>256:raise ValueError('material_region_adapter_count')
        for part,box in enumerate(ndimage.find_objects(parts),1):
            local=parts[box]==part;row=dict(region_id=rid,part=part)
            if local.size>MAX_CROP_PIXELS or int(local.sum())>MAX_PERMISSION_PIXELS:
                rows.append(row|dict(applied=False,reason='size_limit_previous_retained'));continue
            _,_,_,_,width,_=geometry(local);radius=max(16.,.06*width)
            if radius>256.:
                rows.append(row|dict(applied=False,reason='extent_limit_previous_retained'));continue
            pad=int(np.ceil(2*radius+max(24.,.03*width)+8))
            y0,x0=sl[0].start+box[0].start,sl[1].start+box[1].start
            y1,x1=y0+local.shape[0],x0+local.shape[1]
            cy0,cx0=max(0,y0-pad),max(0,x0-pad)
            cy1,cx1=min(applied.shape[0],y1+pad),min(applied.shape[1],x1+pad)
            if (cy1-cy0)*(cx1-cx0)>MAX_CROP_PIXELS:
                rows.append(row|dict(applied=False,reason='context_limit_previous_retained'));continue
            permission=np.zeros((cy1-cy0,cx1-cx0),bool)
            permission[y0-cy0:y1-cy0,x0-cx0:x1-cx0]=local
            crop,meta=refine(source[cy0:cy1,cx0:cx1],generated[cy0:cy1,cx0:cx1],permission,width)
            result[cy0:cy1,cx0:cx1][permission]=crop[permission];rows.append(row|meta)
    return result,dict(version=VERSION,regions=rows,corrected_components=sum(r['applied'] for r in rows),
        permission_geometry_changed=False,default_promoted=False,privacy_validated=False)
