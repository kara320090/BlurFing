"""Round 3: coarse boundary ribbon and curved photographic skin material."""
import cv2
import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree
from photo_synthetic_replacement_v10 import render_core, material, normalize, sample_style
from photo_synthetic_replacement_v11 import crease_descriptors
from photo_synthetic_replacement_v7 import reconstructed_skin
from photo_synthetic_replacement_v6 import smoothstep


def folded_skin(pixels, u, v, width, length):
    base, meta = reconstructed_skin(pixels, u, v, width, length)
    correction, creases = crease_descriptors(pixels, base, u, v, width, length, interior_only=True)
    return base+correction[:, None]*[1., .98, .95], meta | dict(macro_creases=creases)


def boundary_ribbon(base, pixels, u, v, width, length, local):
    """Continuous coarse colors/slopes on the original permission contour.

    This reconstructs an opaque RGB boundary field from aggregated interior
    colors. It neither feathers original RGB nor alters the permission mask.
    """
    pad = ndimage.distance_transform_edt(np.pad(local, 1))
    distance = pad[1:-1, 1:-1][local]
    dy, dx = np.gradient(ndimage.gaussian_filter(pad, max(1., .004*width)))
    normals = np.column_stack((dx[1:-1, 1:-1][local], dy[1:-1, 1:-1][local]))
    normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-8)
    y, x = np.nonzero(local); points = np.column_stack((x, y)).astype(float)
    contours, _ = cv2.findContours(local.astype(np.uint8), cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    contours = sorted(contours, key=lambda a: (-len(a), tuple(a[0, 0])))
    outline = np.concatenate([c[:, 0] for c in contours])
    count = min(256, max(4, round(len(outline)/max(24., .055*width))))
    nodes = outline[np.linspace(0, len(outline)-1, count, dtype=int)].astype(float)
    nodes = np.unique(nodes, axis=0)
    assigned = cKDTree(nodes).query(points, k=1)[1]
    band = max(2., .008*width); inner = max(6., .045*width)
    centers, colors, gradients, node_normals = [], [], [], []
    for j in range(len(nodes)):
        near = (assigned == j) & (distance <= band)
        deeper = (assigned == j) & (distance >= inner*.65) & (distance <= inner)
        if near.sum() < 16: continue
        color = np.median(pixels[near], axis=0)
        depth = float(np.median(distance[near]))
        gradient = np.zeros(3)
        if deeper.sum() >= 16:
            delta = float(np.median(distance[deeper]))-depth
            if delta > 1:
                gradient = np.clip((np.median(pixels[deeper], axis=0)-color)/delta, -.6, .6)
        color = np.clip(color-gradient*(depth-1), color-3., color+3.)
        n = normals[near].mean(axis=0); n /= max(np.linalg.norm(n), 1e-8)
        centers.append(nodes[j]); colors.append(color); gradients.append(gradient); node_normals.append(n)
    meta = dict(method='continuous_coarse_contour_RGB_medians_and_inward_slopes',
        maximum_contour_nodes=256, populated_nodes=len(centers), minimum_node_support=16,
        sample_band_width=band, transition_width=inner, source_pixel_alpha=0.,
        source_outside_permission_used=False, mask_geometry_changed=False,
        source_filtered_raster_exported=False, maximum_query_chunk=4096)
    if len(centers) < 4: return base, meta | dict(applied=False)
    centers, colors, gradients, node_normals = map(np.array, (centers, colors, gradients, node_normals))
    tree = cKDTree(centers); result = base.copy()
    active = np.flatnonzero(distance < inner+1)
    k = min(6, len(centers))
    for start in range(0, len(active), 4096):
        take = active[start:start+4096]
        delta, indices = tree.query(points[take], k=k)
        weights = (delta*delta+4.)**-1.5
        weights *= np.maximum(np.sum(normals[take, None]*node_normals[indices], axis=2), 0)**4
        total = weights.sum(axis=1); good = total > 1e-20
        take, indices, weights, total = take[good], indices[good], weights[good], total[good]
        boundary = colors[indices]+gradients[indices]*np.minimum(distance[take, None, None]-1, inner*.7)
        ribbon = np.sum(boundary*weights[:, :, None], axis=1)/total[:, None]
        blend = smoothstep((distance[take]-1)/inner)
        result[take] = ribbon*(1-blend[:, None])+base[take]*blend[:, None]
    return result, meta | dict(applied=True)


def curved_material(local, u, v, width, length, seed, stats, base):
    result, info = material(local, u, v, width, length, seed, stats, base, projection='dome')
    rng = np.random.default_rng(seed ^ 0xAB12)
    scale = min(1., 1536/max(width, length))
    w, h = max(16, round(width*scale)), max(16, round(length*scale))
    sample = np.vstack(((v+1)*(h-1)/2, (u+1)*(w-1)/2))
    take = lambda a: ndimage.map_coordinates(a, sample, order=1, mode='nearest', prefilter=False)
    noise = rng.standard_normal((h, w)).astype(np.float32)
    mid_sigma = max(1., width*.012*scale)
    mid = cv2.GaussianBlur(noise, (0, 0), mid_sigma)
    broad = cv2.GaussianBlur(noise, (0, 0), max(2., width*.05*scale))
    mid = normalize(mid-broad)
    fine = normalize(cv2.GaussianBlur(noise, (0, 0), max(.55, .003*width*scale))-
                     cv2.GaussianBlur(noise, (0, 0), mid_sigma))
    e = sample_style(stats, u, v)
    # Weaker pigment blotches than round 2; microgeometry supplies the detail.
    relief = (.55*take(mid)+.55*take(fine))*np.clip(e[:, 3]*1.4, .8, 4.)
    modulation = np.clip(1+.36*take(mid), .22, 1.6)
    # Fine independent dry-skin flecks have skewed highlights, not white noise.
    spots = (rng.random((h, w)) < .009).astype(np.float32)
    dry = cv2.GaussianBlur(spots, (0, 0), max(.5, .0015*width*scale))
    dry -= cv2.GaussianBlur(dry, (0, 0), max(1.2, .004*width*scale))
    dry = np.clip(normalize(dry), -1., 5.)
    flecks = take(dry)*np.clip(.7+e[:, 0]*1.3, .7, 2.)
    # Only generated texture is softened. Isotropic source energy ratios set
    # a bounded appearance proxy; this is not a calibrated depth/focus model.
    softness = np.clip((.5-e[:, 0]/np.maximum(e[:, 2], .1))/.5, 0., .65)
    detail = (result-base)*modulation[:, None]+relief[:, None]*[1., .90, .82]+flecks[:, None]
    fade = smoothstep((ndimage.distance_transform_edt(np.pad(local, 1))[1:-1, 1:-1][local]-1)/max(2., .006*width))
    h0, w0 = local.shape
    ratio = min(1., 1024/max(h0, w0))
    size = (max(1, round(w0*ratio)), max(1, round(h0*ratio)))
    weights = cv2.resize(local.astype(np.float32), size, interpolation=cv2.INTER_AREA)
    sigma = max(.6, .002*width*ratio)
    denominator = cv2.GaussianBlur(weights, (0, 0), sigma)
    sy, sx = np.nonzero(local)
    query = np.vstack(((sy+.5)*size[1]/h0-.5, (sx+.5)*size[0]/w0-.5))
    for channel in range(3):
        raster = np.zeros(local.shape, np.float32); raster[local] = detail[:, channel]
        reduced = cv2.resize(raster, size, interpolation=cv2.INTER_AREA)
        blurred = cv2.GaussianBlur(reduced, (0, 0), sigma)/np.maximum(denominator, 1e-6)
        soft = ndimage.map_coordinates(blurred, query, order=1, mode='nearest', prefilter=False)
        detail[:, channel] = detail[:, channel]*(1-softness)+soft*softness
    result = base+detail*fade[:, None]
    return result, info | dict(mesoscale_roughness=True, independent_dry_skin_flecks=True,
        pigment_amplitude_reduced_from_v11=True, generated_softening_proxy_range=[float(softness.min()), float(softness.max())],
        coarse_boundary_reconstructed=True, original_pixel_alpha=0.)


def render(rgb, mask, labels, *, seed=None):
    result, meta = render_core(rgb, mask, labels, seed=seed, version='v12',
        base_fn=folded_skin, boundary_fn=boundary_ribbon, material_fn=curved_material)
    meta['macro_crease_count'] = sum(len(r['color_field']['macro_creases']['curves']) for r in meta['regions'])
    meta['source_dependency'] += '_and_parametric_macro_creases_and_coarse_boundary_slopes'
    return result, meta
