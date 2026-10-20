"""Opt-in coarse 2D junction appearance; unchanged protection authorization.

Fit a planar soft silhouette and optionally one crossing broad fold to cell RGB
means. Only low-dimensional parameters reach the output; source raster/detail
does not. This source-dependent appearance experiment is not a privacy proof.
"""
import numpy as np
from scipy import ndimage
from scipy.optimize import least_squares
from scipy.special import ndtr
from scipy.spatial import cKDTree
from photo_silhouette_appearance_v21 import _curve, _sample
from photo_synthetic_replacement_v6 import smoothstep
from photo_junction_fit_runtime_v1 import fit_patches

VERSION = 'coarse_2D_junction_v23_experimental'
MAX_CROP_PIXELS = 8*1024*1024
MAX_PERMISSION_PIXELS = 4*1024*1024
MAX_NODES = 96


def cell_grid(radius):
    centers = np.linspace(-radius, radius, 13)
    v, u = np.meshgrid(centers, centers, indexing='ij')
    uv = np.column_stack((u.ravel(), v.ravel()))
    offsets = np.linspace(-radius/13, radius/13, 3)
    ov, ou = np.meshgrid(offsets, offsets, indexing='ij')
    return uv[:, None, :] + np.column_stack((ou.ravel(), ov.ravel()))[None, :, :]


def design(points, q, radius):
    u, v = points[..., 0]/radius, points[..., 1]/radius
    distance = points[..., 0]*np.cos(q[0])+points[..., 1]*np.sin(q[0])-q[1]
    alpha = ndtr(distance/q[2])
    # Rounded skin has cross-normal curvature even at a straight silhouette.
    # An affine skin model incorrectly asks the fold to absorb this shading.
    terms = [np.ones_like(u), u, v, alpha, alpha*u, alpha*v,
             alpha*u*u, alpha*u*v, alpha*v*v]
    if len(q) == 6:
        fold_distance = points[..., 0]*np.cos(q[3])+points[..., 1]*np.sin(q[3])-q[4]
        terms.append(alpha*np.exp(-.5*(fold_distance/q[5])**2))
    return np.stack(terms, axis=-1), alpha


def fit_patch(means, cells, radius):
    """Fit 4/5 of spatial cells; keep the remaining checkerboard cells as a guard."""
    if (means.shape != (169, 3) or cells.shape != (169, 9, 2)
            or not np.isfinite(means).all() or not np.isfinite(cells).all()
            or not np.isfinite(radius) or radius < 16 or radius > 256):
        raise ValueError('junction_cell_contract')
    center = cells.mean(axis=1)
    grid = means.reshape(13, 13, 3)
    # No need to replace an effectively one-dimensional V21/V22 profile.
    if float(np.mean((grid-grid.mean(axis=0, keepdims=True))**2)) < 4.:
        return None
    rr, cc = np.mgrid[:13, :13]
    validation = ((rr+2*cc) % 5 == 0).ravel()
    training = ~validation
    affine = np.column_stack((np.ones(169), center/radius))
    plane = affine @ np.linalg.lstsq(affine[training], means[training], rcond=None)[0]
    baseline = float(np.mean((plane[validation]-means[validation])**2))
    if baseline < 4.:
        return None
    # Color-vector gradient estimates orientation even for a dark skin/background step.
    du = np.diff(grid, axis=1).mean(axis=0).sum(axis=0)
    dv = np.diff(grid, axis=0).mean(axis=1).sum(axis=0)
    eigenvalues, eigenvectors = np.linalg.eigh(np.array([[du@du, du@dv], [du@dv, dv@dv]]))
    direction = eigenvectors[:, -1]
    if direction[0] < 0:direction = -direction
    theta = float(np.clip(np.arctan2(direction[1], direction[0]), -1.55, 1.55))

    def optimize(initial, lower, upper):
        def solve(q):
            matrix = design(cells, q, radius)[0].mean(axis=1)
            coeff = np.linalg.lstsq(matrix[training], means[training], rcond=None)[0]
            return matrix@coeff, coeff
        fit = least_squares(lambda q:(solve(q)[0][training]-means[training]).ravel(),
            initial, bounds=(lower, upper), max_nfev=60, ftol=1e-6, xtol=1e-6, gtol=1e-6)
        predicted, coeff = solve(fit.x)
        return fit, predicted, coeff

    lo = [-np.pi/2, -.8*radius, .5]
    hi = [np.pi/2, .8*radius, .22*radius]
    fit, predicted, coeff = optimize([theta, 0., max(1., .05*radius)], lo, hi)
    candidates = [(fit, predicted, coeff)]
    residual = means-predicted
    dark = -residual.mean(axis=1)
    selected = dark > max(2., float(np.quantile(dark, .75)))
    if fit.success and selected.sum() >= 8:
        points = center[selected];weights = dark[selected]
        centroid = np.average(points, axis=0, weights=weights)
        centered = points-centroid
        covariance = (centered*weights[:, None]).T@centered/weights.sum()
        _, vectors = np.linalg.eigh(covariance)
        phi = float(np.arctan2(vectors[1, 0], vectors[0, 0]))
        offset = float(np.clip(centroid@vectors[:, 0], -.5*radius, .5*radius))
        minimum = max(4., .15*radius)
        # The residual's strongest axis may be skin shading. Also initialize a
        # crossing fold independently of that residual orientation.
        for angle in (phi, float(fit.x[0]+np.pi/2)):
            offset=float(np.clip(centroid@np.array([np.cos(angle),np.sin(angle)]),-.5*radius,.5*radius))
            q = list(fit.x)+[angle, offset, max(minimum*1.3, .2*radius)]
            candidates.append(optimize(q, lo+[angle-np.pi/3, -.8*radius, minimum],
                                       hi+[angle+np.pi/3, .8*radius, .6*radius]))
    accepted = []
    for fit, predicted, coeff in candidates:
        q = fit.x
        error = np.sqrt(np.mean((predicted[validation]-means[validation])**2))
        alpha = design(center, q, radius)[1]
        if (alpha < .1).sum() < 12 or (alpha > .9).sum() < 12:continue
        contrast=float(np.linalg.norm(means[alpha>.9].mean(axis=0)-means[alpha<.1].mean(axis=0)))
        # Polynomial coefficients depend on the coordinate origin and can cancel.
        # Guard actual predictions on measured support, not an affine slope bound.
        native=design(cells,q,radius)[0]@coeff
        lower=means.min(axis=0)-12.;upper=means.max(axis=0)+12.
        if (not fit.success or error > 3. or np.max(abs(predicted-means)) > 12.
                or 1.-error**2/baseline < .85 or contrast < 25.
                or q[2] >= .215*radius
                or np.any(native<lower) or np.any(native>upper)):
            continue
        if len(q) == 6:
            if (np.any(coeff[9] > 0) or -coeff[9].mean() < 4.
                    or -coeff[9].min() > 24. or q[5] <= max(4., .15*radius)*1.01
                    or abs(np.cos(q[3]-q[0])) > .95):
                continue
        accepted.append(dict(q=q, coefficients=coeff, validation_RMSE=float(error),
            kind='edge_and_crossing_fold' if len(q)==6 else 'oblique_edge',
            validation_cells=int(validation.sum()),color_lower=lower,color_upper=upper))
    return min(accepted, key=lambda m:m['validation_RMSE']) if accepted else None


def refine(source, generated, permission, width):
    if (not isinstance(permission, np.ndarray) or permission.dtype != np.bool_ or permission.ndim != 2
            or permission.size > MAX_CROP_PIXELS or max(permission.shape, default=0)>32768
            or not isinstance(source, np.ndarray) or not isinstance(generated, np.ndarray)
            or source.dtype != np.uint8 or generated.dtype != np.uint8
            or source.shape != permission.shape+(3,) or generated.shape != source.shape
            or not np.isfinite(width) or width <= 0):
        raise ValueError('junction_RGB8_geometry_contract')
    if not permission.any() or int(permission.sum())>MAX_PERMISSION_PIXELS:
        raise ValueError('junction_permission_size')
    depth=max(16., .06*width);radius=2*depth
    if radius>256.:raise ValueError('junction_extent')
    if ndimage.label(permission)[1]!=1:raise ValueError('junction_single_component')
    result=generated.copy()
    meta=dict(version=VERSION, applied=False, correction_depth=depth, patch_radius=radius,
        permission_geometry_changed=False, source_pixel_alpha=0., source_context_used=True,
        source_filtered_raster_exported=False, source_dependency='cell_RGB_means_low_dimensional_2D_edge_optional_fold',
        privacy_validated=False, natural_appearance_validated=False, maximum_nodes=MAX_NODES)
    curve=_curve(permission,width)
    if curve is None:return result,meta|dict(reason='unsupported_contour')
    nodes,normals,tangents,_=curve
    if len(nodes)>MAX_NODES:
        take=np.linspace(0,len(nodes),MAX_NODES,endpoint=False,dtype=int)
        nodes,normals,tangents=nodes[take],normals[take],tangents[take]
    cells=cell_grid(radius);src=source.astype(np.float32);positions=[];tasks=[];task_nodes=[]
    h,w=permission.shape
    for node,n,t in zip(nodes,normals,tangents):
        pos=node+cells[...,0,None]*n+cells[...,1,None]*t
        if (pos[...,0].min()<0 or pos[...,1].min()<0 or pos[...,0].max()>w-1 or pos[...,1].max()>h-1):
            positions.append(None);continue
        task_nodes.append(len(positions));positions.append(pos)
        tasks.append((_sample(src,pos).mean(axis=1),cells,radius))
    models=[None]*len(positions)
    for i,model in zip(task_nodes,fit_patches(tasks,fit_patch)):
        models[i]=model
    valid=np.array([m is not None for m in models])
    meta.update(nodes=len(nodes),supported_nodes=int(valid.sum()),
        crossing_fold_nodes=sum(m is not None and m['kind']=='edge_and_crossing_fold' for m in models))
    if not valid.any():return result,meta|dict(reason='no_supported_2D_patch')
    distance=ndimage.distance_transform_edt(np.pad(permission,1))[1:-1,1:-1]
    active=permission&(distance<depth);y,x=np.nonzero(active)
    sigma=max(3.,.012*width);support=ndimage.gaussian_filter(permission.astype(float),sigma,mode='constant')
    interior=permission&(distance>=depth)&(distance<2*depth)
    if interior.sum()<64:return result,meta|dict(reason='insufficient_generated_texture_support')
    texture=np.empty((len(y),3))
    for c in range(3):
        base=ndimage.gaussian_filter(np.where(permission,generated[...,c],0.).astype(float),
            sigma,mode='constant')/np.maximum(support,1e-9)
        values=generated[...,c][interior]-base[interior];lo,hi=np.quantile(values,[.01,.99])
        texture[:,c]=np.clip(generated[y,x,c]-base[y,x],min(0.,lo),max(0.,hi))
    tree=cKDTree(nodes)
    for start in range(0,len(y),4096):
        sl=slice(start,start+4096);points=np.column_stack((x[sl],y[sl]))
        _,ids=tree.query(points,k=min(4,len(nodes)))
        color=np.zeros((len(points),3));weights=np.zeros(len(points));coverage=np.zeros(len(points))
        for j in range(ids.shape[1]):
            for i in np.unique(ids[:,j]):
                if not valid[i]:continue
                take=ids[:,j]==i;delta=points[take]-nodes[i]
                uv=np.column_stack((delta@normals[i],delta@tangents[i]))
                # Prediction remains in the measured patch, with a finite smooth footprint.
                # A validated patch has full support in its central half.
                # Fading from its exact center leaves a ghost of a false edge
                # even when the fitted geometry correctly places background there.
                weight=1.-smoothstep((np.max(abs(uv),axis=1)/radius-.5)/.5)
                matrix,alpha=design(uv,models[i]['q'],radius)
                coarse=np.clip(matrix@models[i]['coefficients'],models[i]['color_lower'],models[i]['color_upper'])
                estimate=coarse+texture[sl][take]*alpha[:,None]
                color[take]+=weight[:,None]*estimate;weights[take]+=weight
                coverage[take]=np.maximum(coverage[take],weight)
        color/=np.maximum(weights[:,None],1e-9)
        fade=1.-smoothstep((distance[y[sl],x[sl]]-depth*.4)/(depth*.6))
        mix=coverage*fade
        result[y[sl],x[sl]]=np.clip(np.floor(generated[y[sl],x[sl]]*(1.-mix[:,None])+color*mix[:,None]+.5),0,255).astype(np.uint8)
    before=[];after=[];counts=[];gen=generated.astype(np.float32);out=result.astype(np.float32);active_float=active.astype(float)
    for i in np.flatnonzero(valid):
        pos=positions[i]
        use=ndimage.map_coordinates(active_float,np.stack((pos[...,1],pos[...,0])),order=0,mode='constant')>.5
        n=use.sum(axis=1);good=n>=5
        if not good.any():continue
        mean=[(_sample(a,pos)*use[...,None]).sum(axis=1)/np.maximum(n[:,None],1) for a in (src,gen,out)]
        before.append(float(np.mean((mean[0][good]-mean[1][good])**2)))
        after.append(float(np.mean((mean[0][good]-mean[2][good])**2)));counts.append(int(n[good].sum()))
    accepted=bool(before and np.average(after,weights=counts)<np.average(before,weights=counts))
    meta.update(applied=accepted,reason='coarse_2D_error_improved' if accepted else 'coarse_2D_error_not_improved',
        changed_pixels=int(np.any(result!=generated,axis=2).sum()) if accepted else 0,
        profile_guard=dict(before_MSE=float(np.average(before,weights=counts)) if before else None,
            after_MSE=float(np.average(after,weights=counts)) if after else None,
            per_node_before_MSE=before,per_node_after_MSE=after,accepted=accepted,
            scope='coarse_cell_color_not_naturalness_or_privacy'))
    return (result if accepted else generated.copy()),meta


def refine_regions(source,generated,applied,labels):
    from photo_resize_safety_v1 import validate_resize
    from photo_synthetic_replacement_v2 import geometry
    if (not isinstance(source,np.ndarray) or source.dtype!=np.uint8 or source.ndim!=3 or source.shape[-1]!=3
            or not isinstance(generated,np.ndarray) or generated.dtype!=np.uint8 or generated.shape!=source.shape
            or not isinstance(applied,np.ndarray) or applied.dtype!=np.bool_ or applied.shape!=source.shape[:2]
            or not isinstance(labels,np.ndarray) or labels.dtype!=np.uint16 or labels.shape!=applied.shape):
        raise ValueError('junction_region_contract')
    validate_resize(*applied.shape,1.)
    if np.any(applied&(labels==0)):raise ValueError('junction_region_permission')
    ids=np.unique(labels[applied])
    if len(ids)>256:raise ValueError('junction_region_count')
    result=generated.copy();rows=[];total=0
    for rid,sl in enumerate(ndimage.find_objects(labels),1):
        if sl is None or rid not in ids:continue
        parts,count=ndimage.label(applied[sl]&(labels[sl]==rid));total+=count
        if total>256:raise ValueError('junction_region_count')
        for part,box in enumerate(ndimage.find_objects(parts),1):
            local=parts[box]==part;row=dict(region_id=rid,part=part)
            if local.size>MAX_CROP_PIXELS or int(local.sum())>MAX_PERMISSION_PIXELS:
                rows.append(row|dict(applied=False,reason='size_limit_previous_retained'));continue
            _,_,_,_,width,_=geometry(local);radius=2*max(16.,.06*width)
            if radius>256.:
                rows.append(row|dict(applied=False,reason='extent_limit_previous_retained'));continue
            pad=int(np.ceil(radius*1.55+4))
            y0,x0=sl[0].start+box[0].start,sl[1].start+box[1].start
            y1,x1=y0+local.shape[0],x0+local.shape[1]
            cy0,cx0=max(0,y0-pad),max(0,x0-pad)
            cy1,cx1=min(applied.shape[0],y1+pad),min(applied.shape[1],x1+pad)
            if (cy1-cy0)*(cx1-cx0)>MAX_CROP_PIXELS:
                rows.append(row|dict(applied=False,reason='context_limit_previous_retained'));continue
            permission=np.zeros((cy1-cy0,cx1-cx0),bool)
            permission[y0-cy0:y1-cy0,x0-cx0:x1-cx0]=local
            crop,meta=refine(source[cy0:cy1,cx0:cx1],generated[cy0:cy1,cx0:cx1],permission,width)
            if meta['applied']:
                from photo_synthetic_residual_audit_v1 import inspect_region
                before=inspect_region(source[cy0:cy1,cx0:cx1],generated[cy0:cy1,cx0:cx1],permission)
                after=inspect_region(source[cy0:cy1,cx0:cx1],crop,permission)
                flagged=lambda a:{tuple(w['bbox']) for w in a['windows'] if w['copy_review_flag']}
                new_flags=flagged(after)-flagged(before)
                meta['residual_review_guard']=dict(before_flags=before['review_flags'],candidate_flags=after['review_flags'],
                    new_flag_windows=len(new_flags),privacy_validated=False)
                if new_flags:
                    crop=generated[cy0:cy1,cx0:cx1].copy()
                    meta.update(applied=False,reason='new_residual_review_warning_previous_retained',changed_pixels=0)
            result[cy0:cy1,cx0:cx1][permission]=crop[permission];rows.append(row|meta)
    return result,dict(version=VERSION,regions=rows,corrected_components=sum(r['applied'] for r in rows),
        permission_geometry_changed=False,default_promoted=False,privacy_validated=False)


def refine_complete(source,v19,applied,labels):
    from photo_skin_seam_v22 import refine_complete as previous
    intermediate,v22=previous(source,v19,applied,labels)
    result,junction=refine_regions(source,intermediate,applied,labels)
    return result,dict(version=VERSION,previous=v22,junction=junction,
        permission_geometry_changed=False,default_promoted=False,privacy_validated=False)
