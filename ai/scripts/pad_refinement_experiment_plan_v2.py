"""Development-only coverage/split plans; no GT, inference or model adoption.

Tiles are fixed from an engineering sampling target (512 native -> 256 input,
128 overlap), not selected from annotation/test scores. Their max merge and
per-source sampling policy must be frozen in a NEW training protocol first.
"""
import hashlib
import json
import re
from types import MappingProxyType

import numpy as np
from scipy import ndimage
from pad_refinement_data_contract_v2 import native_shape, validate_source_id

POLICY = dict(version='native_body_tiles_v2_plan_only', connectivity=4,
              native_side=512, stride=384, model_input_size=256,
              max_tiles_per_source=256, max_components_per_source=256, ordering='y0,x0,y1,x1',
              GT_used=False, auto_adoption=False)
POLICY_SHA256 = hashlib.sha256(json.dumps(POLICY, sort_keys=True).encode()).hexdigest()
POLICY = MappingProxyType(POLICY)


def axis_starts(lo, hi):
    """Exclusive endpoint; include last window rather than dropping edge pixels."""
    end = max(lo, hi-POLICY['native_side'])
    return sorted(set(range(lo, end+1, POLICY['stride'])) | {end})


def plan_crops(source, body, coarse):
    if not isinstance(source,dict) or set(source)!={'height','width','coordinate_system','source_sha256'}:
        raise ValueError('source_identity_only; GT_fields_forbidden')
    shape = native_shape(source)
    if not _sha(source.get('source_sha256')):raise ValueError('source_hash_required')
    if (not isinstance(body, np.ndarray) or not isinstance(coarse, np.ndarray) or
            body.dtype != np.bool_ or coarse.dtype != np.bool_ or
            body.shape != shape or coarse.shape != shape):
        raise ValueError('native_boolean_mask_contract')
    if np.any(coarse & ~body):raise ValueError('coarse_outside_body')
    labels, count = ndimage.label(body, ndimage.generate_binary_structure(2, 1))
    if count > POLICY['max_components_per_source']:
        return dict(status='rejected',reason='component_resource_limit',boxes=[],
                    policy=POLICY.copy(),policy_sha256=POLICY_SHA256,
                    native_body_components=count,coverage_verified=False)
    boxes = set()
    for window in ndimage.find_objects(labels):
        if window is None:continue
        ys, xs = window
        for y in axis_starts(ys.start, ys.stop):
            for x in axis_starts(xs.start, xs.stop):
                box = (x,y,min(xs.stop,x+POLICY['native_side']),min(ys.stop,y+POLICY['native_side']))
                a,b,c,d = box
                if body[b:d,a:c].any():boxes.add(box)
                if len(boxes) > POLICY['max_tiles_per_source']:
                    # No prefix plan can be mistaken for complete coverage.
                    return dict(status='rejected',reason='tile_resource_limit',boxes=[],
                                policy=POLICY.copy(),policy_sha256=POLICY_SHA256,
                                minimum_required_tiles=len(boxes),coverage_verified=False)
    boxes = sorted(boxes, key=lambda box:(box[1],box[0],box[3],box[2]))
    multiplicity = np.zeros(shape,np.uint16)
    for a,b,c,d in boxes:multiplicity[b:d,a:c] += 1
    uncovered = int(np.count_nonzero(body & (multiplicity==0)))
    if uncovered:raise AssertionError('native_body_coverage_contract')
    body_count = int(body.sum())
    return dict(status='planned' if boxes else 'empty',boxes=[list(b) for b in boxes],
                policy=POLICY.copy(),policy_sha256=POLICY_SHA256,
                source_sha256=source['source_sha256'],coordinate_system=source['coordinate_system'],
                source_shape=list(shape),body_pixel_sha256=hashlib.sha256(body.tobytes()).hexdigest(),
                coarse_pixel_sha256=hashlib.sha256(coarse.tobytes()).hexdigest(),
                native_body_components=count,native_body_pixels=body_count,
                uncovered_native_body_pixels=uncovered,coverage_verified=True,
                max_native_pixels_per_model_axis=2.,
                max_body_overlap=int(multiplicity[body].max()) if body_count else 0,
                body_pixel_crop_visits=int(multiplicity[body].sum()),
                training_performed=False,approved_for_inference=False)


def _sha(value):
    return isinstance(value,str) and re.fullmatch('[0-9a-f]{64}',value) is not None


def group_splits(identities, groups, reserved_test_hashes):
    """Leave-one-acquisition-group-out development plan, never a final test.

Callers supply byte-verified encoded/upright RGB identities and explicit group
provenance. Group labels alone do not establish independent biometric identity.
"""
    if not isinstance(identities,list) or not identities:raise ValueError('source_identities_required')
    if not isinstance(groups,dict):raise ValueError('explicit_group_map_required')
    if not isinstance(reserved_test_hashes,list) or any(not _sha(h) for h in reserved_test_hashes):
        raise ValueError('reserved_test_hash_contract')
    ids, raw_seen, pixel_seen, members = set(), set(), set(), {}
    for row in identities:
        if not isinstance(row,dict) or set(row)!={'source_id','source_sha256','encoded_RGB_sha256','upright_RGB_sha256'}:
            raise ValueError('verified_raw_encoded_upright_hashes_required')
        sid = row.get('source_id');validate_source_id(sid)
        if sid.casefold() in ids:raise ValueError('duplicate_source_identity')
        ids.add(sid.casefold())
        values = [row.get(k) for k in ['source_sha256','encoded_RGB_sha256','upright_RGB_sha256']]
        if any(not _sha(v) for v in values):raise ValueError('verified_raw_encoded_upright_hashes_required')
        if values[0] in raw_seen or pixel_seen.intersection(values[1:]):raise ValueError('duplicate_source_or_decoded_pixels')
        raw_seen.add(values[0]);pixel_seen.update(values[1:])
        if values[0] in reserved_test_hashes:raise ValueError('reserved_test_source_overlap')
        group = groups.get(sid)
        if not isinstance(group,str) or not group.strip() or group!=group.strip():raise ValueError('missing_group_provenance')
        validate_source_id(group);group=group.casefold()
        members.setdefault(group,[]).append(sid)
    if set(groups) != {r['source_id'] for r in identities}:raise ValueError('group_map_source_mismatch')
    if len(members) < 2:raise ValueError('at_least_two_acquisition_groups_required')
    folds = []
    for group in sorted(members):
        folds.append(dict(train=sorted(s for g,ss in members.items() if g!=group for s in ss),
                          validation=sorted(members[group]),validation_group=group,
                          train_groups=sorted(g for g in members if g!=group)))
    return dict(version='acquisition_group_split_v2_plan_only',folds=folds,
                group_count=len(members),source_count=len(identities),
                groups_disjoint=True,source_and_decoded_duplicates=0,
                reserved_test_exclusions_verified=bool(reserved_test_hashes),
                independent_biometric_identity_verified=False,
                independent_final_test=False,training_performed=False)
