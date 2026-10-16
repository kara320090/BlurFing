"""Independent skin material with bounded long-crease descriptors (round 2)."""
import cv2
import numpy as np
from scipy import ndimage
from photo_synthetic_replacement_v10 import render_core, material, normalize, sample_style
from photo_synthetic_replacement_v7 import reconstructed_skin


def crease_descriptors(pixels, base, u, v, width, length, *, interior_only=False):
    """Trace long oblique grooves in unordered coarse RGB cell summaries.

    Only a small set of quadratic curves leaves this observer. These curves
    are retained source-dependent macro information, NOT anonymity evidence.
    """
    nx, ny = min(16, max(1, int(width)//32)), min(64, max(1, int(length)//16))
    cells = np.clip(((v+1)*ny/2).astype(int), 0, ny-1)*nx+np.clip(((u+1)*nx/2).astype(int), 0, nx-1)
    data = np.full((ny, nx), np.nan); valid = np.zeros((ny, nx), bool)
    for cell in np.unique(cells):
        take = cells == cell
        if take.sum() < 32: continue
        y, x = divmod(int(cell), nx)
        data[y, x] = (np.median(pixels[take], axis=0)-np.median(base[take], axis=0)) @ [.299, .587, .114]
        valid[y, x] = True
    meta = dict(method='long_oblique_coarse_median_quadratic_crease_descriptors', grid=[nx, ny],
        minimum_cell_support=32, maximum_source_statistics=nx*ny*3, maximum_curves=10,
        retained_source_macro_structure=True, source_filtered_raster_exported=False,
        silhouette_adjacent_evidence_excluded=interior_only, curves=[])
    if nx < 6 or ny < 12 or valid.sum() < 24:
        return np.zeros(len(u)), meta | dict(reason='insufficient_coarse_support')
    nearest = ndimage.distance_transform_edt(~valid, return_distances=False, return_indices=True)
    data = data[tuple(nearest)]
    small = ndimage.gaussian_filter(data, (.48, .55), mode='nearest')
    residual = small-ndimage.gaussian_filter(small, (2.5, .6), mode='nearest')
    admissible = valid
    if interior_only:
        # A groove needs interior support on both sides. Edge shading and
        # truncated tip cells cannot establish a long anatomical skin crease.
        inside = ndimage.distance_transform_edt(np.pad(valid, 1))[1:-1, 1:-1]
        admissible = valid & (inside >= 2.)
    # Hough-like long-line proposals avoid assuming that folds are horizontal.
    xs = np.linspace(-.75, .75, max(9, nx))
    proposals = []
    for slope in np.linspace(-.7, .7, 15):
        for intercept in np.linspace(-.95, .95, ny*2):
            ys = intercept+slope*xs
            coords = np.array([(ys+1)*ny/2-.5, (xs+1)*nx/2-.5])
            supported = ndimage.map_coordinates(admissible.astype(float), coords, order=0, mode='constant', cval=0) > .5
            if supported.sum() < len(xs)*.75: continue
            scores = ndimage.map_coordinates(residual, coords, order=1, mode='nearest', prefilter=False)
            score = -float(np.mean(scores[supported]))
            if score > 1.1: proposals.append((score, intercept, slope))
    correction = np.zeros(len(u))
    selected = []
    for score, intercept, slope in sorted(proposals, reverse=True):
        center = intercept+slope*xs
        if any(np.median(np.abs(center-(c[0]+c[1]*xs+c[2]*xs*xs))) < 5/ny for c in selected): continue
        samples = []
        for x, expected in zip(xs, center):
            col = int(np.clip((x+1)*nx/2, 0, nx-1))
            row = int(np.clip((expected+1)*ny/2, 0, ny-1))
            rows = np.arange(max(0, row-2), min(ny, row+3))
            rows = rows[admissible[rows, col]]
            if not len(rows): continue
            r = rows[np.argmin(residual[rows, col])]
            if residual[r, col] < -.8: samples.append((x, (r+.5)*2/ny-1, -residual[r, col]))
        if len(samples) < max(6, len(xs)*.6): continue
        x, y, depth = np.array(samples).T
        design = np.column_stack((np.ones(len(x)), x, x*x))
        coefficients = np.linalg.lstsq(design*np.sqrt(depth)[:, None], y*np.sqrt(depth), rcond=None)[0]
        error = np.abs(design @ coefficients-y)
        if np.median(error) > 1.8/ny or abs(coefficients[2]) > .35: continue
        # Reconstruct a shallow parametric groove narrower than the coarse
        # cell; no source line pixels or high-frequency orientation are used.
        sigma = max(.0045*width, .45*length/ny)
        center_native = coefficients[0]+coefficients[1]*u+coefficients[2]*u*u
        distance = (v-center_native)*length*.5
        amp = float(np.clip(np.median(depth)*1.7, 1.4, 18.))
        extent = np.exp(-(np.maximum(np.abs(u)-.78, 0)/.22)**2)
        groove = np.exp(-.5*(distance/sigma)**2)
        shoulder = np.exp(-.5*((distance-1.8*sigma)/(.8*sigma))**2)
        correction += (-amp*groove+.3*amp*shoulder)*extent
        selected.append(coefficients)
        meta['curves'].append(dict(quadratic_v_from_u=coefficients.tolist(), sigma_source_pixels=sigma,
            depth_RGB=amp, supported_columns=len(samples), fit_median_error_v=float(np.median(error))))
        if len(selected) == 10: break
    return np.clip(correction, -24, 6), meta


def folded_skin(pixels, u, v, width, length):
    base, info = reconstructed_skin(pixels, u, v, width, length)
    correction, creases = crease_descriptors(pixels, base, u, v, width, length)
    return base+correction[:, None]*[1., .98, .95], info | dict(macro_creases=creases)


def mesoscale_material(local, u, v, width, length, seed, stats, base):
    result, info = material(local, u, v, width, length, seed, stats, base)
    rng = np.random.default_rng(seed ^ 0xAB11)
    scale = min(1., 1024/max(width, length))
    w, h = max(16, round(width*scale)), max(16, round(length*scale))
    sample = np.vstack(((v+1)*(h-1)/2, (u+1)*(w-1)/2))
    noise = rng.standard_normal((h, w)).astype(np.float32)
    broad = cv2.GaussianBlur(noise, (0, 0), max(1., width*.014*scale))
    wider = cv2.GaussianBlur(noise, (0, 0), max(2., width*.055*scale))
    middle = normalize(broad-wider)
    # Small independent polygonal undulations stand in for uneven, dry skin.
    high = cv2.GaussianBlur(noise, (0, 0), max(.7, width*.004*scale))
    patches = normalize(high-broad)
    take = lambda a: ndimage.map_coordinates(a, sample, order=1, mode='nearest', prefilter=False)
    energy = sample_style(stats, u, v)
    amp = np.clip(energy[:, 3]*2., 1.2, 6.)
    relief = (.8*take(middle)+.45*take(patches))*amp
    # Variable relief reduces uniform all-over ridge embossing.
    modulation = np.clip(1+.38*take(middle), .18, 1.65)
    distance = ndimage.distance_transform_edt(np.pad(local, 1))[1:-1, 1:-1][local]
    fade = np.clip((distance-1)/max(2., width*.012), 0, 1)
    result = base+(result-base)*modulation[:, None]+relief[:, None]*[1., .85, .72]*fade[:, None]
    return result, info | dict(mesoscale_roughness=True, independently_generated_albedo=True,
        mesoscale_rms=float(np.std(relief)), no_original_pixel_blending=True)


def render(rgb, mask, labels, *, seed=None):
    result, meta = render_core(rgb, mask, labels, seed=seed, version='v11',
        base_fn=folded_skin, material_fn=mesoscale_material)
    meta['macro_crease_count'] = sum(len(r['color_field']['macro_creases']['curves']) for r in meta['regions'])
    meta['source_dependency'] += '_and_long_parametric_macro_crease_descriptors'
    return result, meta
