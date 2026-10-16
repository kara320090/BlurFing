"""Iteration 2: finer independent ridges with diffuse/specular surface relief."""
import cv2
import numpy as np
from scipy import ndimage
from photo_synthetic_replacement_v7 import render_core
from photo_synthetic_replacement_v5 import independent_variation
from photo_synthetic_replacement_v6 import smoothstep
from photographic_ridge_field_v3 import independent_photographic_field
from organic_ridge_profile import render_photographic_profile


def fine_photographic_relief(local, u, v, width, length, seed, energies):
    yy, xx = np.nonzero(local)
    positions = np.column_stack((xx, yy)).astype(float)
    centered = positions-positions.mean(axis=0)
    _, vectors = np.linalg.eigh(centered.T @ centered/len(positions))
    axis = vectors[:, -1]
    if axis[np.argmax(np.abs(axis))] < 0:
        axis = -axis
    rotation = np.stack(([-axis[1], axis[0]], axis))
    projected = positions @ rotation.T
    midpoint = (projected.min(axis=0)+projected.max(axis=0))/2
    scale = 480/max(width, length)
    affine = np.column_stack((rotation*scale, 255.5-midpoint*scale))
    canonical = cv2.warpAffine(local.astype(np.uint8), affine, (512, 512), flags=cv2.INTER_NEAREST,
        borderMode=cv2.BORDER_CONSTANT, borderValue=0) > 0
    rng = np.random.default_rng(seed)
    pitch = float(np.clip(width*scale/rng.uniform(62., 80.), 4., 12.))
    sample = np.vstack((255.5+v*length*.5*scale, 255.5+u*width*.5*scale))
    meta = dict(canonical_shape=[512, 512], canonical_scale=scale,
        synthetic_pitch_canonical=pitch, synthetic_pitch_pixels=pitch/scale,
        pitch_is_measured=False, aspect_ratio_preserved=True,
        source_ridge_phase_transferred=False, source_orientation_transferred=False)
    if len(u) < 32 or width < 4 or canonical.sum() < 32 or width*scale < 8:
        return rng.normal(0., .35, len(u)), meta | dict(synthetic_pattern='unresolved_tiny_region',
            fingerprint_texture_resolved=False)
    field, recipe = independent_photographic_field(canonical, pitch, seed)
    field, contrast, variation = independent_variation(field, pitch, seed)
    profile, profile_meta = render_photographic_profile(field, canonical, pitch, seed)
    gy, gx = np.gradient(profile)
    direction = rng.uniform(0, 2*np.pi)
    slope = (gx*np.cos(direction)+gy*np.sin(direction))*pitch/(2*np.pi)
    highlight = np.maximum(slope, 0.)**1.5
    highlight -= float(highlight[canonical].mean())
    rough = rng.standard_normal((512, 512)).astype(np.float32)
    rough = cv2.GaussianBlur(rough, (0, 0), max(.4, pitch*.12))-cv2.GaussianBlur(rough, (0, 0), pitch*.5)
    rough /= max(float(rough[canonical].std()), 1e-6)
    relief = (.72*profile+.75*slope+.55*highlight)*contrast+.28*rough
    # Only coarse source-energy summaries control the strength envelope below.
    # The generated directional surface contains no source pixel residual.
    relief = cv2.GaussianBlur(relief.astype(np.float32), (0, 0), max(.35, pitch*.055))
    relief -= float(relief[canonical].mean())
    relief /= max(float(relief[canonical].std()), 1e-6)
    values = ndimage.map_coordinates(relief, sample, order=1, mode='nearest', prefilter=False)
    ny, nx, _ = energies.shape
    coords = np.vstack(((v+1)*ny/2-.5, (u+1)*nx/2-.5))
    observed = ndimage.map_coordinates(energies[:, :, 1], coords, order=1, mode='nearest', prefilter=False)
    amplitude = np.clip(observed*.95, .65, 3.2)
    values *= amplitude
    distance = ndimage.distance_transform_edt(np.pad(local, 1))[1:-1, 1:-1][local]
    values *= smoothstep((distance-1)/max(2., .012*width))
    return values, meta | dict(synthetic_pattern=recipe['pattern'], fingerprint_texture_resolved=True,
        field_recipe=recipe, variation=variation, profile_recipe=profile_meta,
        shading_method='independent_fine_ridge_diffuse_directional_slope_and_highlight',
        source_intensity_array_used_by_ridge_generator=False,
        style_input='coarse_scalar_energy_only', style_RMS_range=[float(amplitude.min()), float(amplitude.max())],
        independent_shallow_roughness=True, relief_RMS=float(values.std()))


def render(rgb, mask, labels, *, seed=None):
    return render_core(rgb, mask, labels, seed=seed, version='v8', relief_fn=fine_photographic_relief)
