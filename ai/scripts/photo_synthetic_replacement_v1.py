"""Opaque procedural fingerprint-like replacement, separate from native v4.

No ridge positions, pitch, minutiae, or spatial RGB texture are read from the
source. Each connected region supplies only one median RGB color. Geometry is
from its permission mask. The independently seeded texture replaces ALL mask
pixels, including edges; no source alpha blending or source noise is used.
This is an experimental texture redaction, not biometric validation.
"""
import secrets
import numpy as np
from scipy import ndimage
from photo_resize_safety_v1 import validate_resize
from photo_rejection_resolution_v1 import pixel_hash

VERSION = 'opaque_synthetic_fingerprint_replacement_v1_experimental'
MAX_REGIONS = 256
MAX_REGION_PIXELS = 4*1024*1024


def render(rgb, mask, labels, *, seed=None):
    if (not isinstance(rgb, np.ndarray) or rgb.dtype != np.uint8 or
            rgb.ndim != 3 or rgb.shape[2] != 3):
        raise ValueError('synthetic_RGB_uint8_required')
    validate_resize(*rgb.shape[:2], 1.)
    if (not isinstance(mask, np.ndarray) or mask.dtype != np.bool_ or
            mask.shape != rgb.shape[:2] or not isinstance(labels, np.ndarray) or
            labels.dtype != np.uint16 or labels.shape != mask.shape or
            not np.array_equal(labels > 0, mask)):
        raise ValueError('synthetic_mask_partition_contract')
    if seed is None:
        seed = secrets.randbits(128)
    if type(seed) is not int or not 0 <= seed < 2**128:
        raise ValueError('synthetic_seed_unsigned_128bit_required')
    ids = np.unique(labels[mask])
    if len(ids) > MAX_REGIONS:
        raise ValueError('synthetic_region_resource_limit')
    out = rgb.copy()
    regions = []
    for region_id in ids:
        target = labels == region_id
        if int(target.sum()) > MAX_REGION_PIXELS:
            raise ValueError('synthetic_region_pixel_limit')
        yy, xx = np.nonzero(target)
        y0, y1, x0, x1 = int(yy.min()), int(yy.max())+1, int(xx.min()), int(xx.max())+1
        local = target[y0:y1, x0:x1]
        if ndimage.label(local)[1] != 1:
            raise ValueError('synthetic_region_must_be_connected')
        # PCA uses MASK coordinates only. Deterministic sign resolves its axis.
        points = np.column_stack((xx, yy)).astype(np.float64)
        center = points.mean(axis=0)
        centered = points-center
        covariance = centered.T @ centered / len(points)
        _, vectors = np.linalg.eigh(covariance)
        axis = vectors[:, -1]
        if axis[np.argmax(np.abs(axis))] < 0:
            axis = -axis
        normal = np.array([-axis[1], axis[0]])
        across, along = centered @ normal, centered @ axis
        width = max(1., float(np.ptp(across))+1.)
        length = max(1., float(np.ptp(along))+1.)
        # Per-label seed means enumeration order never consumes another seed.
        rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence([seed, int(region_id)])))
        u, v = across/width, along/width
        angle = rng.uniform(-.2, .2)
        u, v = u*np.cos(angle)-v*np.sin(angle), u*np.sin(angle)+v*np.cos(angle)
        core_u = rng.uniform(-.12, .12)
        core_v = rng.uniform(-.12, .12)
        aspect = rng.uniform(.7, 1.05)
        # Chosen from mask geometry, never from observed original ridge spacing.
        pitch = max(4., width/rng.uniform(28., 38.))
        radius = np.sqrt((u-core_u)**2 + ((v-core_v)*aspect)**2 + .0004)
        warp = .035*np.sin(4.*u+3.*v+rng.uniform(0, 2*np.pi))
        phase = 2*np.pi*(radius+warp)*width/pitch+rng.uniform(0, 2*np.pi)
        relief = 1.9*np.sin(phase)+.65*np.sin(2*phase+.3)
        # All shading/noise is synthetic. Only these three median values depend
        # on source RGB; permuting its region pixels leaves output unchanged.
        color = np.median(rgb[target], axis=0).astype(np.float64)
        shade = 2.8*(.2-u*u)-1.5*v/max(1., length/width)
        micro = rng.normal(0., .18, len(points))
        values = color[None, :] + (shade+relief+micro)[:, None]
        out[target] = np.clip(np.floor(values+.5), 0, 255).astype(np.uint8)
        regions.append(dict(region_id=int(region_id), pixels=int(target.sum()),
            color_median_RGB=color.tolist(), geometric_width_pixels=width,
            synthetic_pitch_pixels=float(pitch), pitch_is_measured=False,
            source_spatial_texture_used=False, mask_sha256=pixel_hash(target)))
    if not np.array_equal(out[~mask], rgb[~mask]):
        raise RuntimeError('synthetic_outside_mask_modified')
    return out, dict(version=VERSION, seed=seed, regions=regions,
        status='synthetic_replacement_applied' if mask.any() else 'no_replacement_regions',
        replacement_regions=len(regions), replaced_pixels=int(mask.sum()),
        actual_changed_pixels=int(np.any(out != rgb, axis=2).sum()),
        source_dependency='three_median_RGB_values_per_region_only',
        original_spatial_texture_used=False, source_alpha_inside_mask=0.,
        edge_source_feathering=False, original_pitch_required=False,
        outside_mask_RGB_preserved=True, output_RGB_sha256=pixel_hash(out),
        mask_sha256=pixel_hash(mask), full_photo_protection_verified=False,
        privacy_validated=False, biometric_validation_performed=False,
        natural_appearance_validated=False, production_approved=False)
