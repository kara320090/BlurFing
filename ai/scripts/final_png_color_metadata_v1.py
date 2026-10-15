"""Final desktop PNG metadata only; model inputs and RGB samples stay unchanged.

An original RGB/RGBA source's valid RGB ICC bytes remain attached to its final
RGB PNG. This does not convert color samples or extend support to grey/CMYK
profiles. HTTP canonical inputs carry no profiles and retain the old encoding.
"""
import hashlib,io
from pathlib import Path
import numpy as np
from PIL import Image,ImageCms
from pad_refinement_data_contract_v2 import digest
from photo_resize_safety_v1 import validate_resize


def _source_metadata(source,expected_sha256):
    source=Path(source)
    if digest(source)!=expected_sha256:raise ValueError('final_PNG_source_hash_mismatch')
    with Image.open(source) as image:
        mode=image.mode;shape=(image.height,image.width);orientation=image.getexif().get(274,1)
        icc=image.info.get('icc_profile')
    if digest(source)!=expected_sha256:raise ValueError('final_PNG_source_hash_mismatch')
    if icc is not None:
        if mode not in ('RGB','RGBA'):raise ValueError('source_ICC_to_final_RGB_mode_not_supported')
        if (not isinstance(icc,bytes) or len(icc)<132 or int.from_bytes(icc[:4],'big')!=len(icc) or
                icc[36:40]!=b'acsp'):raise ValueError('invalid_source_RGB_ICC_profile')
        if icc[16:20]!=b'RGB ' or icc[20:24] not in (b'XYZ ',b'Lab '):
            raise ValueError('source_ICC_to_final_RGB_colorspace_not_supported')
        try:
            profile=ImageCms.ImageCmsProfile(io.BytesIO(icc))
            if profile.profile.xcolor_space.strip()!='RGB':raise ValueError('ICC is not RGB')
            # Validate that this is an actual usable RGB source profile. Build
            # only; never apply a transform to source/model/returned samples.
            ImageCms.buildTransform(profile,ImageCms.createProfile('sRGB'),'RGB','RGB',renderingIntent=1)
        except Exception as error:raise ValueError('invalid_or_unsupported_source_RGB_ICC_profile') from error
    return mode,shape,orientation,icc


def save_final_rgb_png(source,expected_source_sha256,returned,target,orientation):
    """Write one fresh final PNG, preserving valid original RGB ICC bytes only."""
    target=Path(target)
    if target.exists() or target.is_symlink():raise FileExistsError('fresh_final_PNG_required')
    if (not isinstance(returned,np.ndarray) or returned.dtype!=np.uint8 or returned.ndim!=3 or returned.shape[2]!=3):
        raise ValueError('final_PNG_RGB_uint8_required')
    validate_resize(returned.shape[0],returned.shape[1],1.)
    mode,shape,actual_orientation,icc=_source_metadata(source,expected_source_sha256)
    if (returned.shape[:2]!=shape or type(orientation)is not int or orientation not in range(1,9) or actual_orientation!=orientation):
        raise ValueError('final_PNG_shape_or_EXIF_binding_mismatch')
    before=hashlib.sha256(returned.tobytes()).hexdigest();exif=Image.Exif();exif[274]=orientation
    options=dict(exif=exif)
    if icc is not None:options['icc_profile']=icc
    created=False
    try:
        with target.open('xb') as stream:
            created=True;Image.fromarray(returned).save(stream,format='PNG',**options)
        with Image.open(target) as image:
            if (image.format!='PNG' or image.mode!='RGB' or image.size!=shape[::-1] or image.getexif().get(274,1)!=orientation or
                    image.info.get('icc_profile')!=icc or not np.array_equal(np.asarray(image),returned)):
                raise ValueError('final_PNG_RGB_EXIF_ICC_roundtrip_mismatch')
        if digest(source)!=expected_source_sha256:raise ValueError('final_PNG_source_hash_mismatch')
        if hashlib.sha256(returned.tobytes()).hexdigest()!=before:raise ValueError('final_PNG_returned_RGB_changed')
    except Exception:
        if created:target.unlink(missing_ok=True)
        raise
    icc_sha=hashlib.sha256(icc).hexdigest()if icc is not None else None
    return dict(final_png_color_policy='original_RGB_ICC_bytes_preserved_without_color_conversion',
        source_ICC_present=icc is not None,source_ICC_profile_sha256=icc_sha,returned_ICC_profile_sha256=icc_sha,
        source_ICC_mode=mode if icc is not None else None,returned_RGB_color_samples_converted=False,
        model_canonical_inputs_unchanged=True)
