"""Lightweight native RGB decode; strict EXIF and unchanged source pixels."""
import hashlib
import numpy as np
from PIL import Image
from pad_refinement_data_contract_v2 import digest
from photo_resize_safety_v1 import validate_resize


def canonical_rgb(source):
    sha=digest(source)
    with Image.open(source) as image:
        validate_resize(image.height,image.width,1.)
        orientation=image.getexif().get(274,1);mode=image.mode
        if type(orientation) is not int or orientation not in range(1,9):raise ValueError('invalid_source_exif_orientation')
        if mode in ['RGB','L']:rgb=np.asarray(image.convert('RGB')).copy();alpha_policy='not_present'
        elif mode=='RGBA':
            rgba=np.asarray(image).astype(np.uint32);alpha=rgba[:,:,3:4]
            rgb=((rgba[:,:,:3]*alpha+255*(255-alpha)+127)//255).astype(np.uint8)
            alpha_policy='composite_over_opaque_white_integer_round_nearest'
        else:raise ValueError('unsupported_source_mode')
    if digest(source)!=sha:raise ValueError('frozen_run_inputs_or_code_changed')
    return rgb,dict(original_source_sha256=sha,source_mode=mode,source_exif_orientation=orientation,
        alpha_policy=alpha_policy,EXIF_transposed=False,coordinate_system='encoded_original_pixels',
        canonical_RGB_sha256=hashlib.sha256(rgb.tobytes()).hexdigest())


def source_diagnostic(source):
    """Header only, for private failure logs. Never dump EXIF personal fields."""
    with Image.open(source) as image:
        orientation=image.getexif().get(274,1)
        return dict(mode=image.mode,shape=[image.height,image.width],
            EXIF_orientation_repr=repr(orientation),EXIF_orientation_type=type(orientation).__name__,
            source_sha256=digest(source))
