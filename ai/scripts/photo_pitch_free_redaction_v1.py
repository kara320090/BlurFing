"""Explicit solid black redaction of a hash-bound mask; no inferred spacing.

Removing source RGB inside a supplied mask is a local pixel guarantee, not
evidence that the mask contains every fingerprint. Never an implicit fallback
for the appearance-preserving frozen renderer or an anatomical approval.
"""
import hashlib,re
import numpy as np
from photo_resize_safety_v1 import validate_resize

VERSION='solid_black_pitch_free_redaction_v1_experimental'


def pixel_hash(value):return hashlib.sha256(value.tobytes()).hexdigest()


def redact(rgb,mask,expected_RGB_sha256,expected_mask_sha256):
    if (not isinstance(rgb,np.ndarray) or rgb.dtype!=np.uint8 or rgb.ndim!=3 or rgb.shape[2]!=3 or min(rgb.shape[:2])<1 or
            not isinstance(mask,np.ndarray) or mask.dtype!=np.bool_ or mask.shape!=rgb.shape[:2]):
        raise ValueError('pitch_free_RGB_mask_contract')
    validate_resize(*mask.shape,1.)
    if any(not isinstance(value,str) or re.fullmatch('[0-9a-f]{64}',value) is None for value in [expected_RGB_sha256,expected_mask_sha256]):
        raise ValueError('pitch_free_hash_contract')
    if pixel_hash(rgb)!=expected_RGB_sha256 or pixel_hash(mask)!=expected_mask_sha256:
        raise ValueError('pitch_free_source_or_mask_hash_mismatch')
    output=rgb.copy();output[mask]=0
    if (not np.array_equal(output[~mask],rgb[~mask]) or np.any(output[mask]) or
            pixel_hash(rgb)!=expected_RGB_sha256 or pixel_hash(mask)!=expected_mask_sha256):
        raise RuntimeError('pitch_free_redaction_invariant_failure')
    return output,dict(version=VERSION,method='solid_black',status='redacted_unverified_scope' if mask.any() else 'no_mask_original_returned',
        provided_mask_pixels=int(mask.sum()),changed_RGB_pixels=int(np.any(output!=rgb,axis=2).sum()),
        input_RGB_sha256=expected_RGB_sha256,mask_pixel_sha256=expected_mask_sha256,returned_RGB_sha256=pixel_hash(output),
        source_RGB_removed_inside_provided_mask=True,RGB_outside_provided_mask_preserved=True,
        pitch_estimation_required=False,pitch_generated=False,frozen_renderer_used=False,
        anatomical_mask_coverage_verified=False,whole_photo_protection_verified=False,privacy_validated=False,
        default_pipeline_enabled=False)
