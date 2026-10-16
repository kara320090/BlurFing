"""V17: robust macro-fold depth summaries and photographic surface response."""
import cv2
import numpy as np
from photo_synthetic_replacement_v10 import render_core
from photo_synthetic_replacement_v13 import coupled_material
from photo_synthetic_replacement_v11 import crease_descriptors
from photo_synthetic_replacement_v12 import boundary_ribbon
from photo_synthetic_replacement_v7 import reconstructed_skin
from photo_synthetic_replacement_v15 import quiet_micro
from photo_synthetic_replacement_v16 import organic_ridges


def fit_crease_depths(pixels, base, u, v, width, length, curves):
    """Export curve depth, not an image residual or original ridge pattern.

    At most 6 tangential x 16 cross-section scalar medians per macro curve
    enter a robust three-coefficient fit. Spatial macro information remains
    source dependent and cannot establish general biometric privacy.
    """
    residual = (pixels.astype(float)-base) @ np.array([.299, .587, .114])
    refined = []; correction = np.zeros(len(u)); diagnostics = []
    for curve in curves:
        q = curve['quadratic_v_from_u']; sigma = max(1., float(curve['sigma_source_pixels']))
        offset = (v-q[0]-q[1]*u-q[2]*u*u)*length*.5/sigma
        tangent = np.clip(((u+.78)*6/1.56).astype(int), 0, 5)
        cross = np.clip(((offset+4)*2).astype(int), 0, 15)
        valid = (abs(u) <= .78) & (abs(offset) < 4)
        values, design, counts = [], [], []
        for group in np.unique((tangent*16+cross)[valid]):
            take = valid & (tangent*16+cross == group)
            if take.sum() < 24: continue
            t = float(np.median(offset[take]))
            basis = -np.exp(-.5*t*t)+.3*np.exp(-.5*((t-1.8)/.8)**2)
            values.append(float(np.median(residual[take])))
            design.append([basis, 1., t]); counts.append(min(int(take.sum()), 128))
        depth = float(curve['depth_RGB']); fitted_sigma = sigma
        method = 'original_coarse_depth_insufficient_support'
        if len(values) >= 12 and np.linalg.matrix_rank(np.array(design)) == 3:
            a, b = np.array(design), np.array(values)
            weight = np.sqrt(np.array(counts)/max(counts))
            for _ in range(3):
                coefficients = np.linalg.lstsq(a*weight[:, None], b*weight, rcond=None)[0]
                error = a @ coefficients-b
                spread = max(.35, 1.4826*float(np.median(abs(error-np.median(error)))))
                weight = np.sqrt(np.array(counts)/max(counts))*np.minimum(1., 1.5*spread/np.maximum(abs(error), 1e-6))
            depth = float(np.clip(coefficients[0], 0., 24.))
            method = 'robust_bounded_macro_cross_section_depth'
        diagnostics.append(dict(method=method, supported_scalar_cells=len(values), maximum_cells=96,
            old_depth_RGB=float(curve['depth_RGB']), fitted_depth_RGB=depth,
            old_sigma_source_pixels=sigma, fitted_sigma_source_pixels=fitted_sigma))
        if depth <= 1e-6: continue
        refined.append(dict(curve, depth_RGB=depth, sigma_source_pixels=fitted_sigma))
        extent = np.exp(-(np.maximum(abs(u)-.78, 0)/.22)**2)
        offset = offset*sigma/fitted_sigma
        correction += depth*(-np.exp(-.5*offset*offset)+.3*np.exp(-.5*((offset-1.8)/.8)**2))*extent
    return np.clip(correction, -28, 8), refined, dict(
        method='bounded_macro_cross_section_scalar_depth_fit', curves=diagnostics,
        maximum_scalar_medians_per_curve=96, source_filtered_raster_exported=False,
        raw_source_residual_transferred=False)


def photographic_skin(pixels, u, v, width, length):
    base, meta = reconstructed_skin(pixels, u, v, width, length)
    _, descriptors = crease_descriptors(pixels, base, u, v, width, length, interior_only=True)
    correction, curves, depth = fit_crease_depths(pixels, base, u, v, width, length, descriptors['curves'])
    descriptors = dict(descriptors, curves=curves)
    return base+correction[:, None]*[1., .98, .95], meta | dict(macro_creases=descriptors, crease_depth_fit=depth)


def photographic_light(ridge, occupancy, pitch, scale, light, seed):
    height = ridge*(1-.65*occupancy)
    gy, gx = np.gradient(height)
    factor = max(2., pitch*scale)*.20
    normal = np.stack((-gx*factor, -gy*factor, np.ones_like(height)), axis=2)
    normal /= np.maximum(np.linalg.norm(normal, axis=2, keepdims=True), 1e-8)
    direction = np.array([.5*light[0], .5*light[1], np.sqrt(.75)])
    direction /= np.linalg.norm(direction)
    half = direction+[0., 0., 1.]; half /= np.linalg.norm(half)
    rng = np.random.default_rng(seed ^ 0xF017)
    rough = cv2.resize(rng.random((12, 10)).astype(np.float32), height.shape[::-1], interpolation=cv2.INTER_CUBIC)
    rough = np.clip(cv2.GaussianBlur(rough, (0, 0), max(1., pitch*scale*.3)), 0., 1.)
    exponent = 20+35*rough
    diffuse = np.maximum(normal @ direction, 0.)
    specular = np.maximum(normal @ half, 0.)**exponent
    response = .55*height+2.*(diffuse-float(diffuse.mean()))+3.2*(specular-float(specular.mean()))
    return response, dict(method='approximate_diffuse_and_variable_roughness_microfacet_response',
        coarse_light_direction=light.tolist(), exponent_range=[float(exponent.min()), float(exponent.max())],
        pores_and_creased_ridges_share_normals=True, calibrated_physical_camera_model=False,
        source_detail_input=False)


def render(rgb, mask, labels, *, seed=None):
    prepared = {}
    def prepare(pixels, u, v, width, length):
        base, meta = photographic_skin(pixels, u, v, width, length)
        prepared['curves'] = meta['macro_creases']['curves']
        return base, meta
    def shade(local, u, v, width, length, child, stats, base):
        return coupled_material(local, u, v, width, length, child, stats, base,
            prepared['curves'], ridge_fn=organic_ridges, micro_fn=quiet_micro, light_fn=photographic_light)
    result, meta = render_core(rgb, mask, labels, seed=seed, version='v17',
        base_fn=prepare, boundary_fn=boundary_ribbon, material_fn=shade)
    meta['macro_crease_count'] = sum(len(r['color_field']['macro_creases']['curves']) for r in meta['regions'])
    meta['source_dependency'] += '_and_bounded_macro_cross_section_medians_and_boundary_summaries'
    return result, meta
