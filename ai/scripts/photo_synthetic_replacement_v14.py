"""V14: summarized boundary color and derivative correction with C1 blending."""
import cv2
import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree
from photo_synthetic_replacement_v13 import render_version


def hermite_ribbon(base, pixels, u, v, width, length, local):
    padded = ndimage.distance_transform_edt(np.pad(local, 1))
    distance = padded[1:-1, 1:-1][local]
    dy, dx = np.gradient(ndimage.gaussian_filter(padded, max(1., .004*width)))
    normals = np.column_stack((dx[1:-1, 1:-1][local], dy[1:-1, 1:-1][local]))
    normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-8)
    y, x = np.nonzero(local); points = np.column_stack((x, y)).astype(float)
    contours, _ = cv2.findContours(local.astype(np.uint8), cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    contours = sorted(contours, key=lambda c: (-len(c), tuple(c[0, 0])))
    outline = np.concatenate([c[:, 0] for c in contours])
    count = min(256, max(4, round(len(outline)/max(24., width*.055))))
    nodes = np.unique(outline[np.linspace(0, len(outline)-1, count, dtype=int)], axis=0).astype(float)
    owner = cKDTree(nodes).query(points, k=1)[1]
    band = max(1.25, width*.003); transition = max(8., width*.055)
    centers, deltas, slopes, directions = [], [], [], []
    for j in range(len(nodes)):
        near = (owner == j) & (distance <= band)
        deeper = (owner == j) & (distance >= transition*.45) & (distance <= transition*.75)
        if near.sum() < 12: continue
        # A mean preserves the mixture at antialiased silhouette pixels; the
        # median can discard its background contribution and paint a rim.
        color = np.mean(pixels[near], axis=0)
        base_color = np.mean(base[near], axis=0)
        delta = color-base_color
        slope_delta = np.zeros(3)
        if deeper.sum() >= 12:
            separation = float(np.mean(distance[deeper])-np.mean(distance[near]))
            if separation > 1:
                source_slope = (np.mean(pixels[deeper], axis=0)-color)/separation
                base_slope = (np.mean(base[deeper], axis=0)-base_color)/separation
                slope_delta = np.clip(source_slope-base_slope, -.6, .6)
        n = normals[near].mean(axis=0); n /= max(np.linalg.norm(n), 1e-8)
        centers.append(nodes[j]); deltas.append(delta); slopes.append(slope_delta); directions.append(n)
    meta = dict(method='coarse_boundary_mixture_mean_and_C1_Hermite_correction',
        populated_nodes=len(centers), maximum_contour_nodes=256,
        minimum_node_support=12, source_pixel_alpha=0., source_outside_permission_used=False,
        transition_width=transition, sample_band_width=band,
        correction_and_derivative_zero_at_inner_join=True, mask_geometry_changed=False)
    if len(centers) < 4: return base, meta | dict(applied=False)
    centers, deltas, slopes, directions = map(np.array, (centers, deltas, slopes, directions))
    tree = cKDTree(centers); result = base.copy(); active = np.flatnonzero(distance < transition+1)
    for start in range(0, len(active), 4096):
        take = active[start:start+4096]
        distances, indices = tree.query(points[take], k=min(6, len(centers)))
        weights = (distances*distances+4.)**-1.5
        weights *= np.maximum(np.sum(normals[take, None]*directions[indices], axis=2), 0)**4
        total = weights.sum(axis=1); good = total > 1e-20
        take, indices, weights, total = take[good], indices[good], weights[good], total[good]
        delta = np.sum(deltas[indices]*weights[:, :, None], axis=1)/total[:, None]
        derivative = np.sum(slopes[indices]*weights[:, :, None], axis=1)/total[:, None]
        t = np.clip((distance[take]-1)/transition, 0., 1.)
        h00 = 2*t**3-3*t*t+1; h10 = t**3-2*t*t+t
        result[take] += delta*h00[:, None]+derivative*(transition*h10[:, None])
    if not np.isfinite(result).all(): raise ValueError('synthetic_boundary_nonfinite')
    return result, meta | dict(applied=True)


def render(rgb, mask, labels, *, seed=None):
    return render_version(rgb, mask, labels, seed=seed, version='v14', boundary_fn=hermite_ribbon)
