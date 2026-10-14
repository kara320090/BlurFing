"""Geometry-only terminal-branch experiment, never a production protection mask.

No RGB/GT input and no semantic-tip union. Existing 512 working side, 1.35
width extent, 4px width and 1.1 elongation checks are reused without tuning.
Nearest skeleton support is review evidence, not anatomical finger identity.
"""
import math
import cv2
import numpy as np
from scipy import ndimage
from skimage.morphology import skeletonize
from finger_body_distal_estimator import (WORKING_SIDE, PAD_WIDTH_MULTIPLIER,
                                        validate_candidate_context_allocation)
from photo_resize_safety_v1 import validate_resize

VERSION = 'photo_terminal_branch_candidates_v1_experimental'


def skeleton_graph(skeleton):
    """Undirected pixel graph without diagonal shortcuts across a grid corner."""
    coords = np.argwhere(skeleton)
    lookup = {tuple(p): i for i, p in enumerate(coords)}
    neighbors = [[] for _ in coords]
    for i, (y, x) in enumerate(coords):
        for dy in [-1, 0, 1]:
            for dx in [-1, 0, 1]:
                if not (dy or dx):
                    continue
                j = lookup.get((y+dy, x+dx))
                if j is None:
                    continue
                if dy and dx and ((y+dy, x) in lookup or (y, x+dx) in lookup):
                    continue
                neighbors[i].append(j)
        neighbors[i].sort()
    return coords, neighbors


def terminal_paths(coords, neighbors):
    """Keep each endpoint-to-first-junction path; loops do not invent a tip."""
    rows = []
    for endpoint, adjacent in enumerate(neighbors):
        if len(adjacent) != 1:
            continue
        path, previous, current = [endpoint], None, endpoint
        while True:
            choices = [j for j in neighbors[current] if j != previous]
            if len(choices) != 1:
                break
            following = choices[0]
            if following in path:
                raise ValueError('terminal_path_cycle')
            path.append(following)
            previous, current = current, following
            if len(neighbors[current]) != 2:
                break
        points = coords[path]
        arc = np.r_[0., np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))]
        rows.append(dict(endpoint_index=endpoint, path_indices=path,
                         points=points, arc=arc,
                         ends_at_junction=len(neighbors[current]) > 2))
    return rows


def observed_terminal_cap(component, points, arc):
    """Follow the outward terminal direction to the first observed body exit."""
    if len(points) < 2 or arc[-1] <= 0:
        raise ValueError('terminal_direction_unobserved')
    interior = min(len(points)-1, max(1, int(np.searchsorted(arc, .25*arc[-1]))))
    direction = points[0].astype(float)-points[interior]
    length = float(np.linalg.norm(direction))
    if length == 0 or not np.isfinite(length):
        raise ValueError('terminal_direction_unobserved')
    direction /= length
    height, width = component.shape
    last = points[0].copy()
    for step in range(1, math.ceil(math.hypot(height, width))+2):
        point = np.rint(points[0]+step*direction).astype(int)
        y, x = point
        if not (0 <= y < height and 0 <= x < width) or not component[y, x]:
            break
        last = point
    else:
        raise ValueError('terminal_body_exit_unobserved')
    cut = bool(last[0] in [0, height-1] or last[1] in [0, width-1])
    return dict(cap_working_yx=last.tolist(),
                cap_offset=float(np.linalg.norm(last-points[0])),
                frame_cut=cut, outward_direction_yx=direction.tolist())


def prune_junction_contained_spurs(skeleton, distance):
    """Remove terminal paths whose whole arc fits inside the estimated radius.

    This changes the internal skeleton only. The body and tip masks are never
    cleaned or filled. The existing OpenCV DIST_L2/mask5 radius is approximate;
    this is an engineering spur criterion, not an anatomical proof. No fitted
    cutoff is used.
    """
    skeleton = skeleton.copy()
    removed, iterations = 0, 0
    while True:
        coords, graph = skeleton_graph(skeleton)
        paths = terminal_paths(coords, graph)
        discard = np.zeros_like(skeleton)
        for path in paths:
            if not path['ends_at_junction']:
                continue
            points = path['points']; y, x = points[-1]
            if path['arc'][-1] <= float(distance[y, x]):
                discard[points[:-1, 0], points[:-1, 1]] = True
        count = int(discard.sum())
        if not count:
            return skeleton, dict(internal_spur_pixels_removed=removed, pruning_iterations=iterations,
                                  pruning_policy='terminal_arc_contained_within_observed_junction_radius')
        skeleton[discard] = False
        removed += count; iterations += 1


def raw_working_candidates(component):
    skeleton = skeletonize(component)
    distance = cv2.distanceTransform(np.pad(component.astype(np.uint8), 1),
                                    cv2.DIST_L2, 5)[1:-1, 1:-1]
    skeleton, pruning = prune_junction_contained_spurs(skeleton, distance)
    coords, graph = skeleton_graph(skeleton)
    paths = terminal_paths(coords, graph)
    if not paths:
        return [], dict(skeleton_pixels=int(skeleton.sum()), terminal_count=0,
                        reason='skeleton_endpoints_unobserved', **pruning)
    nearest_all = ndimage.distance_transform_edt(~skeleton)
    rows = []
    for path in paths:
        points, arc = path['points'], path['arc']
        row = dict(endpoint_working_yx=points[0].tolist(),
                   branch_length_working=float(arc[-1]),
                   ends_at_junction=path['ends_at_junction'], reject_reason=None)
        rows.append(row)
        try:
            cap = observed_terminal_cap(component, points, arc)
            row.update(cap)
            if cap['frame_cut']:
                raise ValueError('terminal_truncated_by_image_frame')
            total_length = float(arc[-1]+cap['cap_offset'])
            if total_length < 12:
                raise ValueError('finger_too_short')
            reference = (arc >= .10*arc[-1]) & (arc <= .25*arc[-1])
            if not reference.any():
                raise ValueError('width_profile_unstable')
            samples = points[reference]
            observed_width = float(np.median(2*distance[samples[:, 0], samples[:, 1]]))
            row.update(reference_width_working=observed_width,
                       width_source='terminal_branch_local_distance_transform',
                       tip_to_junction_length_working=total_length)
            if observed_width < 4 or total_length/observed_width < 1.1:
                raise ValueError('finger_width_unstable')
            extent = min(total_length, PAD_WIDTH_MULTIPLIER*observed_width)
            prefix = (arc+cap['cap_offset']) <= extent
            # A junction is shared topology, never owned by an endpoint.
            if path['ends_at_junction']:
                prefix[-1] = False
            seeds = points[prefix]
            if not len(seeds):
                raise ValueError('empty_terminal_prefix')
            selected = np.zeros(component.shape, bool)
            selected[seeds[:, 0], seeds[:, 1]] = True
            # Both EDT rasters measure distance to observed skeleton pixels.
            # Exact equality avoids choosing a first/last owner for a tie.
            nearest_prefix = ndimage.distance_transform_edt(~selected)
            mask = component & (nearest_prefix == nearest_all)
            if not mask.any():
                raise ValueError('empty_terminal_candidate')
            row.update(mask=mask, distal_extent_working=extent,
                       nearest_support_semantics='nearest terminal-prefix skeleton, not anatomical pad')
        except ValueError as error:
            row['reject_reason'] = str(error)
    return rows, dict(skeleton_pixels=int(skeleton.sum()), terminal_count=len(paths),
                      junction_pixels=sum(len(adjacent) > 2 for adjacent in graph),
                      reason=None, **pruning)


def working_candidates(component):
    rows, topology = raw_working_candidates(component)
    # Equal-distance pixels can qualify for multiple branches. Preserve the
    # ambiguity and reject all affected candidates, never assign to an index.
    seen, overlap = np.zeros(component.shape, bool), np.zeros(component.shape, bool)
    for row in rows:
        if row.get('mask') is not None:
            overlap |= seen & row['mask']
            seen |= row['mask']
    for row in rows:
        mask = row.get('mask')
        if mask is not None and np.any(mask & overlap):
            row['reject_reason'] = 'terminal_nearest_support_ambiguous'
            row['ambiguous_pixels'] = int((mask & overlap).sum())
            del row['mask']
    return rows, topology


def estimate(body, tip, *, _working_candidates=None, _detector_version=VERSION):
    """Observe branches in encoded source pixels; never feeds a renderer."""
    if (not isinstance(body, np.ndarray) or not isinstance(tip, np.ndarray) or
            body.ndim != 2 or tip.shape != body.shape or body.dtype != np.bool_ or
            tip.dtype != np.bool_ or min(body.shape) < 1):
        raise ValueError('boolean_semantic_masks_required')
    height, width = body.shape
    validate_resize(height, width, 1.)
    if np.any(tip & ~body):
        raise ValueError('tip_outside_finger_body')
    scale = min(1., WORKING_SIDE/max(body.shape))
    shape, audit = validate_resize(height, width, scale)
    small = cv2.resize(body.astype(np.uint8), (shape[1], shape[0]),
                       interpolation=cv2.INTER_NEAREST) > 0
    labels, count = ndimage.label(small)
    combined, rows, components = np.zeros(body.shape, bool), [], []
    for component_id in range(1, count+1):
        component = labels == component_id
        # Same existing coarse-component criterion, no new fragment threshold.
        if component.sum() < .0001*small.size:
            continue
        candidates, topology = (_working_candidates or working_candidates)(component)
        components.append(dict(component=component_id, **topology))
        for index, candidate in enumerate(candidates, 1):
            row = {k:v for k, v in candidate.items() if k != 'mask'}
            row.update(candidate_id=f'body-{component_id:04d}-terminal-{index:04d}',
                       component=component_id, working_scale=scale,
                       actual_resize_yx=[shape[0]/height, shape[1]/width])
            if candidate['reject_reason'] is None:
                validate_candidate_context_allocation(height, width, len(rows)+1)
                native = cv2.resize(candidate['mask'].astype(np.uint8), (width, height),
                                    interpolation=cv2.INTER_NEAREST) > 0
                native &= body
                if not native.any():
                    row['reject_reason'] = 'empty_native_terminal_candidate'
                else:
                    y, x = np.where(native)
                    row.update(mask=native, mask_pixels=int(native.sum()),
                        semantic_tip_overlap_pixels=int((native & tip).sum()),
                        bbox_encoded_source_xyxy=[int(x.min()), int(y.min()), int(x.max())+1, int(y.max())+1])
                    if np.any(native & combined):
                        raise ValueError('native_terminal_ownership_overlap')
                    combined |= native
            rows.append(row)
    return dict(mask=combined, regions=rows, components=components,
                detector_version=_detector_version, working_shape=list(shape), resize_audit=audit,
                coordinate_system='encoded_original_pixels',
                semantic_tip_used_for_selection=False, semantic_tip_union_applied=False,
                approved_for_use=False, renderer_binding_allowed=False,
                protection_applied=False, candidate_semantics='free body terminal branches, not confirmed fingers')
