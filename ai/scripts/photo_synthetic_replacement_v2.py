"""Opaque synthetic ridges over a coarse, low-order source color field.

V2 retains coarse spatial color statistics, unlike V1's single median color.
Only cell medians enter a cubic (or lower) polynomial. Original pixels, local
ridge phase, and high-frequency residuals are never blended back into output.
Cell-wise pixel permutation invariance is a data-flow test, NOT privacy proof.
"""
import secrets
import numpy as np
from scipy import ndimage
from photo_resize_safety_v1 import validate_resize
from photo_rejection_resolution_v1 import pixel_hash

VERSION = 'opaque_synthetic_fingerprint_replacement_v2_experimental'
MAX_REGIONS = 256
MAX_REGION_PIXELS = 4*1024*1024
MIN_COLOR_CELL_WIDTH = 64


def geometry(target):
    yy, xx = np.nonzero(target)
    points = np.column_stack((xx, yy)).astype(np.float64)
    centered = points-points.mean(axis=0)
    _, vectors = np.linalg.eigh(centered.T @ centered/len(points))
    axis = vectors[:, -1]
    if axis[np.argmax(np.abs(axis))] < 0:
        axis = -axis
    normal = np.array([-axis[1], axis[0]])
    across, along = centered @ normal, centered @ axis
    width, length = max(1., float(np.ptp(across))+1.), max(1., float(np.ptp(along))+1.)
    # Centers in [-1,1] give a numerically stable low-order color basis.
    u = 2*(across-(across.min()+across.max())/2)/width
    v = 2*(along-(along.min()+along.max())/2)/length
    return yy, xx, u, v, width, length


def color_cells(u, v, width, length):
    nx = min(8, max(1, int(width)//MIN_COLOR_CELL_WIDTH))
    ny = min(10, max(1, int(length)//MIN_COLOR_CELL_WIDTH))
    bx = np.clip(((u+1)*nx/2).astype(int), 0, nx-1)
    by = np.clip(((v+1)*ny/2).astype(int), 0, ny-1)
    return by*nx+bx, nx, ny


def _basis(u, v, degree):
    return np.column_stack([u**i*v**(total-i) for total in range(degree+1) for i in range(total+1)])


def color_field(pixels, u, v, width, length):
    cells, nx, ny = color_cells(u, v, width, length)
    positions, colors, weights = [], [], []
    for cell in np.unique(cells):
        select = cells == cell
        # Geometry/coverage determines selection; no texture quality gate.
        if select.sum() < 16:
            continue
        positions.append([float(u[select].mean()), float(v[select].mean())])
        colors.append(np.median(pixels[select], axis=0))
        weights.append(int(select.sum()))
    count = len(colors)
    degree = 3 if count >= 24 else 2 if count >= 12 else 1 if count >= 4 else 0
    if degree == 0:
        median = np.median(pixels, axis=0)
        coefficients = median[None, :]
        result = np.broadcast_to(median, pixels.shape).copy()
        fit_error = 0.
    else:
        coords, values = np.array(positions), np.array(colors)
        design = _basis(coords[:, 0], coords[:, 1], degree)
        weight = np.sqrt(np.array(weights)/max(weights))
        # Regularization only stabilizes a bounded polynomial, not source texture.
        penalty = np.eye(design.shape[1])*.025
        penalty[0, 0] = 0
        lhs = np.vstack((design*weight[:, None], penalty))
        rhs = np.vstack((values*weight[:, None], np.zeros((len(penalty), 3))))
        coefficients = np.linalg.lstsq(lhs, rhs, rcond=None)[0]
        result = _basis(u, v, degree) @ coefficients
        # Prevent polynomial extrapolation from creating extreme edge colors.
        result = np.clip(result, values.min(axis=0)-3, values.max(axis=0)+3)
        fit_error = float(np.sqrt(np.mean((design @ coefficients-values)**2)))
    return result, dict(grid=[nx, ny], populated_cells=count, degree=degree,
        maximum_statistics=nx*ny*3, coefficients_RGB=coefficients.tolist(),
        cell_median_fit_RMSE=fit_error, cell_selection_min_pixels=16,
        source_data='coarse_cell_RGB_medians_only' if degree else 'region_RGB_median_only')


def render(rgb, mask, labels, *, seed=None):
    if (not isinstance(rgb, np.ndarray) or rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3):
        raise ValueError('synthetic_RGB_uint8_required')
    validate_resize(*rgb.shape[:2], 1.)
    if (not isinstance(mask, np.ndarray) or mask.dtype != np.bool_ or mask.shape != rgb.shape[:2] or
            not isinstance(labels, np.ndarray) or labels.dtype != np.uint16 or labels.shape != mask.shape or
            not np.array_equal(labels > 0, mask)):
        raise ValueError('synthetic_mask_partition_contract')
    if seed is None:
        seed = secrets.randbits(128)
    if type(seed) is not int or not 0 <= seed < 2**128:
        raise ValueError('synthetic_seed_unsigned_128bit_required')
    ids = np.unique(labels[mask])
    if len(ids) > MAX_REGIONS:
        raise ValueError('synthetic_region_resource_limit')
    out = rgb.copy(); regions = []
    for region_id in ids:
        target = labels == region_id
        if int(target.sum()) > MAX_REGION_PIXELS:
            raise ValueError('synthetic_region_pixel_limit')
        yy, xx, u, v, width, length = geometry(target)
        y0, y1, x0, x1 = int(yy.min()), int(yy.max())+1, int(xx.min()), int(xx.max())+1
        local = target[y0:y1, x0:x1]
        if ndimage.label(local)[1] != 1:
            raise ValueError('synthetic_region_must_be_connected')
        base, field = color_field(rgb[target], u, v, width, length)
        rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence([seed, int(region_id)])))
        across, along = u*.5, v*.5*length/width
        angle = rng.uniform(-.22, .22)
        a = across*np.cos(angle)-along*np.sin(angle)
        b = across*np.sin(angle)+along*np.cos(angle)
        # Smooth independent coordinate warps remove perfectly repeated rings.
        for _ in range(3):
            p, q = rng.uniform(1.5, 5., 2); phase = rng.uniform(0, 2*np.pi)
            a = a+.018*np.sin(p*a+q*b+phase)
            b = b+.018*np.cos(q*a-p*b+phase)
        pattern = int(rng.integers(0, 3))
        if pattern == 0:
            distance = b+.32*np.exp(-((a-rng.uniform(-.12, .12))/.38)**2)
            family = 'arch'
        elif pattern == 1:
            # An offset core produces open loops through the region boundary.
            core = rng.uniform(.35, .7)
            distance = np.sqrt((a-core)**2+(.72*b)**2+.001)+.08*b
            family = 'offset_loop'
        else:
            core_a, core_b = rng.uniform(-.13, .13, 2)
            distance = np.sqrt((a-core_a)**2+(.85*(b-core_b))**2+.0005)+.05*np.sin(3*a+2*b)
            family = 'warped_whorl'
        pitch = max(4., width/rng.uniform(40., 54.))
        phase = 2*np.pi*distance*width/pitch+rng.uniform(0, 2*np.pi)
        amplitude = 1.2+.45*np.sin(3*a-2*b+rng.uniform(0, 2*np.pi))
        relief = amplitude*(np.sin(phase)+.22*np.sin(2*phase+.4))
        # Fade generated relief at the edge, never fade into original RGB.
        padded = np.pad(local, 1, constant_values=False)
        edge = ndimage.distance_transform_edt(padded)[1:-1, 1:-1][local]
        fade = np.clip(edge/max(2., .018*width), 0, 1)
        noise = rng.normal(0., .32, len(u))
        values = base+(relief*fade+noise)[:, None]
        out[target] = np.clip(np.floor(values+.5), 0, 255).astype(np.uint8)
        regions.append(dict(region_id=int(region_id), pixels=int(target.sum()),
            geometric_width_pixels=width, synthetic_pitch_pixels=float(pitch),
            pitch_is_measured=False, synthetic_pattern=family, color_field=field,
            source_ridge_phase_used=False, original_pixel_residual_used=False,
            mask_sha256=pixel_hash(target)))
    if not np.array_equal(out[~mask], rgb[~mask]):
        raise RuntimeError('synthetic_outside_mask_modified')
    return out, dict(version=VERSION, seed=seed, regions=regions,
        status='synthetic_replacement_applied' if mask.any() else 'no_replacement_regions',
        replacement_regions=len(regions), replaced_pixels=int(mask.sum()),
        actual_changed_pixels=int(np.any(out != rgb, axis=2).sum()),
        source_dependency='coarse_cell_RGB_medians_fitted_by_polynomial_degree_at_most_3',
        coarse_spatial_color_preserved=True, original_pixel_residual_used=False,
        source_alpha_inside_mask=0., edge_source_feathering=False, original_pitch_required=False,
        outside_mask_RGB_preserved=True, output_RGB_sha256=pixel_hash(out), mask_sha256=pixel_hash(mask),
        full_photo_protection_verified=False, privacy_validated=False,
        biometric_validation_performed=False, natural_appearance_validated=False, production_approved=False)
