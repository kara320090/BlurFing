"""V19: opt-in irregular generated ridges and bounded skin contour continuation."""
import cv2
import numpy as np
from scipy import ndimage
from photo_synthetic_replacement_v10 import render_core,sample_style
from photo_synthetic_replacement_v13 import coupled_material
from photo_synthetic_replacement_v17 import photographic_skin,photographic_light
from photo_synthetic_replacement_v16 import organic_profile
from photo_synthetic_replacement_v15 import pore_height,quiet_micro
from photo_synthetic_replacement_v12 import boundary_ribbon
from photo_synthetic_replacement_v5 import independent_variation
from photographic_ridge_field_v3 import independent_photographic_field
from photo_organic_surface_v19 import interrupted_profile,contour_continuation
from photo_native_texture_stats_v1 import observe,missing_gains,equalize_generated
from photo_synthetic_replacement_v2 import geometry
from photo_synthetic_replacement_v6 import smoothstep
from photo_rejection_resolution_v1 import pixel_hash

MAX_REUSED_BASE_BYTES = 64 * 1024 * 1024

def organic_ridges(gu,gv,width,length,seed):
    rng=np.random.default_rng(seed ^ 0xAB100)
    scale=min(1.,480/max(width,length))
    pitch=float(np.clip(width*scale/rng.uniform(48.,65.),4.,12.))
    y,x=np.mgrid[:512,:512]
    mask=(abs(x-255.5)<=max(4.,width*scale*.5)) & (abs(y-255.5)<=max(4.,length*scale*.5))
    field,recipe=independent_photographic_field(mask,pitch,seed)
    field,contrast,warp=independent_variation(field,pitch,seed)
    profile,profile_meta=organic_profile(field,pitch,seed)
    profile,irregular=interrupted_profile(profile,mask,pitch,seed)
    pu=np.arcsin(np.clip(gu*.94,-.94,.94))/np.arcsin(.94);pv=gv*(1+.08*gu*gu)
    coords=np.array([255.5+pv*length*.5*scale,255.5+pu*width*.5*scale])
    ridge=ndimage.map_coordinates(profile,coords,order=3,mode='nearest',prefilter=True)
    modulation=ndimage.map_coordinates(contrast,coords,order=1,mode='nearest',prefilter=False)
    native_pitch=pitch/scale;latent_scale=min(1.,1536/max(width,length))
    pores,pore_meta=pore_height(ridge,max(2.,native_pitch*latent_scale),seed)
    return ridge+.42*pores,modulation,native_pitch,dict(pattern=recipe['pattern'],field_recipe=recipe,
        profile_recipe=profile_meta,variation=warp,pores=pore_meta,irregularity=irregular,
        synthetic_pitch_pixels=native_pitch,pitch_is_measured=False,
        source_orientation_transferred=False,source_ridge_phase_transferred=False)


def render(rgb,mask,labels,*,seed=None,generated_style=None):
    prepared={};bases=[];cached_bytes=0
    def prepare(pixels,u,v,width,length):
        base,meta=photographic_skin(pixels,u,v,width,length)
        prepared['curves']=meta['macro_creases']['curves']
        return base,meta
    def shade(local,u,v,width,length,child,stats,base):
        actual=stats if generated_style is None else generated_style(child,stats.copy())
        if (not isinstance(actual,np.ndarray) or actual.shape!=stats.shape or
                not np.isfinite(actual).all() or np.any(actual<0) or np.any(actual>16)):
            raise ValueError('generated_style_summary_contract')
        return coupled_material(local,u,v,width,length,child,actual,base,prepared['curves'],
            ridge_fn=organic_ridges,micro_fn=quiet_micro,light_fn=photographic_light)
    def boundary(base,pixels,u,v,width,length,local):
        nonlocal cached_bytes
        base,detail=boundary_ribbon(base,pixels,u,v,width,length,local)
        # Keep only this invocation's already computed field. A bounded cache
        # avoids recomputing the same fit during band completion.
        if cached_bytes+base.nbytes<=MAX_REUSED_BASE_BYTES:
            bases.append(base.copy());cached_bytes+=base.nbytes
        else:
            bases.append(None)
        return base,detail
    result,meta=render_core(rgb,mask,labels,seed=seed,version='v19',base_fn=prepare,
        boundary_fn=boundary,material_fn=shade)
    meta['macro_crease_count']=sum(len(r['color_field']['macro_creases']['curves']) for r in meta['regions'])
    for index,region in enumerate(meta['regions']):
        target=labels==region['region_id'];y,x,u,v,width,length=geometry(target)
        local=target[y.min():y.max()+1,x.min():x.max()+1]
        wanted,style=observe(rgb[target],local,u,v,width,length)
        existing,_=observe(result[target],local,u,v,width,length)
        gains=missing_gains(wanted,existing)
        base=bases[index];bases[index]=None
        if base is None:
            base,_=photographic_skin(rgb[target],u,v,width,length)
            base,_=boundary_ribbon(base,rgb[target],u,v,width,length,local)
        generated=(result[target].astype(float)-base) @ np.array([.299,.587,.114])
        detail=equalize_generated(generated,local,u,v,gains)
        limit=4*np.linalg.norm(sample_style(wanted,u,v),axis=1)
        distance=ndimage.distance_transform_edt(np.pad(local,1))[1:-1,1:-1][local]
        fade=smoothstep((distance-1)/max(2.,.006*width))
        values=result[target].astype(float)+np.clip(detail,-limit,limit)[:,None]*fade[:,None]
        values,edge=contour_continuation(values,rgb[target],local,width)
        result[target]=np.clip(np.floor(values+.5),0,255).astype(np.uint8)
        after,_=observe(result[target],local,u,v,width,length)
        region['legacy_texture_style']=region['texture_style'];region['texture_style']=style
        region['camera_band_completion']=dict(method='bounded_generated_material_band_equalization',
            target=wanted.tolist(),before=existing.tolist(),after=after.tolist(),gains=gains.tolist(),
            source_filtered_pixels_used=False,maximum_additional_gain_per_band=2.,
            source_phase_transferred=False,measurement_after_RGB8_quantization=True)
        region['contour_continuation']=edge
    meta['source_dependency']+='_and_bounded_macro_curves_native_band_contrast_and_guarded_inside_contour_RGB_means'
    meta['version']='opaque_skin_material_v19_experimental'
    meta['output_RGB_sha256']=pixel_hash(result)
    meta['actual_changed_pixels']=int(np.any(result!=rgb,axis=2).sum())
    if not np.array_equal(result[~mask],rgb[~mask]):raise RuntimeError('synthetic_outside_mask_modified')
    return result,meta
