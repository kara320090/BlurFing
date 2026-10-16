"""Opaque replacement with a reconstructed coarse skin surface (iteration 1).

V7 deliberately retains additional coarse source color/crease information.
Medians are interpolated, not raw or low-pass source pixels. This improves
appearance; it does not prove biometric information has been eliminated.
"""
import secrets
import numpy as np
from scipy import ndimage
from photo_resize_safety_v1 import validate_resize
from photo_rejection_resolution_v1 import pixel_hash
from photo_synthetic_replacement_v2 import geometry
from photo_synthetic_replacement_v4 import local_appearance
from photo_synthetic_replacement_v6 import continuous_boundary, texture_style, styled_relief

MAX_REGIONS = 256
MAX_REGION_PIXELS = 4*1024*1024
MAX_BOUNDING_PIXELS = 8*1024*1024


def skin_cells(u, v, width, length):
    nx = min(12, max(1, int(width)//56))
    ny = min(40, max(1, int(length)//24))
    x = np.clip(((u+1)*nx/2).astype(int), 0, nx-1)
    y = np.clip(((v+1)*ny/2).astype(int), 0, ny-1)
    return y*nx+x, nx, ny


def reconstructed_skin(pixels, u, v, width, length):
    """Reconstruct broad RGB structure using <=480 supported RGB medians."""
    cells, nx, ny = skin_cells(u, v, width, length)
    values = np.full((ny, nx, 3), np.nan)
    counts = np.zeros((ny, nx), int)
    for cell in np.unique(cells):
        take = cells == cell
        if take.sum() < 24:
            continue
        row, col = divmod(int(cell), nx)
        values[row, col] = np.median(pixels[take], axis=0)
        counts[row, col] = int(take.sum())
    valid = counts > 0
    meta = dict(method='coarse_RGB_median_surface_reconstruction', grid=[nx, ny],
        maximum_source_statistics=nx*ny*3, populated_cells=int(valid.sum()),
        minimum_cell_support=24, source_pixel_alpha=0., source_filtered_image_transferred=False,
        source_phase_transferred=False, retained_macro_appearance=True)
    if valid.sum() < 4 or nx < 2 or ny < 2:
        base, _, previous = local_appearance(pixels, u, v, width, length)
        return base, meta | dict(fallback=previous['method'])
    nearest = ndimage.distance_transform_edt(~valid, return_distances=False, return_indices=True)
    filled = values[tuple(nearest)]
    # Preserve broad folds and oblique shading; suppress cell noise/ridge alias.
    smooth = ndimage.gaussian_filter(filled, (.55, .60, 0), mode='nearest')
    sample = np.vstack(((v+1)*ny/2-.5, (u+1)*nx/2-.5))
    result = np.column_stack([ndimage.map_coordinates(smooth[:, :, k], sample,
        order=3, mode='nearest', prefilter=True) for k in range(3)])
    result = np.clip(result, values[valid].min(axis=0), values[valid].max(axis=0))
    return result, meta


def render_core(rgb, mask, labels, *, seed=None, version='v7', relief_fn=styled_relief,
                surface_fn=None):
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
        base, color = reconstructed_skin(pixels, u, v, width, length)
        base, boundary = continuous_boundary(base, pixels, u, v, width, length, local)
        energies, style = texture_style(pixels, local, u, v, width, length)
        child_seed = int(np.random.SeedSequence([seed, int(rid)]).generate_state(1, dtype=np.uint64)[0])
        relief, texture = relief_fn(local, u, v, width, length, child_seed, energies)
        grain = np.random.default_rng(child_seed ^ 0xE041).normal(0., .25, len(u))
        values = base+(relief+grain)[:, None]
        surface_meta = dict(applied=False)
        if surface_fn is not None:
            values, surface_meta = surface_fn(values, base, local, u, v, width, length, child_seed, energies)
        if values.shape != pixels.shape or not np.isfinite(values).all():
            raise ValueError('synthetic_generated_surface_nonfinite_or_shape_mismatch')
        out[target] = np.clip(np.floor(values+.5), 0, 255).astype(np.uint8)
        regions.append(dict(region_id=int(rid), pixels=int(target.sum()), geometric_width_pixels=width,
            color_field=color, boundary_color=boundary, texture_style=style, skin_surface=surface_meta, **texture,
            original_pixel_residual_used=False, mask_sha256=pixel_hash(target)))
    if not np.array_equal(out[~mask], rgb[~mask]):
        raise RuntimeError('synthetic_outside_mask_modified')
    return out, dict(version='opaque_reconstructed_skin_'+version+'_experimental', seed=seed, regions=regions,
        status='synthetic_replacement_applied' if mask.any() else 'no_replacement_regions',
        replacement_regions=len(regions), replaced_pixels=int(mask.sum()),
        macro_crease_count=0, macro_structure_method='coarse_median_surface_not_fitted_curve_count',
        unresolved_texture_regions=sum(not r['fingerprint_texture_resolved'] for r in regions),
        actual_changed_pixels=int(np.any(out != rgb, axis=2).sum()),
        source_dependency='coarse_RGB_surface_boundary_medians_and_isotropic_energy_pairs',
        original_pixel_residual_used=False, source_alpha_inside_mask=0., edge_source_feathering=False,
        original_pitch_required=False, source_permutation_invariance_claimed=False,
        coarse_spatial_color_preserved=True, outside_mask_RGB_preserved=True,
        output_RGB_sha256=pixel_hash(out), mask_sha256=pixel_hash(mask),
        full_photo_protection_verified=False, privacy_validated=False, biometric_validation_performed=False,
        natural_appearance_validated=False, production_approved=False)


def render(rgb, mask, labels, *, seed=None):
    return render_core(rgb, mask, labels, seed=seed)
