"""Opaque synthetic ridges with continuous boundary color and coarse texture style.

V6 additionally observes isotropic band-energy summaries. These may depend on
source texture, but no source residual, phase, orientation or minutiae enter the
generated field. This data-flow restriction is not a biometric privacy proof.
"""
import secrets
import cv2
import numpy as np
from scipy import ndimage
from photo_resize_safety_v1 import validate_resize
from photo_rejection_resolution_v1 import pixel_hash
from photo_synthetic_replacement_v2 import geometry, color_cells
from photo_synthetic_replacement_v4 import local_appearance, boundary_geometry
from photo_synthetic_replacement_v5 import macro_creases, variable_relief

VERSION = 'opaque_continuous_boundary_local_texture_v6_experimental'
MAX_REGIONS = 256
MAX_REGION_PIXELS = 4*1024*1024
MAX_BOUNDING_PIXELS = 8*1024*1024


def smoothstep(x):
    x = np.clip(x, 0., 1.)
    return x*x*(3-2*x)


def continuous_boundary(base, pixels, u, v, width, length, local):
    """Interpolate coarse interior-boundary medians with continuous normals.

    All nodes participate with positive weights, avoiding nearest-neighbor and
    normal-sector switches in V4/V5. A smoothstep mixes generated fields only.
    The source sampling partition is unchanged; normal vectors are mask-only.
    """
    distance, sector = boundary_geometry(local)
    padded = ndimage.distance_transform_edt(np.pad(local, 1))
    dy, dx = np.gradient(ndimage.gaussian_filter(padded, max(1.2, width*.003)))
    normal = np.column_stack((dx[1:-1, 1:-1][local], dy[1:-1, 1:-1][local]))
    normal /= np.maximum(np.linalg.norm(normal, axis=1, keepdims=True), 1e-8)
    cells, nx, ny = color_cells(u, v, width, length)
    xy = np.column_stack((u*width/2, v*length/2))
    band = distance <= max(2., .004*width)
    groups = cells*4+sector
    nodes, colors, normals = [], [], []
    for group in np.unique(groups[band]):
        take = band & (groups == group)
        if take.sum() < 8:
            continue
        nodes.append(xy[take].mean(axis=0))
        colors.append(np.median(pixels[take], axis=0))
        n = normal[take].mean(axis=0)
        normals.append(n/max(np.linalg.norm(n), 1e-8))
    transition = max(3., .035*width)
    meta = dict(method='positive_continuous_normal_weighted_boundary_medians',
        populated_groups=len(nodes), sample_band_width=max(2., .004*width),
        generated_transition_width=transition, source_pixel_alpha=0.,
        source_outside_permission_used=False, maximum_query_chunk=2048)
    if len(nodes) < 4:
        return base, meta | dict(applied=False, reason='insufficient_boundary_support')
    nodes, colors, normals = np.array(nodes), np.array(colors), np.array(normals)
    active = np.flatnonzero(distance < transition+1)
    result = base.copy()
    reconstructed = 0
    radius = max(2., .12*min(width/nx, length/ny))
    for start in range(0, len(active), 2048):
        take = active[start:start+2048]
        delta = xy[take, None, :]-nodes[None, :, :]
        spatial = (np.sum(delta*delta, axis=2)+radius*radius)**-2
        # Opposite boundaries do not cross-contaminate; angular affinity is
        # continuous even where the four sampling sectors change.
        angular = np.maximum(normal[take] @ normals.T, 0.)**6
        weights = spatial*angular
        total = weights.sum(axis=1)
        good = total > 1e-20
        take = take[good]
        boundary = (weights[good] @ colors)/total[good, None]
        blend = smoothstep((distance[take]-1)/transition)
        result[take] = boundary*(1-blend[:, None])+base[take]*blend[:, None]
        reconstructed += len(take)
    if not np.isfinite(result).all():
        raise ValueError('synthetic_boundary_nonfinite')
    return result, meta | dict(applied=True, reconstructed_pixels=reconstructed,
        source_statistics_partition='V4_boundary_cells_and_normal_sectors')


def texture_style(pixels, local, u, v, width, length):
    """Observe <=48 coarse pairs of isotropic robust band energies.

    Work on a <=512px raster with masked normalization and interior support.
    No outside color enters the raster. Export scalar energies, not filtered
    source images. This is an appearance proxy, not calibrated focus/pitch.
    """
    h, w = local.shape
    scale = min(1., 512/max(h, w))
    shape = (max(1, round(w*scale)), max(1, round(h*scale)))
    weight = cv2.resize(local.astype(np.float32), shape, interpolation=cv2.INTER_AREA)
    maps = []
    for data in (pixels @ np.array([.299, .587, .114]), u, v):
        raster = np.zeros(local.shape, np.float32)
        raster[local] = data
        reduced = cv2.resize(raster, shape, interpolation=cv2.INTER_AREA)
        maps.append(reduced/np.maximum(weight, 1e-6))
    gray, umap, vmap = maps
    support = weight > .999
    pitch = max(2., width*scale/38.)  # geometry-only analysis scale
    distance = ndimage.distance_transform_edt(np.pad(support, 1))[1:-1, 1:-1]
    valid = distance >= max(2., pitch*.6)
    nx = min(6, max(1, int(width)//96))
    ny = min(8, max(1, int(length)//96))
    sample_x = np.clip(((umap+1)*nx/2).astype(int), 0, nx-1)
    sample_y = np.clip(((vmap+1)*ny/2).astype(int), 0, ny-1)
    bands = []
    filtered = []
    for sigma in (max(.5, pitch*.10), max(.8, pitch*.30), max(1.2, pitch*.60)):
        numerator = cv2.GaussianBlur(gray*weight, (0, 0), sigma, borderType=cv2.BORDER_REFLECT_101)
        denominator = cv2.GaussianBlur(weight, (0, 0), sigma, borderType=cv2.BORDER_REFLECT_101)
        filtered.append(numerator/np.maximum(denominator, 1e-6))
    bands = [filtered[0]-filtered[1], filtered[0]-filtered[2]]
    values = np.full((ny, nx, 2), np.nan)
    for row in range(ny):
        for col in range(nx):
            take = valid & (sample_x == col) & (sample_y == row)
            if take.sum() < 32:
                continue
            values[row, col] = [float(1.4826*np.median(np.abs(b[take]-np.median(b[take])))) for b in bands]
    observed = np.isfinite(values[:, :, 0])
    meta = dict(method='coarse_isotropic_two_band_robust_energy', grid=[nx, ny],
        analysis_shape=[shape[1], shape[0]], analysis_geometry_pitch=pitch,
        populated_cells=int(observed.sum()), minimum_support=32,
        source_filtered_image_transferred=False, source_phase_transferred=False,
        source_orientation_transferred=False, calibrated_focus_measurement=False)
    if not observed.any():
        values[:] = (.65, 1.2)
        meta['fallback'] = 'bounded_default_style_insufficient_interior'
    else:
        nearest = ndimage.distance_transform_edt(~observed, return_distances=False, return_indices=True)
        values = values[tuple(nearest)]
        values = ndimage.gaussian_filter(values, (.65, .65, 0), mode='nearest')
    values = np.clip(values, 0., 12.)
    meta['energy_pairs'] = values.tolist()
    return values, meta


def styled_relief(local, u, v, width, length, seed, energies):
    raw, meta = variable_relief(local, u, v, width, length, seed)
    ny, nx, _ = energies.shape
    positions = np.vstack(((v+1)*ny/2-.5, (u+1)*nx/2-.5))
    observed = np.column_stack([ndimage.map_coordinates(energies[:, :, i], positions,
        order=1, mode='nearest', prefilter=False) for i in range(2)])
    # A bounded design rule: weak source detail produces gentler new ridges.
    # The positive floor preserves synthetic texture even on flat inputs.
    target = np.clip(observed[:, 1]*.85, .70, 2.6)
    ratio = observed[:, 0]/np.maximum(observed[:, 1], .25)
    softness = np.clip((.65-ratio)/.45, 0., 1.)
    if not meta['fingerprint_texture_resolved']:
        return raw, meta | dict(texture_style_applied=False, style_RMS_range=[float(target.min()), float(target.max())])
    # Blur only an independently generated field, never source RGB.
    h, w = local.shape
    scale = min(1., 512/max(h, w)); shape = (max(1, round(w*scale)), max(1, round(h*scale)))
    weight = cv2.resize(local.astype(np.float32), shape, interpolation=cv2.INTER_AREA)
    raster = np.zeros(local.shape, np.float32); raster[local] = raw
    small = cv2.resize(raster, shape, interpolation=cv2.INTER_AREA)
    sigma = max(.55, meta['synthetic_pitch_pixels']*scale*.18)
    numerator = cv2.GaussianBlur(small, (0, 0), sigma, borderType=cv2.BORDER_REFLECT_101)
    denominator = cv2.GaussianBlur(weight, (0, 0), sigma, borderType=cv2.BORDER_REFLECT_101)
    soft = cv2.resize(numerator/np.maximum(denominator, 1e-6), (w, h), interpolation=cv2.INTER_LINEAR)[local]
    value = raw*(1-softness)+soft*softness
    distance = ndimage.distance_transform_edt(np.pad(local, 1))[1:-1, 1:-1][local]
    interior = distance > max(2., .025*width)
    normalization = max(.1, float(value[interior].std() if interior.any() else value.std()))
    value = value/normalization*target
    # Smoothly attenuate at the edge, leaving a generated color field there.
    value *= smoothstep((distance-1)/max(2., .018*width))
    return value, meta | dict(texture_style_applied=True,
        style_RMS_range=[float(target.min()), float(target.max())],
        generated_softening_range=[float(softness.min()), float(softness.max())],
        source_intensity_array_used_by_ridge_generator=False,
        original_intensities_used_by_relief=True,
        style_input='coarse_scalar_band_energies_only', relief_RMS=float(value.std()))


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
    for rid in ids:
        target = labels == rid
        if target.sum() > MAX_REGION_PIXELS:
            raise ValueError('synthetic_region_pixel_limit')
        yy, xx, u, v, width, length = geometry(target)
        local = target[yy.min():yy.max()+1, xx.min():xx.max()+1]
        if local.size > MAX_BOUNDING_PIXELS:
            raise ValueError('synthetic_region_bbox_pixel_limit')
        if ndimage.label(local)[1] != 1:
            raise ValueError('synthetic_region_must_be_connected')
        pixels = rgb[target]
        base, _, color = local_appearance(pixels, u, v, width, length)
        correction, crease_strength, creases = macro_creases(pixels, base, u, v, width, length)
        base, boundary = continuous_boundary(base+correction[:, None], pixels, u, v, width, length, local)
        energies, style = texture_style(pixels, local, u, v, width, length)
        child_seed = int(np.random.SeedSequence([seed, int(rid)]).generate_state(1, dtype=np.uint64)[0])
        relief, texture = styled_relief(local, u, v, width, length, child_seed, energies)
        grain = np.random.default_rng(child_seed ^ 0xE041).normal(0., .25, len(u))
        values = base+((1-.55*crease_strength)*relief+grain)[:, None]
        out[target] = np.clip(np.floor(values+.5), 0, 255).astype(np.uint8)
        regions.append(dict(region_id=int(rid), pixels=int(target.sum()), geometric_width_pixels=width,
            color_field=color, boundary_color=boundary, macro_creases=creases, texture_style=style, **texture,
            pitch_is_measured=False, source_ridge_phase_used=False, original_pixel_residual_used=False,
            mask_sha256=pixel_hash(target)))
    if not np.array_equal(out[~mask], rgb[~mask]):
        raise RuntimeError('synthetic_outside_mask_modified')
    return out, dict(version=VERSION, seed=seed, regions=regions,
        status='synthetic_replacement_applied' if mask.any() else 'no_replacement_regions',
        replacement_regions=len(regions), replaced_pixels=int(mask.sum()),
        macro_crease_count=sum(len(r['macro_creases']['curves']) for r in regions),
        unresolved_texture_regions=sum(not r['fingerprint_texture_resolved'] for r in regions),
        actual_changed_pixels=int(np.any(out != rgb, axis=2).sum()),
        source_dependency='V5_coarse_color_and_crease_summaries_plus_coarse_isotropic_band_energy_pairs',
        coarse_spatial_color_preserved=True, original_pixel_residual_used=False,
        source_alpha_inside_mask=0., edge_source_feathering=False, original_pitch_required=False,
        source_permutation_invariance_claimed=False,
        outside_mask_RGB_preserved=True, output_RGB_sha256=pixel_hash(out), mask_sha256=pixel_hash(mask),
        full_photo_protection_verified=False, privacy_validated=False, biometric_validation_performed=False,
        natural_appearance_validated=False, production_approved=False)
