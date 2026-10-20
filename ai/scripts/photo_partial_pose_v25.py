"""Per-digit observed pose, with independent semantic TIP evidence.

Folded or occluded digits cannot invalidate another digit. This experimental
geometry is not anatomical truth or a ridge-visibility classifier. Source,
worker/model, BODY, and per-region raw-ridge checks remain authoritative.
"""
import numpy as np
from scipy import ndimage
from photo_resize_safety_v1 import validate_resize
from photo_pose_permissions_v1 import (
    DIGITS, PAIRS, _body_contract, _points, normalized_landmarks_to_native,
    tip_connected_component,
)

VERSION = 'semantic_tip_anchored_partial_pose_v25_experimental'


def partial_permissions(body, semantic_tip, native_xy):
    _body_contract(body)
    points = _points(native_xy)
    if (not isinstance(semantic_tip, np.ndarray) or semantic_tip.dtype != np.bool_
            or semantic_tip.shape != body.shape or np.any(semantic_tip & ~body)):
        raise ValueError('partial_pose_semantic_tip_contract')
    height, width = body.shape
    axes = []; skipped = []
    for label, ((tip_id, dip_id), digit) in enumerate(zip(PAIRS, DIGITS), 1):
        tip, dip = points[tip_id], points[dip_id]
        delta = tip - dip; squared = float(delta @ delta)
        reason = None
        if any(not (0 <= p[0] <= width - 1 and 0 <= p[1] <= height - 1) for p in (tip, dip)):
            reason = 'axis_endpoint_out_of_frame'
        elif not np.isfinite(squared) or squared <= 0:
            reason = 'positive_finite_axis_required'
        else:
            for name, p in (('tip', tip), ('midpoint', (tip + dip) / 2)):
                x, y = np.floor(p + .5).astype(int)
                if not body[y, x]:
                    reason = name + '_outside_BODY'; break
            x, y = np.floor(tip + .5).astype(int)
            if reason is None and not semantic_tip[y, x]:
                reason = 'observed_TIP_not_supported_by_semantic_TIP'
        if reason:
            skipped.append(dict(label=label, digit=digit, reason=reason)); continue
        axis = delta / np.sqrt(squared)
        axes.append(dict(label=label, digit=digit, tip_id=tip_id, DIP_or_IP_id=dip_id,
            tip_native_xy=tip.tolist(), DIP_or_IP_native_xy=dip.tolist(),
            axis_native_xy=axis.tolist(), axis_native_yx=axis[::-1].tolist(),
            length_native_pixels=float(np.sqrt(squared)),
            semantic_TIP_at_observed_TIP=True, anatomical_axis_ground_truth=False))
    diagnostic = dict(version=VERSION, selected_digits=[a['digit'] for a in axes],
        skipped_digits=skipped, GT_used=False, anatomical_wholepad_verified=False,
        privacy_validated=False, semantic_TIP_support_required=True)
    if not axes:
        return None, diagnostic
    owners = np.zeros(body.shape, np.uint8); proposed = np.zeros_like(owners)
    for y0 in range(0, height, 128):
        yy, xx = np.nonzero(body[y0:y0 + 128]); yy += y0
        pts = np.stack([xx, yy], axis=1).astype(np.float64)
        best = np.full(len(pts), np.inf); winner = np.zeros(len(pts), np.uint8)
        # Unselected digits reserve their finite geometric domains, but cannot
        # authorize protection. Otherwise one valid digit would own the whole
        # hand and rounding it could erase another digit's V6 proposal.
        for label, (tip_id, dip_id) in enumerate(PAIRS, 1):
            dip = points[dip_id]; delta = points[tip_id] - dip
            squared = float(delta @ delta)
            if not np.isfinite(squared) or squared <= 0:
                continue
            t = np.clip(((pts - dip) @ delta) / squared, 0., 1.)
            residual = pts - (dip + t[:, None] * delta)
            distance = np.einsum('ij,ij->i', residual, residual)
            take = distance < best
            best[take] = distance[take]; winner[take] = label
        owners[yy, xx] = winner
        for a in axes:
            dip = np.asarray(a['DIP_or_IP_native_xy']); delta = np.asarray(a['tip_native_xy']) - dip
            take = (winner == a['label']) & (((pts - dip) @ delta) >= 0.)
            proposed[yy[take], xx[take]] = a['label']
    permission = np.zeros_like(owners); rejected = np.zeros_like(owners)
    bound_axes = []
    for a in axes:
        x, y = np.floor(np.asarray(a['tip_native_xy']) + .5).astype(int)
        if proposed[y, x] != a['label']:
            diagnostic['skipped_digits'].append(dict(label=a['label'],digit=a['digit'],reason='observed_TIP_owner_conflict'))
            continue
        bound, unbound, detail = tip_connected_component(proposed == a['label'], a['tip_native_xy'])
        permission[bound] = a['label']; rejected[unbound] = a['label']
        a.update(detail)
        bound_axes.append(a)
    if len(bound_axes) != len(axes):
        axes = bound_axes
        proposed[~np.isin(proposed, [a['label'] for a in axes])] = 0
    diagnostic['selected_digits'] = [a['digit'] for a in axes]
    diagnostic['unselected_digit_domains_reserved'] = True
    if not axes:
        return None, diagnostic
    if (not np.array_equal(owners > 0, body) or
            not np.array_equal((permission > 0) | (rejected > 0), proposed > 0) or
            np.any((permission > 0) & (rejected > 0))):
        raise RuntimeError('partial_pose_partition_contract')
    return dict(owner_labels=owners, proposed_labels=proposed, permission_labels=permission,
                rejected_labels=rejected, axes=axes, metadata=diagnostic), diagnostic


def partition_candidates(mask, owners, selected_labels, *, maximum=128):
    """Touching candidates remain separate across observed digit ownership.

    Unassigned/unselected model suggestions are retained as separate review
    candidates. A rejected neighbour must not reject a valid digit atomically.
    """
    if (not isinstance(mask,np.ndarray) or mask.dtype != np.bool_ or mask.ndim != 2 or
            not isinstance(owners,np.ndarray) or owners.dtype != np.uint8 or owners.shape != mask.shape or
            not isinstance(selected_labels,list) or not selected_labels or
            selected_labels != sorted(set(selected_labels)) or
            any(type(i) is not int or not 1 <= i <= 5 for i in selected_labels) or
            type(maximum) is not int or not 1 <= maximum <= 128):
        raise ValueError('partial_pose_partition_candidates_contract')
    validate_resize(*mask.shape,1.)
    if np.any(owners > 5):raise ValueError('partial_pose_partition_candidates_contract')
    labels = np.zeros(mask.shape,np.uint16); count = 0
    domains = [owners == i for i in selected_labels]
    domains.append(~np.isin(owners,selected_labels))
    for domain in domains:
        cc, number = ndimage.label(mask & domain,np.ones((3,3),np.uint8))
        if count + number > maximum:
            raise ValueError('partial_pose_candidate_limit')
        take = cc > 0
        labels[take] = cc[take] + count
        count += number
    if not np.array_equal(labels > 0,mask):
        raise RuntimeError('partial_pose_candidate_pixel_loss')
    return labels, count


def geometry_from_worker(source, rgb, record):
    # Keep malformed, raced, foreign-source and unpinned worker records fatal.
    from photo_pose_native_pipeline_v1 import verify_worker
    from pad_refinement_data_contract_v2 import read_body, read_mask, native_shape
    verify_worker(source, rgb, record)
    if record['hand_count'] != 1:
        return None, dict(version=VERSION, selected_digits=[], skipped_digits=[],
            reason='exactly_one_observed_hand_required', hand_count=record['hand_count'])
    body = read_body(source)
    tip = read_mask(source['tip_path'], source['tip_sha256'], native_shape(source))
    native = normalized_landmarks_to_native(record['hands'][0]['normalized_xy'], body.shape,
                                            source['source_exif_orientation'])
    return partial_permissions(body, tip, native)
