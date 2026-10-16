"""Opaque independent ridges with bounded macro-crease descriptors.

Only unordered color summaries enter appearance reconstruction. Macro crease
positions are additional source-dependent appearance information, not a privacy
proof. No source high-pass, ridge orientation, minutiae or raw feather is used.
"""
import secrets
import cv2
import numpy as np
from scipy import ndimage, signal
from photo_resize_safety_v1 import validate_resize
from photo_rejection_resolution_v1 import pixel_hash
from photo_synthetic_replacement_v2 import geometry, color_cells
from photo_synthetic_replacement_v4 import local_appearance, boundary_geometry, boundary_appearance, source_groups
from photographic_ridge_field_v3 import independent_photographic_field
from organic_ridge_profile import render_photographic_profile, smooth_random
from independent_skin_relief import independent_skin_relief

VERSION='opaque_variable_ridges_macro_creases_v5_experimental'
MAX_REGIONS=256
MAX_REGION_PIXELS=4*1024*1024
MAX_BOUNDING_PIXELS=8*1024*1024


def macro_cells(u,v,width,length):
    nx=min(12,max(1,int(width)//48));ny=min(48,max(1,int(length)//16))
    bx=np.clip(((u+1)*nx/2).astype(int),0,nx-1)
    by=np.clip(((v+1)*ny/2).astype(int),0,ny-1)
    return by*nx+bx,nx,ny


def appearance_groups(u,v,width,length,distance,sector):
    """Exact geometry-only partition for V5's source permutation contract."""
    coarse,_,_=color_cells(u,v,width,length)
    macro,nx,ny=macro_cells(u,v,width,length)
    return source_groups(coarse,distance,width,sector)*(nx*ny)+macro


def macro_creases(pixels,base,u,v,width,length):
    """Fit <=3 long transverse quadratic grooves to coarse median residuals.

    Small/local valleys and unsupported extrapolation do not become creases.
    The fitted output contains only curve, width and depth parameters, not a
    downsampled source image. Thresholds here belong to this appearance-only
    version; frozen detector/pitch/feature gates are not involved.
    """
    cells,nx,ny=macro_cells(u,v,width,length)
    meta=dict(method='coarse_median_residual_quadratic_macro_creases',grid=[nx,ny],
        maximum_source_statistics=nx*ny*3,minimum_cell_support=24,
        source_high_frequency_transferred=False,original_pixel_alpha=0.,curves=[])
    if nx<4 or ny<10:
        return np.zeros(len(u)),np.zeros(len(u)),meta|dict(reason='insufficient_macro_geometry')
    values=np.full((ny,nx),np.nan);positions=np.zeros((ny,nx,2));valid=np.zeros((ny,nx),bool)
    weights=np.array([.299,.587,.114])
    for cell in np.unique(cells):
        take=cells==cell
        if take.sum()<24:continue
        row,col=divmod(int(cell),nx)
        values[row,col]=(np.median(pixels[take],axis=0)-np.median(base[take],axis=0))@weights
        positions[row,col]=[u[take].mean(),v[take].mean()];valid[row,col]=True
    if not valid.any():return np.zeros(len(u)),np.zeros(len(u)),meta|dict(reason='no_macro_support')
    # Fill missing cells for bounded smoothing, never count these as evidence.
    nearest=ndimage.distance_transform_edt(~valid,return_distances=False,return_indices=True)
    filled=values[tuple(nearest)]
    smooth=ndimage.gaussian_filter(filled,(.65,.6),mode='nearest')
    central=(np.arange(nx)+.5)/nx
    cols=(central>=.15)&(central<=.85)
    row_support=valid[:,cols].sum(axis=1)
    response=-np.median(smooth[:,cols],axis=1)
    response[row_support<max(2,int(cols.sum()*.5))]=0
    min_width=max(1.5,.035*ny)
    peaks,properties=signal.find_peaks(response,prominence=2.,width=min_width,distance=max(3,round(ny*.10)))
    correction=np.zeros(len(u));crease_strength=np.zeros(len(u))
    chosen=sorted(range(len(peaks)),key=lambda i:(-float(properties['prominences'][i]),int(peaks[i])))[:3]
    for index in chosen:
        row=int(peaks[index]);half=max(2,int(np.ceil(properties['widths'][index]*.6)))
        support=[]
        for col in range(nx):
            start=max(0,row-half);stop=min(ny,row+half+1)
            candidates=np.arange(start,stop);candidates=candidates[valid[candidates,col]]
            if not len(candidates):continue
            found=int(candidates[np.argmin(smooth[candidates,col])])
            depth=-float(smooth[found,col])
            if depth<2.:continue
            support.append((positions[found,col,0],positions[found,col,1],depth))
        if len(support)<max(4,int(np.ceil(nx*.5))):continue
        samples=np.array(support);xs,ys,depths=samples.T
        if np.ptp(xs)<.9:continue
        design=np.column_stack((np.ones(len(xs)),xs,xs*xs))
        coefficient=np.linalg.lstsq(design,ys,rcond=None)[0]
        residual=np.abs(design@coefficient-ys)
        if np.median(residual)>2.5/ny or np.max(residual)>5./ny:continue
        sigma=float(np.clip(properties['widths'][index]/ny/1.1775,.035,.16))
        # Residual already excludes the broad V4 shading; avoid double counting.
        depth=float(np.clip(np.median(depths),0,28.))
        center=coefficient[0]+coefficient[1]*u+coefficient[2]*u*u
        offset=(v-center)/sigma
        support_fade=np.clip((u-xs.min()+.15)/.15,0,1)*np.clip((xs.max()+.15-u)/.15,0,1)
        broad=np.exp(-.5*offset*offset)
        narrow=np.exp(-.5*(offset/.32)**2)
        shoulder=np.exp(-.5*((offset-.6)/.45)**2)
        groove=(-depth*(.72*broad+.28*narrow)+.12*depth*shoulder)*support_fade
        correction+=groove
        crease_strength=np.maximum(crease_strength,broad*support_fade*np.clip(depth/8.,0,1))
        meta['curves'].append(dict(quadratic_v_from_u=coefficient.tolist(),sigma_v=sigma,
            depth_RGB=depth,supported_u=[float(xs.min()),float(xs.max())],support_columns=len(xs),
            median_fit_residual_v=float(np.median(residual)),source_pixel_residual_transferred=False))
    return np.clip(correction,-32,4),crease_strength,meta


def independent_variation(field,pitch,seed):
    """Smooth bounded coordinate deformation and width bias; no source input."""
    rng=np.random.default_rng(seed ^ 0x5B15)
    dy=smooth_random(field.shape,7,pitch*1.5,rng)*pitch*.8
    dx=smooth_random(field.shape,7,pitch*1.5,rng)*pitch*.8
    dy_y,dy_x=np.gradient(dy);dx_y,dx_x=np.gradient(dx)
    # Bound the Jacobian's displacement Frobenius norm: singular values of the
    # mapping remain >=.72, preventing a folded/reversed coordinate map.
    norm=np.sqrt(dy_y*dy_y+dy_x*dy_x+dx_y*dx_y+dx_x*dx_x)
    factor=min(1.,.28/max(float(norm.max()),1e-6));dy*=factor;dx*=factor
    yy,xx=np.mgrid[:field.shape[0],:field.shape[1]]
    warped=ndimage.map_coordinates(field,[yy+dy,xx+dx],order=1,mode='reflect',prefilter=False)
    bias=smooth_random(field.shape,15,max(1.,pitch*.75),rng)*.16
    contrast=np.clip(.65+.24*smooth_random(field.shape,9,pitch*1.2,rng),.22,1.10)
    return (warped+bias).astype(np.float32),contrast,dict(
        method='independent_smooth_coordinate_warp_width_bias_and_contrast',
        displacement_gradient_bound=float(norm.max()*factor),mapping_minimum_singular_value_bound=.72,
        displacement_canonical_range=[float(min(dx.min(),dy.min())),float(max(dx.max(),dy.max()))],
        contrast_range=[float(contrast.min()),float(contrast.max())],contrast_std=float(contrast.std()),
        original_pixels_input=False)


def variable_relief(local,u,v,width,length,seed):
    scale=480/max(width,length);yy,xx=np.nonzero(local)
    positions=np.column_stack((xx,yy)).astype(np.float64);centered=positions-positions.mean(axis=0)
    _,vectors=np.linalg.eigh(centered.T@centered/len(positions));axis=vectors[:,-1]
    if axis[np.argmax(np.abs(axis))]<0:axis=-axis
    rotation=np.stack(([-axis[1],axis[0]],axis));projected=positions@rotation.T
    midpoint=(projected.min(axis=0)+projected.max(axis=0))/2
    affine=np.column_stack((rotation*scale,255.5-midpoint*scale))
    canonical=cv2.warpAffine(local.astype(np.uint8),affine,(512,512),flags=cv2.INTER_NEAREST,
        borderMode=cv2.BORDER_CONSTANT,borderValue=0)>0
    rng=np.random.default_rng(seed);pitch=float(np.clip(width*scale/rng.uniform(34.,42.),4.,16.))
    coordinates=np.vstack((255.5+v*length*.5*scale,255.5+u*width*.5*scale))
    if len(u)<32 or width<4 or canonical.sum()<32 or width*scale<8:
        return rng.normal(0.,.45,len(u)),dict(synthetic_pattern='unresolved_tiny_region',
            fingerprint_texture_resolved=False,synthetic_pitch_pixels=pitch/scale,canonical_scale=scale)
    field,recipe=independent_photographic_field(canonical,pitch,seed)
    field,contrast,variation=independent_variation(field,pitch,seed)
    profile,profile_recipe=render_photographic_profile(field,canonical,pitch,seed)
    surface,skin_recipe=independent_skin_relief(canonical,pitch,seed)
    gy,gx=np.gradient(profile);light=rng.uniform(0,2*np.pi)
    slope=(gx*np.cos(light)+gy*np.sin(light))*pitch/(2*np.pi)
    relief=(3.0*profile+.9*slope)*contrast+1.0*surface
    values=ndimage.map_coordinates(relief,coordinates,order=1,mode='nearest',prefilter=False)
    distance=ndimage.distance_transform_edt(np.pad(local,1))[1:-1,1:-1][local]
    values*=np.clip(distance/max(2.,.012*width),0,1)
    return values,dict(synthetic_pattern=recipe['pattern'],fingerprint_texture_resolved=True,
        canonical_scale=scale,canonical_shape=[512,512],aspect_ratio_preserved=True,
        synthetic_pitch_canonical=pitch,synthetic_pitch_pixels=pitch/scale,
        field_recipe=recipe,profile_recipe=profile_recipe,skin_recipe=skin_recipe,variation=variation,
        relief_RMS=float(values.std()),original_intensities_used_by_relief=False)


def render(rgb,mask,labels,*,seed=None):
    if not isinstance(rgb,np.ndarray) or rgb.dtype!=np.uint8 or rgb.ndim!=3 or rgb.shape[2]!=3:
        raise ValueError('synthetic_RGB_uint8_required')
    validate_resize(*rgb.shape[:2],1.)
    if (not isinstance(mask,np.ndarray) or mask.dtype!=np.bool_ or mask.shape!=rgb.shape[:2] or
        not isinstance(labels,np.ndarray) or labels.dtype!=np.uint16 or labels.shape!=mask.shape or
        not np.array_equal(labels>0,mask)):raise ValueError('synthetic_mask_partition_contract')
    if seed is None:seed=secrets.randbits(128)
    if type(seed) is not int or not 0<=seed<2**128:raise ValueError('synthetic_seed_unsigned_128bit_required')
    ids=np.unique(labels[mask])
    if len(ids)>MAX_REGIONS:raise ValueError('synthetic_region_resource_limit')
    out=rgb.copy();regions=[]
    for rid in ids:
        target=labels==rid
        if target.sum()>MAX_REGION_PIXELS:raise ValueError('synthetic_region_pixel_limit')
        yy,xx,u,v,width,length=geometry(target)
        local=target[yy.min():yy.max()+1,xx.min():xx.max()+1]
        if local.size>MAX_BOUNDING_PIXELS:raise ValueError('synthetic_region_bbox_pixel_limit')
        if ndimage.label(local)[1]!=1:raise ValueError('synthetic_region_must_be_connected')
        pixels=rgb[target];base,gain,color=local_appearance(pixels,u,v,width,length)
        correction,crease_strength,creases=macro_creases(pixels,base,u,v,width,length)
        distance,sector=boundary_geometry(local)
        base,boundary=boundary_appearance(base+correction[:,None],pixels,u,v,width,length,distance,sector)
        child_seed=int(np.random.SeedSequence([seed,int(rid)]).generate_state(1,dtype=np.uint64)[0])
        relief,texture=variable_relief(local,u,v,width,length,child_seed)
        grain=np.random.default_rng(child_seed ^ 0xE041).normal(0.,.65,len(u))
        values=base+(gain*(1-.55*crease_strength)*relief+grain)[:,None]
        out[target]=np.clip(np.floor(values+.5),0,255).astype(np.uint8)
        regions.append(dict(region_id=int(rid),pixels=int(target.sum()),geometric_width_pixels=width,
            color_field=color,boundary_color=boundary,macro_creases=creases,**texture,
            pitch_is_measured=False,source_ridge_phase_used=False,original_pixel_residual_used=False,
            mask_sha256=pixel_hash(target)))
    if not np.array_equal(out[~mask],rgb[~mask]):raise RuntimeError('synthetic_outside_mask_modified')
    return out,dict(version=VERSION,seed=seed,regions=regions,
        status='synthetic_replacement_applied' if mask.any() else 'no_replacement_regions',
        replacement_regions=len(regions),replaced_pixels=int(mask.sum()),
        macro_crease_count=sum(len(r['macro_creases']['curves']) for r in regions),
        unresolved_texture_regions=sum(not r['fingerprint_texture_resolved'] for r in regions),
        actual_changed_pixels=int(np.any(out!=rgb,axis=2).sum()),
        source_dependency='V4_coarse_color_and_boundary_statistics_plus_macro_cell_RGB_medians_for_parametric_creases',
        source_permutation_partition='V4_partition_intersected_with_macro_color_cells',
        coarse_spatial_color_preserved=True,original_pixel_residual_used=False,
        source_alpha_inside_mask=0.,edge_source_feathering=False,original_pitch_required=False,
        outside_mask_RGB_preserved=True,output_RGB_sha256=pixel_hash(out),mask_sha256=pixel_hash(mask),
        full_photo_protection_verified=False,privacy_validated=False,biometric_validation_performed=False,
        natural_appearance_validated=False,production_approved=False)
