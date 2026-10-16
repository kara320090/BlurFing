"""V16: anatomy-scaled independent flow with local ridge-width variation."""
import cv2
import numpy as np
from scipy import ndimage
from photo_synthetic_replacement_v13 import render_version
from photo_synthetic_replacement_v12 import boundary_ribbon
from photo_synthetic_replacement_v5 import independent_variation
from photo_synthetic_replacement_v15 import pore_height, quiet_micro
from photographic_ridge_field_v3 import independent_photographic_field
from organic_ridge_profile import render_photographic_profile, smooth_random


def organic_profile(field, pitch, seed):
    support = np.ones((512, 512), bool)
    profile, recipe = render_photographic_profile(field, support, pitch, seed)
    rng = np.random.default_rng(seed ^ 0xF016)
    grid = int(np.clip(round(512/max(pitch*2.5, 12)), 12, 40))
    bias = smooth_random(profile.shape, grid, max(.7, pitch*.35), rng)*.14
    sharpness = np.clip(1.2+.3*smooth_random(profile.shape, 11, pitch*.9, rng), .65, 1.9)
    # A spatially varying, asymmetric cross-section changes width/shoulder,
    # rather than adding high-frequency noise to otherwise identical ridges.
    height = np.tanh((profile+bias)*sharpness)
    height += .10*(height*height-float(np.mean(height*height)))
    height -= float(height.mean()); height /= max(float(height.std()), 1e-6)
    return height.astype(np.float32), recipe | dict(
        method='independent_spatially_variable_ridge_width_and_asymmetric_shoulders',
        width_bias_range=[float(bias.min()), float(bias.max())],
        sharpness_range=[float(sharpness.min()), float(sharpness.max())],
        source_phase_input=False)


def organic_ridges(gu, gv, width, length, seed):
    rng = np.random.default_rng(seed ^ 0xAB100)
    scale = min(1., 480/max(width, length))
    pitch = float(np.clip(width*scale/rng.uniform(48., 65.), 4., 12.))
    y, x = np.mgrid[:512, :512]
    # Pole locations now follow the aspect of this pad instead of the entire
    # square canvas. Only geometry is used, never source ridge orientation.
    geometry_mask = (abs(x-255.5) <= max(4., width*scale*.5)) & (abs(y-255.5) <= max(4., length*scale*.5))
    field, recipe = independent_photographic_field(geometry_mask, pitch, seed)
    field, contrast, warp = independent_variation(field, pitch, seed)
    profile, info = organic_profile(field, pitch, seed)
    pu = np.arcsin(np.clip(gu*.94, -.94, .94))/np.arcsin(.94)
    pv = gv*(1+.08*gu*gu)
    coords = np.array([255.5+pv*length*.5*scale, 255.5+pu*width*.5*scale])
    ridge = ndimage.map_coordinates(profile, coords, order=3, mode='nearest', prefilter=True)
    modulation = ndimage.map_coordinates(contrast, coords, order=1, mode='nearest', prefilter=False)
    native_pitch = pitch/scale
    latent_scale = min(1., 1536/max(width, length))
    pores, pore_meta = pore_height(ridge, max(2., native_pitch*latent_scale), seed)
    return ridge+.42*pores, modulation, native_pitch, dict(pattern=recipe['pattern'], field_recipe=recipe,
        profile_recipe=info, variation=warp, pores=pore_meta, pores_in_height_before_lighting=True,
        flow_geometry='aspect_scaled_fingerprint_pad_bounding_geometry',
        synthetic_pitch_pixels=native_pitch, pitch_is_measured=False,
        source_orientation_transferred=False, source_ridge_phase_transferred=False)


def render(rgb, mask, labels, *, seed=None):
    return render_version(rgb, mask, labels, seed=seed, version='v16',
        boundary_fn=boundary_ribbon, ridge_fn=organic_ridges, micro_fn=quiet_micro)
