"""Rounded permissions + explicit owner axes + unchanged V12 native RGB gate.

Detection is not a successful protection. Each connected permission component
needs its own pitch/structure evidence; rejected regions retain source RGB.
"""
import numpy as np
from scipy import ndimage
import photo_learned_pad_pipeline_v1 as base
from photo_learned_pad_pipeline_v12 import prepare_scoped_region
from photo_resize_safety_v1 import validate_resize
from pad_refinement_data_contract_v2 import verify_source, read_source_rgb, read_body, read_mask, native_shape
from finger_body_distal_estimator import estimate
from photo_candidate_context_v1 import candidate_contexts
from photo_native_owner_context_v1 import restore_contexts

VERSION = 'rounded_pad_native_protection_v1_experimental'


def protection_contexts(body, tip, rounding, pose_geometry=None, *, complete_native_edges=False):
    rows = rounding['candidates']
    if pose_geometry is None:
        contexts = restore_contexts(candidate_contexts(estimate(body, tip, preserve_candidates=True), body), body)
        if complete_native_edges:
            from photo_native_partition_edges_v1 import restore_edges
            contexts = restore_edges(contexts,body)
        owners = {c['candidate_id']: c['body'] for c in contexts}
    else:
        owners = {'pose-'+a['digit']: pose_geometry['owner_labels'] == a['label'] for a in pose_geometry['axes']}
    if len(rows) != len(owners) or len({r['candidate_id'] for r in rows}) != len(rows) or {r['candidate_id'] for r in rows} != set(owners):
        raise ValueError('rounded_protection_owner_identity_mismatch')
    result = []
    for row in rows:
        applied = row['status'] == 'rounded_cap_applied'
        axis = row['geometry']['axis_xy'][::-1] if applied else None
        result.append(dict(candidate_id=row['candidate_id'], body=owners[row['candidate_id']],
            axis_native_yx=axis, reason=None if applied else 'rounded_geometry_unresolved'))
    return result


def connected_partition(mask, contexts):
    """Represent every permission pixel once; never merge disconnected evidence."""
    if not isinstance(mask, np.ndarray) or mask.dtype != np.bool_ or mask.ndim != 2 or min(mask.shape) < 1:
        raise ValueError('rounded_protection_mask_contract')
    validate_resize(*mask.shape, 1.)
    if not isinstance(contexts, list) or len(contexts) > base.MAX_COMPONENTS:
        raise ValueError('rounded_protection_context_limit')
    coverage = np.zeros(mask.shape, np.uint16)
    winner = np.zeros_like(coverage)
    ids = set()
    for i, context in enumerate(contexts, 1):
        owner, identity = context['body'], context['candidate_id']
        if (not isinstance(owner, np.ndarray) or owner.dtype != np.bool_ or owner.shape != mask.shape or
                not isinstance(identity, str) or identity in ids):
            raise ValueError('rounded_protection_context_contract')
        ids.add(identity)
        if context['reason'] is None:
            axis = np.asarray(context['axis_native_yx'], np.float64)
            if axis.shape != (2,) or not np.isfinite(axis).all() or not 0 < np.linalg.norm(axis) < np.inf:
                raise ValueError('rounded_protection_axis_contract')
        inside = mask & owner
        coverage[inside] += 1
        winner[inside] = i
    labels = np.zeros_like(coverage)
    records = []

    def add(native, identity, reason, context=None):
        local, count = ndimage.label(native)
        if len(records)+count > base.MAX_COMPONENTS:
            raise ValueError('rounded_protection_component_limit')
        for part, window in enumerate(ndimage.find_objects(local), 1):
            component = len(records)+1
            region = local[window] == part
            labels[window][region] = component
            cid = f'{identity}:permission-{part:04d}'
            association = None if reason else dict(candidate_id=cid,
                axis_native_yx=list(context['axis_native_yx']), anatomical_owner_verified=False,
                association_policy='same_owner_as_rounded_detection; connected_permission_local_evidence')
            records.append(dict(candidate_id=cid, reason=reason, association=association,
                owner=None if context is None else context['body'],
                plan=dict(component=component, status='planned' if reason is None else 'rejected',
                    reject_reason=reason, working_scale=1., mask_pixels=int(region.sum()))))
    for i, context in enumerate(contexts, 1):
        add(mask & (coverage == 1) & (winner == i), context['candidate_id'], context['reason'], context)
    add(mask & (coverage == 0), 'unassigned', 'rounded_protection_owner_unavailable')
    add(mask & (coverage > 1), 'ambiguous', 'rounded_protection_owner_ambiguous')
    if not np.array_equal(labels > 0, mask):
        raise ValueError('rounded_protection_pixel_loss')
    return dict(labels=labels, records=records)


def evaluate(source, mask, expected_pixel_sha256, rounding, *, pose_geometry=None, detect_only=False):
    if type(detect_only) is not bool:
        raise ValueError('detect_only_flag_must_be_boolean')
    if any(k.startswith('GT') for k in source):
        raise ValueError('GT_fields_forbidden_in_rounded_protection')
    verify_source(source, 'inference')
    rgb = read_source_rgb(source['source_path'], source['source_sha256'])
    body = read_body(source)
    tip = read_mask(source['tip_path'], source['tip_sha256'], native_shape(source))
    if (not isinstance(mask, np.ndarray) or mask.dtype != np.bool_ or mask.shape != body.shape or
            base.pixel_hash(mask) != expected_pixel_sha256 or np.any(mask & ~body)):
        raise ValueError('rounded_protection_mask_binding_mismatch')
    policy=rounding.get('native_owner_edge_policy')
    if policy not in (None,'unique_native_quantization_band_v1'):
        raise ValueError('rounded_protection_unknown_native_edge_policy')
    contexts = protection_contexts(body, tip, rounding, pose_geometry,complete_native_edges=policy is not None)
    partition = connected_partition(mask, contexts)
    labels = partition['labels']
    before = base.pixel_hash(labels)

    def candidates(actual, ignored_estimator_contexts):
        if not np.array_equal(actual, mask) or base.pixel_hash(labels) != before:
            raise ValueError('rounded_protection_candidate_identity_changed')
        return partition
    returned, report = base.evaluate_learned_mask(source, mask, expected_pixel_sha256,
        detect_only=detect_only, _version=VERSION, _scope_adapter=prepare_scoped_region,
        _candidate_builder=candidates)
    accepted = np.zeros_like(mask)
    for row in report['regions']:
        if row['status'] == 'transformed':
            accepted |= labels == row['region_id']
    if (returned.dtype != np.uint8 or returned.shape != rgb.shape or
            not np.array_equal(returned[~accepted], rgb[~accepted]) or base.pixel_hash(labels) != before):
        raise ValueError('rounded_protection_actual_RGB_outside_accepted_permission_changed')
    verify_source(source, 'inference')
    report.update(rounded_geometry_version=rounding['version'], accepted_permission_pixels=int(accepted.sum()),
        rejected_permission_pixels=int((mask & ~accepted).sum()),
        permission_applied_fraction=float(accepted.sum()/mask.sum()) if mask.any() else None,
        final_native_gate_authoritative=True, legacy_estimator_contexts_used=False,
        count_semantics='connected rounded permission components, not verified fingerprints',
        partition_policy='rounded_detection_owner_and_axis; no permission pixel dropped',
        GT_used=False, privacy_validated=False, complete_photo_protection_verified=False,
        RGB_outside_accepted_permission_preserved=True, rejected_pixels_preserved=True,
        black_redaction_used_as_protection=False, algorithm_thresholds_unchanged=True, frozen_files_unchanged=True)
    return returned, report, accepted, labels
