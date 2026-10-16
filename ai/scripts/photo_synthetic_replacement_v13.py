"""Versioned opaque material with crease-coupled ridge deformation.

The observer retains coarse source colors, macro curves and scalar energies.
The material receives summaries only: no source RGB raster, ridge phase or
minutiae. This data flow is not a general biometric privacy guarantee.
"""
import cv2
import numpy as np
from scipy import ndimage
from photo_synthetic_replacement_v10 import render_core, normalize, sample_style
from photo_synthetic_replacement_v11 import crease_descriptors
from photo_synthetic_replacement_v12 import boundary_ribbon
from photo_synthetic_replacement_v7 import reconstructed_skin
from photo_synthetic_replacement_v6 import smoothstep
from photo_synthetic_replacement_v5 import independent_variation
from photographic_ridge_field_v3 import independent_photographic_field
from organic_ridge_profile import render_photographic_profile

MAX_SURFACE_DIMENSION = 1536


def crease_geometry(gu, gv, width, length, curves, seed):
    """A shared fold geometry controls ridge position, occlusion and shading."""
    rng = np.random.default_rng(seed ^ 0xCE13)
    bend = np.zeros(gu.shape, np.float32)
    occupancy = np.zeros_like(bend); secondary = np.zeros_like(bend)
    for c in curves:
        q = c['quadratic_v_from_u']
        offset = (gv-q[0]-q[1]*gu-q[2]*gu*gu)*length*.5
        sigma = max(1., float(c['sigma_source_pixels']))
        extent = np.exp(-(np.maximum(np.abs(gu)-.78, 0)/.22)**2)
        valley = np.exp(-.5*(offset/(sigma*1.4))**2)*extent
        occupancy = np.maximum(occupancy, valley*np.clip(c['depth_RGB']/8, 0, 1))
        bend += (sigma/length)*.45*np.tanh(offset/sigma)*valley
    count = int(np.clip(length/max(width*.16, 24), 3, 14))
    for _ in range(count):
        x0, y0 = rng.uniform(-.55, .55), rng.uniform(-.85, .85)
        slope = rng.uniform(-.35, .35)*width/length
        span = rng.uniform(.22, .65)
        sigma = max(.8, width*rng.uniform(.0015, .0035))
        offset = (gv-y0-slope*(gu-x0)-rng.uniform(-.04, .04)*(gu-x0)**2)*length*.5
        extent = np.exp(-((gu-x0)/span)**6)
        valley = np.exp(-.5*(offset/sigma)**2)*extent
        shoulder = np.exp(-.5*((offset-1.8*sigma)/(.8*sigma))**2)*extent
        amplitude = rng.uniform(.6, 1.5)
        secondary += (valley-.25*shoulder)*amplitude
        occupancy = np.maximum(occupancy, .30*valley)
        bend += .35*sigma/length*np.tanh(offset/sigma)*valley
    # Bound the coordinate-map Jacobian rather than clipping its positions.
    dy, dx = np.gradient(bend)
    dy *= max(1, gu.shape[0]-1)/2
    dx *= max(1, gu.shape[1]-1)/2*length/width
    norm = np.hypot(dx, dy)
    factor = min(1., .22/max(float(norm.max()), 1e-6))
    bend *= factor
    return gv+bend, occupancy, secondary, dict(
        observed_macro_curves=len(curves), generated_secondary_folds=count,
        warp_gradient_bound=float(norm.max()*factor),
        warp_minimum_singular_value_bound=.78, source_ridge_phase_used=False)


def ridge_surface(gu, gv, width, length, seed):
    rng = np.random.default_rng(seed ^ 0xAB100)
    scale = min(1., 480/max(width, length))
    pitch = float(np.clip(width*scale/rng.uniform(48., 65.), 4., 12.))
    mask = np.ones((512, 512), bool)
    field, recipe = independent_photographic_field(mask, pitch, seed)
    field, contrast, warp = independent_variation(field, pitch, seed)
    profile, info = render_photographic_profile(field, mask, pitch, seed)
    pu = np.arcsin(np.clip(gu*.94, -.94, .94))/np.arcsin(.94)
    pv = gv*(1+.08*gu*gu)
    coords = np.array([255.5+pv*length*.5*scale, 255.5+pu*width*.5*scale])
    ridge = ndimage.map_coordinates(profile, coords, order=3, mode='nearest', prefilter=True)
    modulation = ndimage.map_coordinates(contrast, coords, order=1, mode='nearest', prefilter=False)
    return ridge, modulation, pitch/scale, dict(pattern=recipe['pattern'], field_recipe=recipe,
        profile_recipe=info, variation=warp, synthetic_pitch_pixels=pitch/scale,
        pitch_is_measured=False, source_ridge_phase_transferred=False)


def legacy_micro(ridge, gu, gv, pitch, scale, seed):
    """Independent V13 microtexture, retained for version replay."""
    rng = np.random.default_rng(seed ^ 0x5013)
    p = max(2., pitch*scale)
    impulses = ((rng.random(ridge.shape) < .035) & (ridge > .25)).astype(np.float32)
    pore = cv2.GaussianBlur(impulses, (0, 0), max(.45, .065*p))
    lip = cv2.GaussianBlur(impulses, (0, 0), max(.85, .14*p))
    pores = np.clip(normalize(lip-pore), -4., 2.)
    spots = (rng.random(ridge.shape) < .009).astype(np.float32)
    dry = cv2.GaussianBlur(spots, (0, 0), max(.5, .08*p))
    dry -= cv2.GaussianBlur(dry, (0, 0), max(1.2, .22*p))
    detail = .45*pores+.55*np.clip(normalize(dry), -1., 5.)
    return detail, dict(method='legacy_independent_pores_and_dry_flecks', source_pixels_input=False)


def diffuse_light(ridge, occupancy, pitch, scale, light, seed):
    height = ridge*(1-.65*occupancy)
    gy, gx = np.gradient(height)
    slope = (gx*light[0]+gy*light[1])*max(2., pitch*scale)/(2*np.pi)
    return .85*height+.7*slope, dict(method='crease_coupled_diffuse_relief',
        crease_occlusion_used=True, coarse_light_direction=light.tolist())


def generated_soften(detail, local, width, softness):
    """Only independently generated detail is filtered, at <=1024px."""
    h, w = local.shape; ratio = min(1., 1024/max(h, w))
    size = (max(1, round(w*ratio)), max(1, round(h*ratio)))
    weight = cv2.resize(local.astype(np.float32), size, interpolation=cv2.INTER_AREA)
    sigma = max(.6, .002*width*ratio)
    den = cv2.GaussianBlur(weight, (0, 0), sigma)
    y, x = np.nonzero(local)
    query = np.vstack(((y+.5)*size[1]/h-.5, (x+.5)*size[0]/w-.5))
    out = detail.copy()
    for k in range(3):
        raster = np.zeros(local.shape, np.float32); raster[local] = detail[:, k]
        small = cv2.resize(raster, size, interpolation=cv2.INTER_AREA)
        blurred = cv2.GaussianBlur(small, (0, 0), sigma)/np.maximum(den, 1e-6)
        soft = ndimage.map_coordinates(blurred, query, order=1, mode='nearest', prefilter=False)
        out[:, k] = detail[:, k]*(1-softness)+soft*softness
    return out


def coupled_material(local, u, v, width, length, seed, stats, base, curves, *,
                     ridge_fn=ridge_surface, micro_fn=legacy_micro, light_fn=diffuse_light):
    scale = min(1., MAX_SURFACE_DIMENSION/max(width, length))
    w, h = max(16, round(width*scale)), max(16, round(length*scale))
    y, x = np.mgrid[:h, :w].astype(np.float32)
    gu, gv = 2*x/(w-1)-1, 2*y/(h-1)-1
    sample = np.vstack(((v+1)*(h-1)/2, (u+1)*(w-1)/2))
    take = lambda a: ndimage.map_coordinates(a, sample, order=1, mode='nearest', prefilter=False)
    bent, occupancy, folds, fold_meta = crease_geometry(gu, gv, width, length, curves, seed)
    ridge, modulation, pitch, ridge_meta = ridge_fn(gu, bent, width, length, seed)
    gray = base @ np.array([.299, .587, .114]); step = max(1, len(u)//4096)
    design = np.column_stack((np.ones(len(u[::step])), u[::step], v[::step]))
    light = np.linalg.lstsq(design, gray[::step], rcond=None)[0][1:]
    if np.linalg.norm(light) < .2: light = np.array([-.8, -.6])
    light /= max(np.linalg.norm(light), 1e-6)
    shading, lighting = light_fn(ridge, occupancy, pitch, scale, light, seed)
    micro, micro_meta = micro_fn(ridge, gu, bent, pitch, scale, seed)
    rng = np.random.default_rng(seed ^ 0xAB12)
    noise = rng.standard_normal((h, w)).astype(np.float32)
    mid_sigma = max(1., width*.012*scale)
    mid = cv2.GaussianBlur(noise, (0, 0), mid_sigma)
    broad = cv2.GaussianBlur(noise, (0, 0), max(2., width*.05*scale))
    mid = normalize(mid-broad)
    fine = normalize(cv2.GaussianBlur(noise, (0, 0), max(.55, .003*width*scale))-
                     cv2.GaussianBlur(noise, (0, 0), mid_sigma))
    e = sample_style(stats, u, v)
    amplitude = np.clip(np.hypot(e[:, 1], e[:, 2])*1.5, .9, 9.)
    relief = take(shading*modulation*np.clip(1+.3*mid, .2, 1.6))*amplitude
    relief -= take(folds)*np.clip(e[:, 2]*1.2, .5, 4.)
    relief += take(micro)*np.clip(.7+e[:, 0]*1.3, .7, 2.)
    pigment = (.4*take(mid)+.45*take(fine))*np.clip(e[:, 3]*1.4, .8, 4.)
    detail = relief[:, None]*[1., .96, .92]+pigment[:, None]*[1., .90, .82]
    softness = np.clip((.5-e[:, 0]/np.maximum(e[:, 2], .1))/.5, 0., .65)
    detail = generated_soften(detail, local, width, softness)
    distance = ndimage.distance_transform_edt(np.pad(local, 1))[1:-1, 1:-1][local]
    fade = smoothstep((distance-1)/max(2., .006*width))
    result = base+detail*fade[:, None]
    return result, dict(method='joint_crease_ridge_skin_surface', latent_shape=[h, w],
        maximum_latent_dimension=MAX_SURFACE_DIMENSION, synthetic_pitch_pixels=pitch,
        fingerprint_texture_resolved=bool(width >= 4 and len(u) >= 32),
        crease_geometry=fold_meta, ridge_surface=ridge_meta, micro_surface=micro_meta, lighting=lighting,
        source_pixels_input=False, source_ridge_phase_transferred=False, original_pixel_alpha=0.)


def render_version(rgb, mask, labels, *, seed=None, version='v13',
                   boundary_fn=boundary_ribbon, ridge_fn=ridge_surface,
                   micro_fn=legacy_micro, light_fn=diffuse_light):
    # Region preparation and material share only bounded curve descriptors.
    # The closure is request-local, never global or shared between requests.
    prepared = {}
    def prepare(pixels, u, v, width, length):
        base, info = reconstructed_skin(pixels, u, v, width, length)
        correction, curves = crease_descriptors(pixels, base, u, v, width, length, interior_only=True)
        prepared['curves'] = curves['curves']
        return base+correction[:, None]*[1., .98, .95], info | dict(macro_creases=curves)
    def shade(local, u, v, width, length, child, stats, base):
        return coupled_material(local, u, v, width, length, child, stats, base, prepared['curves'],
            ridge_fn=ridge_fn, micro_fn=micro_fn, light_fn=light_fn)
    result, meta = render_core(rgb, mask, labels, seed=seed, version=version,
        base_fn=prepare, boundary_fn=boundary_fn, material_fn=shade)
    meta['macro_crease_count'] = sum(len(r['color_field']['macro_creases']['curves']) for r in meta['regions'])
    meta['source_dependency'] += '_and_bounded_macro_curves_and_inside_boundary_summaries'
    return result, meta


def render(rgb, mask, labels, *, seed=None):
    return render_version(rgb, mask, labels, seed=seed)
