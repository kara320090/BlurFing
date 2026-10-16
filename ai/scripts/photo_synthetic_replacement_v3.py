"""Opaque photographic synthetic ridges with no original ridge-phase input.

Reuses independent field/profile generators, not the frozen transform's observed
pitch gate. All pitches below are synthesis parameters, never measurements.
Only V2's bounded coarse RGB statistics carry source appearance into the region.
"""
import secrets
import cv2
import numpy as np
from scipy import ndimage
from photo_resize_safety_v1 import validate_resize
from photo_rejection_resolution_v1 import pixel_hash
from photo_synthetic_replacement_v2 import geometry, color_field
from photographic_ridge_field_v3 import independent_photographic_field
from organic_ridge_profile import render_photographic_profile
from independent_skin_relief import independent_skin_relief

VERSION = 'opaque_photographic_synthetic_replacement_v3_experimental'
MAX_REGIONS = 256
MAX_REGION_PIXELS = 4*1024*1024
CANONICAL_SIZE = 512


def photographic_relief(local, u, v, width, length, seed):
    """Isotropic PCA frame; source intensities never enter this function.

    Generator buffers stay at 512 square, including the skin helper's 4x canvas.
    Mapping back samples only target pixels. It does not stretch a rectangle to
    a square or copy source pixels into a boundary feather.
    """
    scale = 480/max(width, length)
    yy, xx = np.nonzero(local)
    positions = np.column_stack((xx, yy)).astype(np.float64)
    centered = positions-positions.mean(axis=0)
    _, vectors = np.linalg.eigh(centered.T @ centered/len(positions))
    axis = vectors[:, -1]
    if axis[np.argmax(np.abs(axis))] < 0:
        axis = -axis
    rotation = np.stack(([-axis[1], axis[0]], axis))
    projected = positions @ rotation.T
    midpoint = (projected.min(axis=0)+projected.max(axis=0))/2
    affine = np.column_stack((rotation*scale, 255.5-midpoint*scale))
    canonical = cv2.warpAffine(local.astype(np.uint8), affine, (512, 512),
        flags=cv2.INTER_NEAREST, borderMode=cv2.BORDER_CONSTANT, borderValue=0) > 0
    rng = np.random.default_rng(seed)
    # Explicit independent design spacing, not an estimated or default source pitch.
    pitch = float(np.clip(width*scale/rng.uniform(34., 42.), 4., 16.))
    coordinates = np.vstack((255.5+v*length*.5*scale, 255.5+u*width*.5*scale))
    if len(u) < 32 or width < 4 or canonical.sum() < 32 or width*scale < 8:
        return rng.normal(0., .45, len(u)), dict(synthetic_pattern='unresolved_tiny_region',
            fingerprint_texture_resolved=False, canonical_scale=scale,
            synthetic_pitch_canonical=pitch, synthetic_pitch_pixels=pitch/scale)
    field, recipe = independent_photographic_field(canonical, pitch, seed)
    profile, profile_recipe = render_photographic_profile(field, canonical, pitch, seed)
    surface, skin_recipe = independent_skin_relief(canonical, pitch, seed)
    # Ridge cross-sections carry width/shoulder variation; weak directional
    # shading gives relief instead of the appearance of dark printed lines.
    gy, gx = np.gradient(profile)
    light = rng.uniform(0., 2*np.pi)
    slope = (gx*np.cos(light)+gy*np.sin(light))*pitch/(2*np.pi)
    relief = 3.4*profile+1.0*slope+.9*surface
    # Sampling beyond the canonical mask is unnecessary. Values at a mask edge
    # remain generated; only synthetic relief fades, never source alpha.
    values = ndimage.map_coordinates(relief, coordinates, order=1, mode='nearest', prefilter=False)
    distance = ndimage.distance_transform_edt(np.pad(local, 1))[1:-1, 1:-1][local]
    fade = np.clip(distance/max(2., .012*width), 0, 1)
    values = values*fade+rng.normal(0., .18, len(u))
    return values, dict(synthetic_pattern=recipe['pattern'], fingerprint_texture_resolved=True,
        canonical_scale=scale, canonical_shape=[512, 512], aspect_ratio_preserved=True,
        synthetic_pitch_canonical=pitch, synthetic_pitch_pixels=pitch/scale,
        field_recipe=recipe, profile_recipe=profile_recipe, skin_recipe=skin_recipe,
        relief_RMS=float(np.std(values)), original_intensities_used_by_relief=False)


def render(rgb, mask, labels, *, seed=None):
    if not isinstance(rgb, np.ndarray) or rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError('synthetic_RGB_uint8_required')
    validate_resize(*rgb.shape[:2], 1.)
    if (not isinstance(mask, np.ndarray) or mask.dtype != np.bool_ or mask.shape != rgb.shape[:2] or
            not isinstance(labels, np.ndarray) or labels.dtype != np.uint16 or labels.shape != mask.shape or
            not np.array_equal(labels > 0, mask)):
        raise ValueError('synthetic_mask_partition_contract')
    if seed is None:
        seed = secrets.randbits(128)
    if type(seed) is not int or not 0 <= seed < 2**128:
        raise ValueError('synthetic_seed_unsigned_128bit_required')
    ids = np.unique(labels[mask])
    if len(ids) > MAX_REGIONS:
        raise ValueError('synthetic_region_resource_limit')
    out = rgb.copy(); regions = []
    for region_id in ids:
        target = labels == region_id
        if target.sum() > MAX_REGION_PIXELS:
            raise ValueError('synthetic_region_pixel_limit')
        yy, xx, u, v, width, length = geometry(target)
        local = target[yy.min():yy.max()+1, xx.min():xx.max()+1]
        if ndimage.label(local)[1] != 1:
            raise ValueError('synthetic_region_must_be_connected')
        base, color = color_field(rgb[target], u, v, width, length)
        child_seed = int(np.random.SeedSequence([seed, int(region_id)]).generate_state(1, dtype=np.uint64)[0])
        relief, texture = photographic_relief(local, u, v, width, length, child_seed)
        out[target] = np.clip(np.floor(base+relief[:, None]+.5), 0, 255).astype(np.uint8)
        regions.append(dict(region_id=int(region_id), pixels=int(target.sum()),
            geometric_width_pixels=width, color_field=color, **texture,
            pitch_is_measured=False, source_ridge_phase_used=False,
            original_pixel_residual_used=False, mask_sha256=pixel_hash(target)))
    if not np.array_equal(out[~mask], rgb[~mask]):
        raise RuntimeError('synthetic_outside_mask_modified')
    return out, dict(version=VERSION, seed=seed, regions=regions,
        status='synthetic_replacement_applied' if mask.any() else 'no_replacement_regions',
        replacement_regions=len(regions), replaced_pixels=int(mask.sum()),
        unresolved_texture_regions=sum(not r['fingerprint_texture_resolved'] for r in regions),
        actual_changed_pixels=int(np.any(out != rgb, axis=2).sum()),
        source_dependency='coarse_cell_RGB_medians_fitted_by_polynomial_degree_at_most_3',
        coarse_spatial_color_preserved=True, original_pixel_residual_used=False,
        source_alpha_inside_mask=0., edge_source_feathering=False, original_pitch_required=False,
        outside_mask_RGB_preserved=True, output_RGB_sha256=pixel_hash(out), mask_sha256=pixel_hash(mask),
        full_photo_protection_verified=False, privacy_validated=False,
        biometric_validation_performed=False, natural_appearance_validated=False, production_approved=False)
