"""Opt-in appearance of a physical silhouette inside an unchanged permission.

A permission polygon is not a physical skin contour. Fit only a single blurred
RGB step plus a linear shading term to tangent-averaged original profiles.
Reconstruct that coarse appearance, with generated-only texture, inside the
permission. Never copy/alpha-blend source RGB or shrink the protection mask.
This is an experimental appearance model, not a skin classifier or privacy proof.
"""
import cv2
import numpy as np
from scipy import ndimage
from scipy.optimize import least_squares
from scipy.special import ndtr
from scipy.spatial import cKDTree
from photo_synthetic_replacement_v6 import smoothstep

VERSION = 'coarse_silhouette_appearance_v21_experimental'
MAX_CROP_PIXELS = 8*1024*1024
MAX_PERMISSION_PIXELS = 4*1024*1024
MAX_NODES = 192


def _fit_profile(profile, t, radius):
    """Export 2 geometric + 9 coarse color parameters, never a sampled raster."""
    affine = np.column_stack((np.ones(len(t)), t/radius))
    linear = affine @ np.linalg.lstsq(affine, profile, rcond=None)[0]
    linear_error = float(np.mean((linear-profile)**2))
    if linear_error < 1.:
        return None
    def solve(q):
        design = np.column_stack((affine, ndtr((t-q[0])/q[1])))
        coeff = np.linalg.lstsq(design, profile, rcond=None)[0]
        return design @ coeff, coeff
    slope = np.linalg.norm(np.diff(profile, axis=0), axis=1)
    edge = np.clip(t[int(np.argmax(slope))], -.5*radius, .5*radius)
    fit = least_squares(lambda q: (solve(q)[0]-profile).ravel(),
        [edge, max(.6, .07*radius)], bounds=([-.6*radius, .5], [.6*radius, .22*radius]),
        max_nfev=60, ftol=1e-6, xtol=1e-6, gtol=1e-6)
    modeled, coeff = solve(fit.x)
    error = float(np.mean((modeled-profile)**2))
    contrast = float(np.linalg.norm(coeff[2]))
    explained = 1.-error/linear_error
    # Fixed structural evidence tests, chosen before development-photo replay.
    # A broad shadow, double edge/crease, or fine repeated ridges is not a step.
    if (not fit.success or contrast < 25. or explained < .90
            or np.sqrt(error) > .08*contrast or fit.x[1] >= .21*radius
            or np.linalg.norm(coeff[1]) > .35*contrast):
        return None
    return dict(offset=float(fit.x[0]), blur=float(fit.x[1]), coefficients=coeff,
        contrast=contrast, explained=explained, profile_RMSE=float(np.sqrt(error)))


def _sample(rgb, positions):
    # Input is already float32, so interpolation cannot silently round to uint8.
    coords = np.stack((positions[..., 1], positions[..., 0]))
    return np.stack([ndimage.map_coordinates(rgb[..., c], coords, order=1,
        mode='nearest', prefilter=False) for c in range(3)], axis=-1)


def _curve(mask, width):
    contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    if len(contours) != 1 or len(contours[0]) < 24:
        return None
    outline = contours[0][:, 0].astype(float)
    # Anchor sampling to mask geometry, not OpenCV's image-axis start vertex.
    # Otherwise a 90-degree image rotation moves the coarse support windows.
    radial = ((outline-outline.mean(axis=0))**2).sum(axis=1)
    outline = np.roll(outline, -int(np.argmax(radial)), axis=0)
    tangent_half = max(12., .03*width)
    smooth = ndimage.gaussian_filter1d(outline, max(2., tangent_half/3.), axis=0, mode='wrap')
    count = min(MAX_NODES, max(4, round(len(outline)/max(16., .045*width))))
    index = np.linspace(0, len(outline), count, endpoint=False, dtype=int)
    nodes = smooth[index]
    tangent = (np.roll(smooth, -2, axis=0)-np.roll(smooth, 2, axis=0))[index]
    tangent /= np.maximum(np.linalg.norm(tangent, axis=1, keepdims=True), 1e-8)
    normals = np.column_stack((-tangent[:, 1], tangent[:, 0]))
    signed = ndimage.distance_transform_edt(mask)-ndimage.distance_transform_edt(~mask)
    plus = ndimage.map_coordinates(signed, (nodes+normals*3).T[::-1], order=1)
    minus = ndimage.map_coordinates(signed, (nodes-normals*3).T[::-1], order=1)
    normals *= np.where(plus >= minus, 1., -1.)[:, None]
    return nodes, normals, tangent, tangent_half


def refine(source, generated, permission, width, *, texture_mode='local_generated'):
    """Return a fresh RGB8 crop and audit. Crop must include contextual pixels.

    Context is read only. Source outside permission contributes coarse profiles,
    never output pixels. Unsupported arcs retain generated RGB, not source RGB.
    Other pads must be processed separately; this accepts one connected region.
    """
    if texture_mode not in ('local_generated','interior_envelope'):
        raise ValueError('silhouette_texture_mode_contract')
    if (not isinstance(permission, np.ndarray) or permission.dtype != np.bool_
            or permission.ndim != 2 or permission.size > MAX_CROP_PIXELS
            or max(permission.shape, default=0) > 32768
            or not isinstance(source, np.ndarray) or not isinstance(generated, np.ndarray)
            or source.dtype != np.uint8 or generated.dtype != np.uint8
            or source.shape != permission.shape+(3,) or generated.shape != source.shape
            or not np.isfinite(width) or width <= 0):
        raise ValueError('silhouette_RGB8_geometry_contract')
    count = int(permission.sum())
    if not count or count > MAX_PERMISSION_PIXELS:
        raise ValueError('silhouette_permission_size_contract')
    radius = max(12., .04*width)
    if radius > 256.:
        raise ValueError('silhouette_profile_extent_contract')
    if ndimage.label(permission)[1] != 1:
        raise ValueError('silhouette_single_component_required')
    meta = dict(version=VERSION, applied=False, correction_depth=radius,
        permission_geometry_changed=False, source_pixel_alpha=0.,
        source_context_used=True, source_filtered_raster_exported=False,
        source_dependency='tangent_mean_RGB_step_offset_blur_and_affine_colors',
        generated_texture_source='generated_only_mask_normalized_residual',
        natural_appearance_validated=False, privacy_validated=False)
    result = generated.copy()
    curve = _curve(permission, width)
    if curve is None:
        return result, meta | dict(reason='unsupported_contour')
    nodes, normals, tangents, half = curve
    t = np.linspace(-radius, radius, 65)
    along = np.linspace(-half, half, max(25, int(2*half)+1))
    src = source.astype(np.float32)
    models = []
    h, w = permission.shape
    for node, normal, tangent in zip(nodes, normals, tangents):
        pos = node + t[:, None, None]*normal + along[None, :, None]*tangent
        # Never invent evidence with mirrored/clamped image-edge pixels.
        if (pos[..., 0].min() < 0 or pos[..., 1].min() < 0
                or pos[..., 0].max() > w-1 or pos[..., 1].max() > h-1):
            models.append(None)
            continue
        models.append(_fit_profile(_sample(src, pos).mean(axis=1), t, radius))
    valid = np.array([m is not None for m in models])
    isolated = valid.copy()
    valid &= (np.roll(isolated, 1) & np.roll(isolated, -1)) | (
        np.roll(isolated, 1) & np.roll(isolated, 2)) | (
        np.roll(isolated, -1) & np.roll(isolated, -2))
    meta.update(nodes=len(nodes), fitted_nodes=int(isolated.sum()), supported_nodes=int(valid.sum()),
        minimum_consecutive_nodes=3, maximum_nodes=MAX_NODES)
    if not valid.any():
        return result, meta | dict(reason='no_supported_single_edge_arc')
    distance = ndimage.distance_transform_edt(np.pad(permission, 1))[1:-1, 1:-1]
    active = permission & (distance < radius)
    y, x = np.nonzero(active)
    points = np.column_stack((x, y))
    # Remove low-frequency generated shading, retaining only generated texture.
    sigma = max(3., .012*width)
    support = ndimage.gaussian_filter(permission.astype(float), sigma, mode='constant')
    texture = np.empty((len(y), 3))
    envelope=[]
    interior=permission & (distance>=radius) & (distance<2*radius)
    for c in range(3):
        smoothed = ndimage.gaussian_filter(np.where(permission, generated[..., c], 0.).astype(float),
            sigma, mode='constant') / np.maximum(support, 1e-9)
        texture[:, c] = generated[y, x, c]-smoothed[y, x]
        if texture_mode == 'interior_envelope' and interior.sum()>=64:
            # Generated shading errors at the old mask edge are not ridge relief.
            # Bound them using only generated detail away from that edge.
            values=generated[...,c][interior]-smoothed[interior]
            low,high=np.quantile(values,[.01,.99])
            low,high=min(0.,float(low)),max(0.,float(high))
            clipped=np.clip(texture[:,c],low,high)
            envelope.append(dict(channel=c,lower=low,upper=high,
                clipped_values=int((clipped!=texture[:,c]).sum()),support=int(interior.sum())))
            texture[:,c]=clipped
    if texture_mode != 'local_generated':
        meta.update(texture_mode=texture_mode,generated_interior_envelope=envelope,
            version='coarse_silhouette_generated_envelope_v22_experimental')
    tree = cKDTree(nodes)
    changed = 0
    for start in range(0, len(y), 4096):
        select = slice(start, start+4096)
        p = points[select]
        delta, indices = tree.query(p, k=min(4, len(nodes)))
        weights = 1./(delta**2+4.)**1.5
        weights /= weights.sum(axis=1, keepdims=True)
        color = np.zeros((len(p), 3)); coverage = np.zeros(len(p))
        closest_normal = normals[indices[:, 0]]
        for j in range(indices.shape[1]):
            for node_id in np.unique(indices[:, j]):
                if not valid[node_id]:
                    continue
                take = indices[:, j] == node_id
                model = models[node_id]
                normal = normals[node_id]
                projection = np.clip((p[take]-nodes[node_id]) @ normal, -radius, radius)
                skin = ndtr((projection-model['offset'])/model['blur'])
                design = np.column_stack((np.ones(len(projection)), projection/radius, skin))
                estimate = design @ model['coefficients'] + texture[select][take]*skin[:, None]
                # Do not interpolate opposing sides or bridge unsupported arcs.
                agree = np.clip(closest_normal[take] @ normal, 0., 1.)**4
                local_weight = weights[take, j]*agree
                color[take] += local_weight[:, None]*estimate
                coverage[take] += local_weight
        color /= np.maximum(coverage[:, None], 1e-9)
        inward = 1.-smoothstep((distance[y[select], x[select]]-radius*.55)/(radius*.45))
        mix = inward*coverage
        value = generated[y[select], x[select]]*(1.-mix[:, None])+color*mix[:, None]
        result[y[select], x[select]] = np.clip(np.floor(value+.5), 0, 255).astype(np.uint8)
        changed += int((mix > 0).sum())
    # Post-save-equivalent RGB8 coarse profile error, only where permission exists.
    # Local measurements are reported individually; this is not a naturalness test.
    before, after, support_count = [], [], []
    gen_float, out_float = generated.astype(np.float32), result.astype(np.float32)
    active_float = active.astype(float)
    for i in np.flatnonzero(valid):
        pos = nodes[i]+t[:, None, None]*normals[i]+along[None, :, None]*tangents[i]
        usable = ndimage.map_coordinates(active_float, np.stack((pos[..., 1], pos[..., 0])),
            order=0, mode='constant') > .5
        counts = usable.sum(axis=1)
        good = counts >= 8
        if not good.any():
            continue
        means = []
        for array in (src, gen_float, out_float):
            samples = _sample(array, pos)
            means.append((samples*usable[..., None]).sum(axis=1)/np.maximum(counts[:, None], 1))
        before.append(float(np.mean((means[0][good]-means[1][good])**2)))
        after.append(float(np.mean((means[0][good]-means[2][good])**2)))
        support_count.append(int(counts[good].sum()))
    accepted = bool(before and np.average(after, weights=support_count) < np.average(before, weights=support_count))
    meta.update(applied=accepted, reason='coarse_profile_improved' if accepted else 'coarse_profile_not_improved',
        proposed_pixels=changed, profile_guard=dict(before_MSE=float(np.average(before, weights=support_count)) if before else None,
            after_MSE=float(np.average(after, weights=support_count)) if after else None, per_node_before_MSE=before,
            per_node_after_MSE=after, aggregation='support_weighted', accepted=accepted,
            scope='coarse_RGB_step_not_skin_identity_or_privacy'),
        model_summary=[dict(node=i, offset=m['offset'], blur=m['blur'], contrast=m['contrast'],
            explained=m['explained']) for i, m in enumerate(models) if valid[i]])
    return (result if accepted else generated.copy()), meta


def refine_regions(source, generated, applied, labels, *, texture_mode='local_generated'):
    """Adapter for already-rendered, already-authorized native RGB regions.

    No routing, visibility decision, mask dilation, or large-pad downscale is
    introduced. Unsupported sizes/holes/arcs explicitly retain their V19 result.
    """
    from photo_resize_safety_v1 import validate_resize
    from photo_synthetic_replacement_v2 import geometry
    if (not isinstance(source, np.ndarray) or source.dtype != np.uint8 or source.ndim != 3
            or source.shape[-1] != 3 or not isinstance(generated, np.ndarray)
            or generated.dtype != np.uint8 or generated.shape != source.shape
            or not isinstance(applied, np.ndarray) or applied.dtype != np.bool_
            or applied.shape != source.shape[:2] or not isinstance(labels, np.ndarray)
            or labels.dtype != np.uint16 or labels.shape != applied.shape):
        raise ValueError('silhouette_region_adapter_contract')
    validate_resize(*applied.shape, 1.)
    if np.any(applied & (labels == 0)):
        raise ValueError('silhouette_region_adapter_permission_contract')
    ids = np.unique(labels[applied])
    if len(ids) > 256:
        raise ValueError('silhouette_region_adapter_count_contract')
    result = generated.copy();rows = [];total_parts = 0
    for rid, sl in enumerate(ndimage.find_objects(labels), 1):
        if sl is None or rid not in ids:
            continue
        target = applied[sl] & (labels[sl] == rid)
        parts, count = ndimage.label(target);total_parts += count
        if total_parts > 256:
            raise ValueError('silhouette_region_adapter_count_contract')
        for part, box in enumerate(ndimage.find_objects(parts), 1):
            local = parts[box] == part
            row = dict(region_id=rid, part=part)
            if local.size > MAX_CROP_PIXELS or int(local.sum()) > MAX_PERMISSION_PIXELS:
                rows.append(row | dict(applied=False, reason='appearance_size_limit_V19_retained'));continue
            _, _, _, _, width, _ = geometry(local)
            radius = max(12., .04*width)
            if radius > 256.:
                rows.append(row | dict(applied=False, reason='appearance_extent_limit_V19_retained'));continue
            pad = int(np.ceil(2*radius+max(12., .03*width)+8))
            y0, x0 = sl[0].start+box[0].start, sl[1].start+box[1].start
            y1, x1 = y0+local.shape[0], x0+local.shape[1]
            cy0, cx0 = max(0,y0-pad), max(0,x0-pad)
            cy1, cx1 = min(applied.shape[0],y1+pad), min(applied.shape[1],x1+pad)
            if (cy1-cy0)*(cx1-cx0) > MAX_CROP_PIXELS:
                rows.append(row | dict(applied=False, reason='appearance_context_limit_V19_retained'));continue
            permission = np.zeros((cy1-cy0,cx1-cx0),bool)
            permission[y0-cy0:y1-cy0,x0-cx0:x1-cx0] = local
            crop, meta = refine(source[cy0:cy1,cx0:cx1], generated[cy0:cy1,cx0:cx1], permission, width,texture_mode=texture_mode)
            result[cy0:cy1,cx0:cx1][permission] = crop[permission]
            rows.append(row | meta)
    return result, dict(version=VERSION if texture_mode=='local_generated' else 'coarse_silhouette_generated_envelope_v22_experimental', regions=rows,
        corrected_components=sum(r['applied'] for r in rows), permission_geometry_changed=False,
        default_promoted=False, privacy_validated=False)
