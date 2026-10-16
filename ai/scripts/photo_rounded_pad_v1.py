"""Optional direction-aware whole-pad geometry, independent of ridge pitch.

Partition before fitting: never round a merged multi-finger union. Observed
TIP/IP-DIP axes are preferred; without a pose, use the local candidate axis
and retain existing protection because an actual joint was not observed.
A flat joint cut, parallel
sides and a semicircular distal cap are intersected with observed BODY.
This is a shape prior, not a measured joint or verified fingerprint coverage.
"""
import numpy as np
from scipy import ndimage
from finger_body_distal_estimator import estimate, PAD_WIDTH_MULTIPLIER
from photo_candidate_context_v1 import candidate_contexts
from photo_native_owner_context_v1 import restore_contexts
from photo_resize_safety_v1 import validate_resize

VERSION = 'rounded_distal_pad_v1_experimental'


def _mask(a):
    if not isinstance(a, np.ndarray) or a.dtype != np.bool_ or a.ndim != 2 or min(a.shape) < 1:
        raise ValueError('rounded_boolean_mask_required')
    validate_resize(*a.shape, 1.)


def _point(a):
    raw = np.asarray(a)
    if raw.shape != (2,) or raw.dtype.kind not in 'iuf' or not np.isfinite(raw).all():
        raise ValueError('rounded_finite_xy_required')
    return raw.astype(np.float64)


def _sample(owner, points):
    # Pixel-center convention matches the existing pose geometry contract.
    p = np.floor(points + .5).astype(np.int64)
    valid = (p[:, 0] >= 0) & (p[:, 0] < owner.shape[1]) & (p[:, 1] >= 0) & (p[:, 1] < owner.shape[0])
    hit = np.zeros(len(points), bool)
    hit[valid] = owner[p[valid, 1], p[valid, 0]]
    return hit, valid


def _ray(owner, start, direction):
    distance = np.arange(0., np.hypot(*owner.shape) + 1., .5)
    hit, valid = _sample(owner, start + distance[:, None] * direction)
    if not hit[0]:
        raise ValueError('rounded_axis_outside_owner')
    outside = np.flatnonzero(~hit)
    if not len(outside) or not valid[outside[0]]:
        raise ValueError('rounded_boundary_clipped_by_frame')
    i = int(outside[0])
    return float((distance[i] + distance[i-1]) / 2.)


def round_cap(owner, joint_xy, tip_xy):
    """Fit one cap in native coordinates, bounded by its observed owner.

Width is the median of three contiguous perpendicular sections at 1/4, 1/2,
3/4 of the joint-to-tip segment. No far-away pixels or area/CC-size ranking
enter the estimate. The top is anchored to the first observed axial boundary.
"""
    _mask(owner)
    joint, tip = _point(joint_xy), _point(tip_xy)
    for point in (joint, tip):
        if np.any(point < 0) or point[0] > owner.shape[1]-1 or point[1] > owner.shape[0]-1:
            raise ValueError('rounded_axis_out_of_frame')
    delta = tip - joint
    length = float(np.linalg.norm(delta))
    if not np.isfinite(length) or length < 1.:
        raise ValueError('rounded_positive_axis_required')
    axis = delta / length
    normal = np.array([-axis[1], axis[0]])
    sections = []
    for fraction in (.25, .5, .75):
        center = joint + fraction * delta
        left, right = _ray(owner, center, -normal), _ray(owner, center, normal)
        sections.append((left, right))
    left, right = np.median(np.array(sections), axis=0)
    radius = float((left + right) / 2.)
    if radius < 1.:
        raise ValueError('rounded_width_unavailable')
    offset = float((right - left) / 2.)
    # Recenter on the observed shaft, never on a distant component's centroid.
    top_start = tip + normal * offset
    extension = _ray(owner, top_start, axis)
    end = length + extension
    cap_height = min(radius, end)
    corners = np.array([joint + normal*(offset+s*radius) + axis*t for s in (-1, 1) for t in (0., end)])
    x0, y0 = np.maximum(np.floor(corners.min(0)).astype(int)-1, 0)
    x1, y1 = np.minimum(np.ceil(corners.max(0)).astype(int)+2, [owner.shape[1], owner.shape[0]])
    result = np.zeros_like(owner)
    for y in range(y0, y1, 128):
        yy, xx = np.mgrid[y:min(y+128, y1), x0:x1]
        dx, dy = xx-joint[0], yy-joint[1]
        longitudinal = dx*axis[0] + dy*axis[1]
        lateral = dx*normal[0] + dy*normal[1] - offset
        top = end-cap_height + cap_height*np.sqrt(np.maximum(0., 1.-(lateral/radius)**2))
        result[y:min(y+128, y1), x0:x1] = (longitudinal >= 0.) & (np.abs(lateral) <= radius) & (longitudinal <= top)
    result &= owner
    # Retain only the part containing this observed/inferred tip anchor.
    x, y = np.floor(tip+.5).astype(int)
    if not result[y, x]:
        raise ValueError('rounded_tip_excluded_by_geometry')
    labels, count = ndimage.label(result)
    result = labels == labels[y, x]
    return result, dict(joint_xy=joint.tolist(), tip_xy=tip.tolist(), axis_xy=axis.tolist(),
        reference_width=float(2*radius), distal_extent=end, cap_height=cap_height,
        width_sections=[list(v) for v in sections], lateral_offset=offset,
        removed_detached_components=int(count-1), pixels=int(result.sum()))


def _inferred_axis(context):
    parent, owner, pad = context['parent'], context['body'], context['pad']
    if context['reject_reason'] is not None or pad is None:
        raise ValueError('rounded_estimator_candidate_rejected')
    parent_axis = np.asarray(parent['major_axis_yx'], np.float64)[::-1]  # towards proximal
    scale = float(parent['working_scale'])
    width = float(parent['reference_width']) / scale
    if not np.isfinite(width) or width <= 0 or not np.isfinite(parent_axis).all():
        raise ValueError('rounded_estimator_scale_contract')
    yy, xx = np.nonzero(pad)
    if len(xx) < 3:
        raise ValueError('rounded_local_axis_unavailable')
    # A hand/palm can skew the parent's major axis. Estimate local pad shape,
    # using the parent only to disambiguate the distal/proximal direction.
    _, vectors = np.linalg.eigh(np.cov(np.stack([xx, yy])))
    axis = vectors[:, np.argmax(np.abs(vectors.T @ parent_axis))]
    if axis @ parent_axis < 0:
        axis = -axis
    t = xx*axis[0] + yy*axis[1]
    normal = np.array([-axis[1], axis[0]])
    u = xx*normal[0] + yy*normal[1]
    top = float(t.min())
    selected = (t >= top+.25*width) & (t <= top+.75*width)
    if not selected.any():
        raise ValueError('rounded_estimator_section_unavailable')
    mid = float(np.median(u[selected]))
    # Do not inherit an unbounded class-2 extension or concatenate other owners.
    depth = min(PAD_WIDTH_MULTIPLIER*width, float(t.max()-top))
    joint = axis*(top+depth) + normal*mid
    anchor = axis*(top+.25*width) + normal*mid
    return joint, anchor


def rounded_pads(base, coarse, body, tip, *, pose_geometry=None):
    """Replace each eligible owner by a whole cap; report unresolved owners.

    The result does NOT intersect with V6 again (which would restore its holes).
    Only a pose joint permits subtractive replacement. Without an observed
    joint, caps can supplement but never remove existing protected pixels.
    For an unresolved owner, retain base rather than invent an anatomical axis.
"""
    _mask(base)
    for a in (coarse, body, tip):
        _mask(a)
        if a.shape != base.shape:
            raise ValueError('rounded_shape_mismatch')
    if np.any((base | coarse | tip) & ~body):
        raise ValueError('rounded_input_outside_body')
    output = base.copy()
    rows = []
    if pose_geometry is not None:
        owners = pose_geometry['owner_labels']
        if owners.shape != body.shape or owners.dtype.kind not in 'iu' or not np.array_equal(owners > 0, body):
            raise ValueError('rounded_pose_partition_contract')
        axes = pose_geometry['axes']
        if [a['label'] for a in axes] != [1, 2, 3, 4, 5] or np.any(owners > 5):
            raise ValueError('rounded_pose_digit_contract')
        contexts = [dict(candidate_id='pose-'+a['digit'], body=owners == a['label'],
            joint=a['DIP_or_IP_native_xy'], tip=a['tip_native_xy']) for a in axes]
        axis_source = 'observed_pose_IP_DIP_to_TIP'
    else:
        estimated = estimate(body, tip, preserve_candidates=True)
        if not np.array_equal(coarse, estimated['mask']):
            raise ValueError('rounded_coarse_binding_mismatch')
        contexts = restore_contexts(candidate_contexts(estimated, body), body)
        axis_source = 'local_candidate_axis_not_observed_joint'
    for context in contexts:
        owner = context['body']
        record = dict(candidate_id=context['candidate_id'], axis_source=axis_source,
            before_pixels=int((base & owner).sum()))
        try:
            joint, anchor = (context['joint'], context['tip']) if pose_geometry is not None else _inferred_axis(context)
            cap, detail = round_cap(owner, joint, anchor)
        except ValueError as error:
            record.update(status='base_retained', reason=str(error), after_pixels=record['before_pixels'])
        else:
            if pose_geometry is None:
                cap |= base & owner
            output[owner] = cap[owner]
            record.update(status='rounded_cap_applied', reason=None, after_pixels=int(cap.sum()), geometry=detail,
                base_preserved=pose_geometry is None)
        rows.append(record)
    if np.any(output & ~body):
        raise RuntimeError('rounded_output_outside_body')
    return output, dict(version=VERSION, candidates=rows, axis_source=axis_source,
        added_pixels=int((output & ~base).sum()), removed_pixels=int((base & ~output).sum()),
        applied_caps=sum(r['status'] == 'rounded_cap_applied' for r in rows),
        unresolved_candidates=sum(r['status'] == 'base_retained' for r in rows),
        GT_used=False, learned_mask_intersection=False, review_required=True,
        anatomical_boundary_verified=False, whole_photo_protection_verified=False)
