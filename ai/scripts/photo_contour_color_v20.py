"""Experimental coarse contour color recovery after V19, never source alpha.

V19 clips every coarse RGB correction to 16, even when the original permission
contour contains a large antialiased skin/background transition. That bound
can make a known coarse color mismatch impossible to correct. This version
uses the observed node-mean range as its interpolation bound instead. Original
V19 and its default path remain unchanged. No source residual raster or fine
ridge phase is exported; coarse source dependence is not a privacy proof.
"""
import cv2
import numpy as np
from scipy import ndimage
from scipy.interpolate import PchipInterpolator
from scipy.spatial import cKDTree
from photo_synthetic_replacement_v6 import smoothstep
from photo_organic_surface_v19 import guard_contour_correction


def contour_color(generated, pixels, local, width):
    if (not isinstance(local, np.ndarray) or local.dtype != np.bool_ or local.ndim != 2
            or local.size > 8*1024*1024 or generated.shape != pixels.shape
            or generated.ndim != 2 or generated.shape[1] != 3 or len(pixels) > 4*1024*1024
            or int(local.sum()) != len(pixels) or not len(pixels)
            or not np.isfinite(pixels).all() or not np.isfinite(generated).all()
            or min(float(pixels.min()), float(generated.min())) < 0
            or max(float(pixels.max()), float(generated.max())) > 255
            or not np.isfinite(width) or width <= 0):
        raise ValueError('contour_color_RGB_geometry_contract')
    distance = ndimage.distance_transform_edt(np.pad(local, 1))[1:-1, 1:-1][local]
    contours, _ = cv2.findContours(local.astype(np.uint8), cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    outline = np.concatenate([c[:, 0] for c in contours])
    count = min(192, max(4, round(len(outline)/max(24., .07*width))))
    nodes = np.unique(outline[np.linspace(0, len(outline)-1, count, dtype=int)], axis=0)
    y, x = np.nonzero(local)
    points = np.column_stack((x, y))
    owner = cKDTree(nodes).query(points, k=1)[1]
    transition = max(8., .06*width)
    band = max(1.5, .006*width)
    knots = np.array([1., 1.+transition*.28, 1.+transition*.64, 1.+transition])
    centers, values = [], []
    for node in range(len(nodes)):
        owned = owner == node
        data = []
        for knot in knots[:-1]:
            take = owned & (abs(distance-knot) <= band)
            if take.sum() < 24:
                break
            data.append(np.mean(pixels[take], axis=0)-np.mean(generated[take], axis=0))
        if len(data) == 3:
            centers.append(nodes[node])
            values.append(data+[np.zeros(3)])
    meta = dict(version='coarse_contour_color_v20', populated_nodes=len(centers), maximum_nodes=192,
        minimum_band_support=24, sample_depths=knots.tolist(), transition_width=transition,
        interpolation_bound='observed_aggregated_RGB_corrections_including_zero',
        original_pixel_alpha=0., source_outside_permission_used=False,
        source_filtered_raster_exported=False, mask_geometry_changed=False,
        source_dependency='inside_contour_RGB_means_only', privacy_validated=False,
        natural_appearance_validated=False, maximum_query_chunk=4096)
    if len(centers) < 4:
        return generated.copy(), meta | dict(applied=False, reason='insufficient_coarse_support')
    values = np.asarray(values)
    interpolator = PchipInterpolator(knots, values, axis=1, extrapolate=False)
    lower = values.min(axis=1)
    upper = values.max(axis=1)
    meta['observed_maximum_absolute_correction'] = float(abs(values).max())
    meta['scalar_node_values_exceeding_V19_bound'] = int((abs(values) > 16.).sum())
    tree = cKDTree(centers)
    result = generated.astype(np.float64, copy=True)
    active = np.flatnonzero(distance < knots[-1])
    for start in range(0, len(active), 4096):
        take = active[start:start+4096]
        delta, indices = tree.query(points[take], k=min(4, len(centers)))
        weights = 1/(delta*delta+4.)**1.5
        weights /= weights.sum(axis=1, keepdims=True)
        t = np.clip(distance[take], knots[0], knots[-1])
        correction = np.zeros((len(take), 3))
        interval = np.clip(np.searchsorted(knots, t, side='right')-1, 0, len(knots)-2)
        dt = (t-knots[interval])[:, None]
        for j in range(indices.shape[1]):
            coeff = interpolator.c[:, interval, indices[:, j], :]
            evaluated = ((coeff[0]*dt+coeff[1])*dt+coeff[2])*dt+coeff[3]
            # Numerical guard: PCHIP may not exceed its observed node envelope.
            evaluated = np.clip(evaluated, lower[indices[:, j]], upper[indices[:, j]])
            correction += evaluated*weights[:, j, None]
        end = smoothstep((knots[-1]-distance[take])/(transition*.36))
        result[take] += correction*end[:, None]
    result = np.clip(result, 0., 255.)
    if not np.isfinite(result).all():
        raise ValueError('contour_color_nonfinite')
    selected, decision = guard_contour_correction(generated, result, pixels, local)
    return selected.copy(), meta | dict(applied=decision['accepted'], boundary_guard=decision)
