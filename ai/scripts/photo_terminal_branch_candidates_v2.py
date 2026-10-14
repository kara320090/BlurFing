"""Review-only terminal prefixes with per-pixel, explicit ownership uncertainty.

Same branch geometry as v1. A distance tie is unowned; it neither assigns an
arbitrary winner nor discards unrelated pixels from the entire candidate.
This does not resolve whether a free branch is anatomically a fingertip.
"""
import numpy as np
import photo_terminal_branch_candidates_v1 as shared

VERSION = 'photo_terminal_branch_candidates_v2_experimental'


def resolve_pixel_ownership(rows, shape):
    seen, overlap = np.zeros(shape, bool), np.zeros(shape, bool)
    for row in rows:
        mask = row.get('mask')
        if mask is not None:
            if not isinstance(mask, np.ndarray) or mask.dtype != np.bool_ or mask.shape != shape:
                raise ValueError('terminal_ownership_mask_contract_mismatch')
            overlap |= seen & mask
            seen |= mask
    for row in rows:
        mask = row.get('mask')
        if mask is None:
            continue
        ambiguous = int((mask & overlap).sum())
        row.update(ambiguous_working_pixels=ambiguous, ownership_policy='equal_distance_pixels_unowned',
                   topology_candidate_working_pixels=int(mask.sum()))
        unique = mask & ~overlap
        if unique.any():
            row['mask'] = unique
        else:
            row['reject_reason'] = 'terminal_unique_support_unavailable'
            del row['mask']
    return rows, int(overlap.sum())


def working_candidates(component):
    rows, topology = shared.raw_working_candidates(component)
    rows, ambiguous = resolve_pixel_ownership(rows, component.shape)
    topology.update(ambiguous_working_pixels=ambiguous,
                    ownership_policy='equal_distance_pixels_unowned')
    return rows, topology


def estimate(body, tip):
    result = shared.estimate(body, tip, _working_candidates=working_candidates,
                             _detector_version=VERSION)
    result.update(ownership_policy='equal_distance_pixels_unowned',
                  protection_of_ambiguous_pixels_allowed=False)
    return result
