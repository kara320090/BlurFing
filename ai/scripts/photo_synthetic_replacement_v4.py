"""Opaque synthetic ridges with locally reconstructed coarse skin appearance.

Source use is limited to cell RGB medians and unordered intensity spread. The
smooth appearance map is not a blurred copy or an alpha blend of source pixels.
Cell permutation invariance checks data flow, not general biometric privacy.
"""
import secrets
import numpy as np
from scipy import ndimage
from scipy.interpolate import RBFInterpolator
from scipy.spatial import cKDTree
from photo_resize_safety_v1 import validate_resize
from photo_rejection_resolution_v1 import pixel_hash
from photo_synthetic_replacement_v2 import geometry, color_cells, color_field
from photo_synthetic_replacement_v3 import photographic_relief

VERSION = 'opaque_local_skin_synthetic_replacement_v4_experimental'
MAX_REGIONS = 256
MAX_REGION_PIXELS = 4*1024*1024
MAX_BOUNDING_PIXELS = 8*1024*1024
APPEARANCE_GRID = 128


def boundary_distance(local):
    return ndimage.distance_transform_edt(np.pad(local, 1))[1:-1, 1:-1][local]


def boundary_geometry(local):
    distance = ndimage.distance_transform_edt(np.pad(local, 1))
    # Geometry only. Four normal sectors separate side/background boundaries
    # from proximal skin boundaries within a coarse cell at a corner.
    smooth = ndimage.gaussian_filter(distance, 1.2)
    dy, dx = np.gradient(smooth)
    dy, dx = dy[1:-1, 1:-1][local], dx[1:-1, 1:-1][local]
    sector = np.where(np.abs(dx) >= np.abs(dy), (dx >= 0).astype(int), 2+(dy >= 0).astype(int))
    return distance[1:-1, 1:-1][local], sector


def source_groups(cells, distance, width, sector):
    """Mask-only partition defining the permutation-invariance contract."""
    return cells*5+np.where(distance <= max(2., .004*width), sector+1, 0)


def boundary_appearance(base, pixels, u, v, width, length, distance, sector):
    """Blend two generated color fields, never a source-pixel feather.

    Boundary medians are aggregated along coarse cells inside the permission.
    A narrow, geometry-only transition avoids repainting a hard artificial rim.
    This deliberately retains more coarse boundary color than V3.
    """
    cells, nx, ny = color_cells(u, v, width, length)
    band = distance <= max(2., .004*width)
    coords, values, sectors = [], [], []
    groups = cells*4+sector
    for group in np.unique(groups[band]):
        take = (groups == group) & band
        if take.sum() < 8:
            continue
        coords.append([(u[take].mean()+1)*nx/2, (v[take].mean()+1)*ny/2])
        values.append(np.median(pixels[take], axis=0))
        sectors.append(int(group%4))
    meta = dict(method='coarse_inside_boundary_RGB_medians_by_normal_sector', populated_groups=len(values),
        maximum_statistics=nx*ny*4*3, sample_band_width=max(2., .004*width),
        generated_transition_width=max(3., .015*width), source_pixel_alpha=0.,
        original_phase_input=False, source_outside_permission_used=False)
    if len(coords) < 4:
        return base, meta | dict(applied=False, reason='insufficient_boundary_support')
    values, coords, sectors = np.array(values), np.array(coords), np.array(sectors)
    active = distance < meta['generated_transition_width']+1
    result = base.copy()
    reconstructed = 0
    for normal in range(4):
        nodes = sectors == normal
        if not nodes.any():
            continue
        tree = cKDTree(coords[nodes]); colors = values[nodes]
        indices = np.flatnonzero(active & (sector == normal))
        k = min(3, int(nodes.sum()))
        for start in range(0, len(indices), 65536):
            take = indices[start:start+65536]
            query = np.column_stack(((u[take]+1)*nx/2, (v[take]+1)*ny/2))
            delta, nearest = tree.query(query, k=k)
            delta, nearest = delta.reshape(-1, k), nearest.reshape(-1, k)
            weights = np.maximum(delta, .05)**-4
            weights /= weights.sum(axis=1, keepdims=True)
            boundary = np.sum(colors[nearest]*weights[:, :, None], axis=1)
            alpha = np.clip(1-(distance[take]-1)/meta['generated_transition_width'], 0, 1)**2
            result[take] = base[take]*(1-alpha[:, None])+boundary*alpha[:, None]
            reconstructed += len(take)
    if not np.isfinite(result).all():
        raise ValueError('synthetic_boundary_nonfinite')
    return result, meta | dict(applied=True, reconstructed_pixels=reconstructed,
        interpolation='positive_inverse_distance_weights_within_same_normal_sector', maximum_query_chunk=65536)


def local_appearance(pixels, u, v, width, length):
    """Reconstruct bounded smooth RGB and contrast from <=80 coarse cells.

    Positions/weights are mask-only. RBF is evaluated on a fixed grid, never
    an unbounded number of native pixels by 80 centres. Sampling is bilinear.
    """
    cells, nx, ny = color_cells(u, v, width, length)
    coords, stats, counts = [], [], []
    for cell in np.unique(cells):
        take = cells == cell
        if take.sum() < 16:
            continue
        values = pixels[take].astype(np.float64)
        gray = values @ np.array([.299, .587, .114])
        # Unordered distribution only: no high-pass/gradient/phase from source.
        mad = float(np.median(np.abs(gray-np.median(gray))))
        coords.append([(u[take].mean()+1)*nx/2, (v[take].mean()+1)*ny/2])
        stats.append([*np.median(values, axis=0), mad])
        counts.append(int(take.sum()))
    if len(stats) < 4 or np.linalg.matrix_rank(np.column_stack((np.ones(len(coords)), coords))) < 3:
        base, fallback = color_field(pixels, u, v, width, length)
        return base, np.full(len(u), .85), dict(method='insufficient_coarse_support_polynomial_fallback',
            populated_cells=len(stats), fallback=fallback, source_ridge_phase_used=False)
    nodes, values = np.array(coords), np.array(stats)
    smoothing = .15/np.clip(np.array(counts)/np.median(counts), .2, 1.)
    interpolator = RBFInterpolator(nodes, values, kernel='thin_plate_spline', degree=1, smoothing=smoothing)
    gy, gx = np.mgrid[:APPEARANCE_GRID, :APPEARANCE_GRID]
    query = np.column_stack((gx.ravel()*nx/(APPEARANCE_GRID-1), gy.ravel()*ny/(APPEARANCE_GRID-1)))
    maps = interpolator(query).reshape(APPEARANCE_GRID, APPEARANCE_GRID, 4)
    # No unbounded extrapolation or invented extreme colors at masked edges.
    maps = np.clip(maps, values.min(axis=0), values.max(axis=0))
    sample = np.vstack(((v+1)*(APPEARANCE_GRID-1)/2, (u+1)*(APPEARANCE_GRID-1)/2))
    sampled = np.column_stack([ndimage.map_coordinates(maps[:, :, k], sample,
        order=1, mode='nearest', prefilter=False) for k in range(4)])
    gain = np.clip(sampled[:, 3]*.32, .70, 1.20)
    if not np.isfinite(sampled).all():
        raise ValueError('synthetic_appearance_nonfinite')
    return sampled[:, :3], gain, dict(method='regularized_coarse_RGB_median_and_MAD_interpolation',
        grid=[nx, ny], populated_cells=len(stats), evaluation_grid=[APPEARANCE_GRID, APPEARANCE_GRID],
        cell_selection_min_pixels=16, maximum_source_statistics=nx*ny*4,
        source_statistics='RGB_median_and_luminance_MAD_within_each_cell',
        source_ridge_phase_used=False, high_frequency_source_residual_used=False,
        source_pixel_alpha=0., contrast_gain_range=[float(gain.min()), float(gain.max())])


def render(rgb, mask, labels, *, seed=None):
    if not isinstance(rgb, np.ndarray) or rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3:
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
        if target.sum() > MAX_REGION_PIXELS:
            raise ValueError('synthetic_region_pixel_limit')
        yy, xx, u, v, width, length = geometry(target)
        local = target[yy.min():yy.max()+1, xx.min():xx.max()+1]
        if local.size > MAX_BOUNDING_PIXELS:
            raise ValueError('synthetic_region_bbox_pixel_limit')
        if ndimage.label(local)[1] != 1:
            raise ValueError('synthetic_region_must_be_connected')
        base, gain, color = local_appearance(rgb[target], u, v, width, length)
        distance, sector = boundary_geometry(local)
        base, boundary = boundary_appearance(base, rgb[target], u, v, width, length, distance, sector)
        child_seed = int(np.random.SeedSequence([seed, int(region_id)]).generate_state(1, dtype=np.uint64)[0])
        relief, texture = photographic_relief(local, u, v, width, length, child_seed)
        grain = np.random.default_rng(child_seed ^ 0xE041).normal(0., 1., len(u))*(.45+.25*gain)
        out[target] = np.clip(np.floor(base+(gain*relief+grain)[:, None]+.5), 0, 255).astype(np.uint8)
        regions.append(dict(region_id=int(region_id), pixels=int(target.sum()),
            geometric_width_pixels=width, color_field=color, boundary_color=boundary, **texture,
            independent_native_grain=True,
            pitch_is_measured=False, source_ridge_phase_used=False,
            original_pixel_residual_used=False, mask_sha256=pixel_hash(target)))
    if not np.array_equal(out[~mask], rgb[~mask]):
        raise RuntimeError('synthetic_outside_mask_modified')
    return out, dict(version=VERSION, seed=seed, regions=regions,
        status='synthetic_replacement_applied' if mask.any() else 'no_replacement_regions',
        replacement_regions=len(regions), replaced_pixels=int(mask.sum()),
        unresolved_texture_regions=sum(not r['fingerprint_texture_resolved'] for r in regions),
        actual_changed_pixels=int(np.any(out != rgb, axis=2).sum()),
        source_dependency='coarse_cell_RGB_medians_luminance_MAD_and_inside_boundary_RGB_medians',
        source_permutation_partition='coarse_cell_intersected_with_inside_boundary_band_normal_sector_or_interior',
        coarse_spatial_color_preserved=True, original_pixel_residual_used=False,
        source_alpha_inside_mask=0., edge_source_feathering=False, original_pitch_required=False,
        outside_mask_RGB_preserved=True, output_RGB_sha256=pixel_hash(out), mask_sha256=pixel_hash(mask),
        full_photo_protection_verified=False, privacy_validated=False,
        biometric_validation_performed=False, natural_appearance_validated=False, production_approved=False)
