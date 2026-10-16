"""Opt-in opaque skin material: independent ridges, pores and shallow folds.

Spatial source detail is reduced to coarse RGB medians and <=48 isotropic
energy vectors. No filtered source raster is returned by the style observer.
This restriction is a data-flow contract, not a biometric privacy proof.
"""
import secrets
import cv2
import numpy as np
from scipy import ndimage
from photo_resize_safety_v1 import validate_resize
from photo_rejection_resolution_v1 import pixel_hash
from photo_synthetic_replacement_v2 import geometry
from photo_synthetic_replacement_v6 import continuous_boundary, smoothstep
from photo_synthetic_replacement_v7 import reconstructed_skin
from photo_synthetic_replacement_v5 import independent_variation
from photographic_ridge_field_v3 import independent_photographic_field
from organic_ridge_profile import render_photographic_profile

MAX_REGIONS = 256
MAX_REGION_PIXELS = 4*1024*1024
MAX_BOUNDING_PIXELS = 8*1024*1024
MAX_MATERIAL_DIMENSION = 1536


def normalize(a):
    a = a-float(a.mean())
    return a/max(float(a.std()), 1e-6)


def native_style(pixels, local, u, v, width, length):
    """Bounded isotropic contrast summaries at explicit source-pixel scales."""
    h, w = local.shape
    scale = min(1., 1024/max(h, w))
    shape = (max(1, round(w*scale)), max(1, round(h*scale)))
    weight = cv2.resize(local.astype(np.float32), shape, interpolation=cv2.INTER_AREA)
    maps = []
    for data in (pixels @ np.array([.299, .587, .114]), u, v):
        raster = np.zeros(local.shape, np.float32); raster[local] = data
        maps.append(cv2.resize(raster, shape, interpolation=cv2.INTER_AREA)/np.maximum(weight, 1e-6))
    gray, umap, vmap = maps
    # The filter radii are camera-pixel scales, not observed ridge pitch.
    radii = np.maximum(.4, np.array([.65, 1.4, 3.2, 7.0, 15.])*scale)
    filtered = []
    for sigma in radii:
        num = cv2.GaussianBlur(gray*weight, (0, 0), float(sigma), borderType=cv2.BORDER_REFLECT_101)
        den = cv2.GaussianBlur(weight, (0, 0), float(sigma), borderType=cv2.BORDER_REFLECT_101)
        filtered.append(num/np.maximum(den, 1e-6))
    valid = ndimage.distance_transform_edt(np.pad(weight > .999, 1))[1:-1, 1:-1] > max(3., 15*scale)
    nx, ny = min(6, max(1, int(width)//80)), min(8, max(1, int(length)//80))
    bx = np.clip(((umap+1)*nx/2).astype(int), 0, nx-1)
    by = np.clip(((vmap+1)*ny/2).astype(int), 0, ny-1)
    stats = np.full((ny, nx, 4), np.nan)
    for y in range(ny):
        for x in range(nx):
            take = valid & (bx == x) & (by == y)
            if take.sum() < 32: continue
            for k in range(4):
                band = (filtered[k]-filtered[k+1])[take]
                stats[y, x, k] = 1.4826*np.median(np.abs(band-np.median(band)))
    seen = np.isfinite(stats[:, :, 0])
    if seen.any():
        near = ndimage.distance_transform_edt(~seen, return_distances=False, return_indices=True)
        stats = ndimage.gaussian_filter(stats[tuple(near)], (.5, .5, 0), mode='nearest')
    else:
        stats[:] = [.35, .6, .9, 1.2]
    stats = np.clip(stats, 0, 16.)
    return stats, dict(method='native_pixel_isotropic_multiband_MAD_summaries',
        grid=[nx, ny], analysis_shape=[shape[1], shape[0]], analysis_scale=scale,
        source_pixel_filter_sigmas=[.65, 1.4, 3.2, 7., 15.], maximum_statistics=nx*ny*4,
        populated_cells=int(seen.sum()), energies=stats.tolist(),
        source_phase_exported=False, source_orientation_exported=False,
        source_filtered_raster_exported=False, calibrated_focus_measurement=False)


def sample_style(stats, u, v):
    ny, nx, _ = stats.shape
    coords = np.vstack(((v+1)*ny/2-.5, (u+1)*nx/2-.5))
    return np.column_stack([ndimage.map_coordinates(stats[:, :, k], coords,
        order=1, mode='nearest', prefilter=False) for k in range(stats.shape[2])])


def material(local, u, v, width, length, seed, stats, base, *, projection='plane'):
    """One shared independently generated relief surface at camera resolution."""
    scale = min(1., MAX_MATERIAL_DIMENSION/max(width, length))
    w, h = max(16, round(width*scale)), max(16, round(length*scale))
    yy, xx = np.mgrid[:h, :w].astype(np.float32)
    gu, gv = 2*xx/max(1, w-1)-1, 2*yy/max(1, h-1)-1
    sample = np.vstack(((v+1)*(h-1)/2, (u+1)*(w-1)/2))
    def take(a):
        return ndimage.map_coordinates(a, sample, order=1, mode='nearest', prefilter=False)
    rng = np.random.default_rng(seed ^ 0xAB100)
    if projection not in ('plane', 'dome'):
        raise ValueError('unsupported_synthetic_material_projection')
    design_scale = 480/max(width, length)
    if projection == 'dome':
        # Do not magnify a tiny input into subpixel synthetic ridge periods.
        design_scale = min(1., design_scale)
    pitch = float(np.clip(width*design_scale/rng.uniform(48., 65.), 4., 12.))
    canonical = np.ones((512, 512), bool)
    field, recipe = independent_photographic_field(canonical, pitch, seed)
    field, contrast, warp = independent_variation(field, pitch, seed)
    profile, profile_meta = render_photographic_profile(field, canonical, pitch, seed)
    # Project the same aspect-preserving synthetic field into the material.
    projected_u, projected_v = gu, gv
    if projection == 'dome':
        projected_u = np.arcsin(np.clip(gu*.94, -.94, .94))/np.arcsin(.94)
        projected_v = gv*(1+.08*gu*gu)
    coords = np.array([255.5+projected_v*length*.5*design_scale, 255.5+projected_u*width*.5*design_scale])
    ridge = ndimage.map_coordinates(profile, coords, order=3, mode='nearest', prefilter=True)
    modulation = ndimage.map_coordinates(contrast, coords, order=1, mode='nearest', prefilter=False)
    native_pitch = pitch/design_scale
    p = max(2., native_pitch*scale)
    coarse = cv2.resize(rng.standard_normal((12, 10)).astype(np.float32), (w, h), interpolation=cv2.INTER_CUBIC)
    coarse = normalize(cv2.GaussianBlur(coarse, (0, 0), max(1., p*.7)))
    # Smooth source color gradient chooses only a broad lighting direction.
    gray = base @ np.array([.299, .587, .114])
    design = np.column_stack((np.ones(len(u)), u, v))
    light = np.linalg.lstsq(design[::max(1, len(u)//4096)], gray[::max(1, len(u)//4096)], rcond=None)[0][1:]
    if np.linalg.norm(light) < .2: light = np.array([-.8, -.6])
    light /= max(np.linalg.norm(light), 1e-6)
    gy, gx = np.gradient(ridge)
    slope = (gx*light[0]+gy*light[1])*p/(2*np.pi)
    # Pores belong to the generated raised ridges rather than arbitrary noise.
    impulses = ((rng.random((h, w)) < .035) & (ridge > .25)).astype(np.float32)
    pore = cv2.GaussianBlur(impulses, (0, 0), max(.45, .065*p))
    lip = cv2.GaussianBlur(impulses, (0, 0), max(.85, .14*p))
    pores = np.clip(normalize(lip-pore), -4., 2.)
    fine_noise = rng.standard_normal((h, w)).astype(np.float32)
    fine = normalize(cv2.GaussianBlur(fine_noise, (0, 0), max(.4, .55*scale))-
                     cv2.GaussianBlur(fine_noise, (0, 0), max(.8, 1.5*scale)))
    folds = np.zeros((h, w), np.float32)
    count = int(np.clip(length/max(width*.15, 16), 4, 18))
    for _ in range(count):
        cx, cy = rng.uniform(-.5, .5), rng.uniform(-.95, .95)
        span = rng.uniform(.22, .85)
        slope_fold = rng.uniform(-.45, .45)*width/length
        offset = (gv-cy-slope_fold*(gu-cx)-rng.uniform(-.08, .08)*(gu-cx)**2)*length*.5*scale
        sigma = rng.uniform(.0015, .004)*width*scale+.4
        extent = np.exp(-((gu-cx)/span)**6)
        groove = np.exp(-.5*(offset/sigma)**2)
        shoulder = np.exp(-.5*((offset-1.7*sigma)/(.8*sigma))**2)
        folds += (groove-.35*shoulder)*extent*rng.uniform(.8, 2.)
    energies = sample_style(stats, u, v)
    # Larger dynamic range than the old <=3.2 gray-level ridge cap; all inputs
    # are coarse positive energies, with no source signal blended back.
    ridge_amp = np.clip(np.hypot(energies[:, 1], energies[:, 2])*1.5, .9, 9.)
    fine_amp = np.clip(energies[:, 0]*1.4, .22, 3.5)
    ridge_relief = take((.85*ridge+.7*slope)*modulation*(1+.3*coarse))
    relief = ridge_relief*ridge_amp
    relief += take(pores)*np.clip(energies[:, 1]*.65, .35, 2.5)
    relief += take(fine)*fine_amp
    relief -= take(folds)*np.clip(energies[:, 2]*1.4, .6, 5.)
    pigment = take(coarse)*np.clip(energies[:, 3]*.55, .4, 3.)
    distance = ndimage.distance_transform_edt(np.pad(local, 1))[1:-1, 1:-1][local]
    fade = smoothstep((distance-1)/max(2., .012*width))
    result = base+(relief[:, None]*np.array([1., .96, .92])+pigment[:, None]*[1., .60, .40])*fade[:, None]
    return result, dict(method='coupled_independent_ridges_pores_shallow_folds_camera_scale',
        latent_shape=[h, w], maximum_latent_dimension=MAX_MATERIAL_DIMENSION,
        surface_projection=projection, design_scale=design_scale,
        synthetic_pattern=recipe['pattern'], field_recipe=recipe, deformation=warp,
        profile_recipe=profile_meta, synthetic_pitch_pixels=native_pitch, pitch_is_measured=False,
        fingerprint_texture_resolved=bool(width*design_scale >= 8 and len(u) >= 32),
        generated_fold_count=count, coarse_light_direction=light.tolist(),
        ridge_amplitude_range=[float(ridge_amp.min()), float(ridge_amp.max())],
        original_pixel_residual_used=False, source_orientation_transferred=False,
        source_ridge_phase_transferred=False, source_style_input='coarse_multiband_energies_and_RGB_shading')


def render_core(rgb, mask, labels, *, seed=None, version='v10', base_fn=None,
                boundary_fn=continuous_boundary, material_fn=material):
    if not isinstance(rgb, np.ndarray) or rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError('synthetic_RGB_uint8_required')
    validate_resize(*rgb.shape[:2], 1.)
    if (not isinstance(mask, np.ndarray) or mask.dtype != np.bool_ or mask.shape != rgb.shape[:2] or
            not isinstance(labels, np.ndarray) or labels.dtype != np.uint16 or labels.shape != mask.shape or
            not np.array_equal(labels > 0, mask)):
        raise ValueError('synthetic_mask_partition_contract')
    if seed is None: seed = secrets.randbits(128)
    if type(seed) is not int or not 0 <= seed < 2**128:
        raise ValueError('synthetic_seed_unsigned_128bit_required')
    ids = np.unique(labels[mask])
    if len(ids) > MAX_REGIONS: raise ValueError('synthetic_region_resource_limit')
    out = rgb.copy(); regions = []
    for rid in ids:
        target = labels == rid
        if target.sum() > MAX_REGION_PIXELS: raise ValueError('synthetic_region_pixel_limit')
        yy, xx, u, v, width, length = geometry(target)
        local = target[yy.min():yy.max()+1, xx.min():xx.max()+1]
        if local.size > MAX_BOUNDING_PIXELS: raise ValueError('synthetic_region_bbox_pixel_limit')
        if ndimage.label(local)[1] != 1: raise ValueError('synthetic_region_must_be_connected')
        pixels = rgb[target]
        if base_fn is None: base, color = reconstructed_skin(pixels, u, v, width, length)
        else: base, color = base_fn(pixels, u, v, width, length)
        base, boundary = boundary_fn(base, pixels, u, v, width, length, local)
        stats, style = native_style(pixels, local, u, v, width, length)
        child = int(np.random.SeedSequence([seed, int(rid)]).generate_state(1, dtype=np.uint64)[0])
        values, material_meta = material_fn(local, u, v, width, length, child, stats, base)
        if values.shape != pixels.shape or not np.isfinite(values).all():
            raise ValueError('synthetic_generated_surface_nonfinite_or_shape_mismatch')
        out[target] = np.clip(np.floor(values+.5), 0, 255).astype(np.uint8)
        regions.append(dict(region_id=int(rid), pixels=int(target.sum()), geometric_width_pixels=width,
            color_field=color, boundary_color=boundary, texture_style=style, skin_surface=material_meta,
            fingerprint_texture_resolved=material_meta['fingerprint_texture_resolved'],
            original_pixel_residual_used=False, mask_sha256=pixel_hash(target)))
    if not np.array_equal(out[~mask], rgb[~mask]): raise RuntimeError('synthetic_outside_mask_modified')
    return out, dict(version='opaque_skin_material_'+version+'_experimental', seed=seed, regions=regions,
        status='synthetic_replacement_applied' if mask.any() else 'no_replacement_regions',
        replacement_regions=len(regions), replaced_pixels=int(mask.sum()), macro_crease_count=0,
        unresolved_texture_regions=sum(not r['fingerprint_texture_resolved'] for r in regions),
        actual_changed_pixels=int(np.any(out != rgb, axis=2).sum()),
        source_dependency='coarse_RGB_appearance_and_native_pixel_multiband_energy_summaries',
        original_pixel_residual_used=False, source_alpha_inside_mask=0., edge_source_feathering=False,
        original_pitch_required=False, coarse_spatial_color_preserved=True, outside_mask_RGB_preserved=True,
        output_RGB_sha256=pixel_hash(out), mask_sha256=pixel_hash(mask),
        full_photo_protection_verified=False, privacy_validated=False, biometric_validation_performed=False,
        natural_appearance_validated=False, production_approved=False)


def render(rgb, mask, labels, *, seed=None):
    return render_core(rgb, mask, labels, seed=seed)
