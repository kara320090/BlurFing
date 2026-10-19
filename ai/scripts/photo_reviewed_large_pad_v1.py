"""Bounded, explicit working-resolution V19 adapter for oversized reviewed pads.

Native compositing permission is unchanged. Area-normalized source colors and
generated-only normalized upsampling exclude outside-mask RGB. This path is an
appearance fallback, not native-resolution texture or privacy validation.
"""
import cv2
import hashlib
import numpy as np
from scipy import ndimage
from photo_resize_safety_v1 import validate_resize
from photo_synthetic_replacement_v10 import MAX_REGION_PIXELS, MAX_BOUNDING_PIXELS


def working_shape(height, width):
    validate_resize(height, width, 1.)
    divisor = 1
    while ((height + divisor - 1)//divisor)*((width + divisor - 1)//divisor) > min(MAX_REGION_PIXELS, MAX_BOUNDING_PIXELS):
        divisor *= 2
    return ((height + divisor - 1)//divisor, (width + divisor - 1)//divisor), divisor


def normalized_resize(values, support, shape):
    """Only permitted samples participate, including at interpolation edges."""
    interpolation = cv2.INTER_AREA if shape[0] <= support.shape[0] and shape[1] <= support.shape[1] else cv2.INTER_LINEAR
    weights = support.astype(np.float32)
    denominator = cv2.resize(weights, (shape[1], shape[0]), interpolation=interpolation)
    numerator = cv2.resize(values.astype(np.float32)*weights[..., None], (shape[1], shape[0]), interpolation=interpolation)
    resized = numerator/np.maximum(denominator[..., None], np.finfo(np.float32).tiny)
    return np.clip(np.floor(resized + .5), 0, 255).astype(np.uint8), denominator


def render_large_pad(rgb, target, rid, seed, render_fn):
    if (rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3 or
            target.dtype != np.bool_ or target.shape != rgb.shape[:2]):
        raise ValueError('large_pad_RGB_mask_contract')
    validate_resize(*target.shape, 1.)
    yy, xx = np.nonzero(target)
    if not len(xx): raise ValueError('large_pad_empty')
    y0,y1,x0,x1=int(yy.min()),int(yy.max())+1,int(xx.min()),int(xx.max())+1
    local=target[y0:y1,x0:x1];source=rgb[y0:y1,x0:x1]
    shape,divisor=working_shape(*local.shape)
    if divisor == 1: raise ValueError('large_pad_adapter_requires_oversized_region')
    working,coverage=normalized_resize(source,local,shape);mask=coverage>0
    if ndimage.label(mask)[1] != 1: raise ValueError('large_pad_working_component_contract')
    labels=np.where(mask,rid,0).astype(np.uint16)
    before=working.copy()
    generated,meta=render_fn(working,mask,labels,seed=seed)
    if (generated.shape != working.shape or generated.dtype != np.uint8 or
            not np.array_equal(before,working) or not np.array_equal(generated[~mask],working[~mask]) or
            len(meta['regions']) != 1 or meta['regions'][0]['region_id'] != rid):
        raise RuntimeError('large_pad_renderer_contract')
    upsampled,generated_coverage=normalized_resize(generated,mask,local.shape)
    if not np.all(generated_coverage[local]>0): raise RuntimeError('large_pad_generated_coverage_gap')
    result=dict(meta['regions'][0])
    result['working_pixels']=result['pixels'];result['pixels']=int(local.sum())
    result['native_mask_sha256']=hashlib.sha256(np.ascontiguousarray(target).tobytes()).hexdigest()
    result['working_resolution_adapter']=dict(version='reviewed_large_pad_v1',
        native_bbox_xyxy=[x0,y0,x1,y1],native_crop_shape=list(local.shape),working_shape=list(shape),
        integer_reduction_divisor=divisor,actual_scale_xy=[shape[1]/local.shape[1],shape[0]/local.shape[0]],
        source_downsample='mask_normalized_INTER_AREA',generated_upsample='mask_normalized_INTER_LINEAR',
        outside_source_RGB_used=False,original_RGB_blended_back=False,native_mask_unchanged=True,
        renderer_geometry_and_texture_metadata_frame='working_pixels',native_texture_resolution_verified=False,
        privacy_validated=False)
    return (y0,y1,x0,x1),upsampled,result
