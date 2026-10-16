"""V15: irregular sweat pores are part of the newly generated ridge height."""
import cv2
import numpy as np
from scipy import ndimage
from photo_synthetic_replacement_v10 import normalize
from photo_synthetic_replacement_v13 import render_version, ridge_surface
from photo_synthetic_replacement_v12 import boundary_ribbon


def pore_height(ridge, pitch, seed):
    rng = np.random.default_rng(seed ^ 0xB015)
    random = rng.random(ridge.shape).astype(np.float32)
    spacing = int(np.clip(round(pitch*.38), 3, 15))
    if spacing % 2 == 0: spacing += 1
    crest = ridge > .65
    centers = crest & (random == ndimage.maximum_filter(random, spacing, mode='reflect'))
    # Three radius groups and lognormal depths avoid identical white dots.
    radius = rng.integers(0, 3, ridge.shape, dtype=np.uint8)
    depths = np.clip(rng.lognormal(0., .35, ridge.shape), .4, 2.)
    result = np.zeros(ridge.shape, np.float32)
    for group, factor in enumerate([.065, .10, .145]):
        impulses = np.where(centers & (radius == group), depths, 0.).astype(np.float32)
        sigma = max(.45, pitch*factor)
        depression = cv2.GaussianBlur(impulses, (0, 0), sigma)
        shoulder = cv2.GaussianBlur(impulses, (0, 0), sigma*1.8)
        result += (shoulder-depression)*sigma*sigma*5.
    # Keep the pore depth bounded without amplifying sparse fields to unit RMS.
    result = np.clip(result, -1.8, .5)
    return result, dict(method='ridge_crest_exclusion_spaced_variable_radius_pore_height',
        centers=int(centers.sum()), spacing_latent_pixels=spacing, radius_groups=3,
        centers_outside_generated_ridge_crest=int((centers & ~crest).sum()),
        uniform_white_flecks=False, source_pixels_input=False,
        pore_height_range=[float(result.min()), float(result.max())])


def porous_ridges(gu, gv, width, length, seed):
    ridge, modulation, pitch, info = ridge_surface(gu, gv, width, length, seed)
    scale = min(1., 1536/max(width, length))
    pores, pore_meta = pore_height(ridge, max(2., pitch*scale), seed)
    return ridge+.42*pores, modulation, pitch, info | dict(pores=pore_meta,
        pores_in_height_before_lighting=True)


def quiet_micro(ridge, gu, gv, pitch, scale, seed):
    rng = np.random.default_rng(seed ^ 0xDA15)
    noise = rng.standard_normal(ridge.shape).astype(np.float32)
    fine = cv2.GaussianBlur(noise, (0, 0), .55)-cv2.GaussianBlur(noise, (0, 0), 1.6)
    # Fine uncorrelated camera/skin roughness, no independent bright spot layer.
    detail = .3*np.clip(normalize(fine), -3., 3.)
    return detail, dict(method='quiet_independent_fine_roughness', uniform_white_flecks=False,
        source_pixels_input=False)


def render(rgb, mask, labels, *, seed=None):
    return render_version(rgb, mask, labels, seed=seed, version='v15',
        boundary_fn=boundary_ribbon, ridge_fn=porous_ridges, micro_fn=quiet_micro)
