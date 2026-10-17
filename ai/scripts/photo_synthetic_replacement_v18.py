"""V18: restore missing camera-scale contrast in independently generated material.

V17 remains byte-for-byte preserved. This adds only a source-summary-driven
appearance layer, and does not declare biometric protection or naturalness.
"""
import numpy as np
from scipy import ndimage
from photo_synthetic_replacement_v17 import render as previous_render
from photo_synthetic_replacement_v2 import geometry
from photo_synthetic_replacement_v6 import smoothstep
from photo_native_texture_stats_v1 import observe,missing_gains,equalize_generated
from photo_synthetic_replacement_v17 import photographic_skin
from photo_synthetic_replacement_v12 import boundary_ribbon
from photo_rejection_resolution_v1 import pixel_hash
from photo_synthetic_replacement_v10 import sample_style


def render(rgb,mask,labels,*,seed=None):
    result,meta = previous_render(rgb,mask,labels,seed=seed)
    for region in meta['regions']:
        target = labels == region['region_id']
        y,x,u,v,width,length = geometry(target)
        local = target[y.min():y.max()+1,x.min():x.max()+1]
        wanted,source = observe(rgb[target],local,u,v,width,length)
        existing,_ = observe(result[target],local,u,v,width,length)
        gains = missing_gains(wanted,existing)
        # Reconstruct the same coarse base as V17, so the residual here is
        # generated material. It is not original RGB minus a low-pass source.
        base,_ = photographic_skin(rgb[target],u,v,width,length)
        base,_ = boundary_ribbon(base,rgb[target],u,v,width,length,local)
        generated = (result[target].astype(float)-base) @ np.array([.299,.587,.114])
        detail = equalize_generated(generated,local,u,v,gains)
        # Bound rare tails using only coarse contrast, with no original blend.
        limit = 4*np.linalg.norm(sample_style(wanted,u,v),axis=1)
        detail = np.clip(detail,-limit,limit)
        distance = ndimage.distance_transform_edt(np.pad(local,1))[1:-1,1:-1][local]
        fade = smoothstep((distance-1)/max(2.,.006*width))
        result[target] = np.clip(np.floor(result[target].astype(float)+detail[:,None]*fade[:,None]+.5),0,255).astype(np.uint8)
        after,_ = observe(result[target],local,u,v,width,length)
        region['legacy_texture_style'] = region['texture_style']
        region['texture_style'] = source
        region['camera_band_completion'] = dict(method='bounded_generated_material_band_equalization',
            target=wanted.tolist(),before=existing.tolist(),after=after.tolist(),gains=gains.tolist(),
            source_filtered_pixels_used=False,maximum_additional_gain_per_band=2.,
            source_phase_transferred=False,maximum_tail_contrast_multiple=4.,
            contrast_ratio_is_appearance_proxy=True,mask_geometry_changed=False,
            no_source_pixel_alpha=True,measurement_after_RGB8_quantization=True)
    meta['version'] = 'opaque_skin_material_v18_experimental'
    meta['source_dependency'] += '_and_native_pixel_band_contrast_summaries'
    meta['output_RGB_sha256'] = pixel_hash(result)
    meta['actual_changed_pixels'] = int(np.any(result != rgb,axis=2).sum())
    if not np.array_equal(result[~mask],rgb[~mask]): raise RuntimeError('synthetic_outside_mask_modified')
    return result,meta
