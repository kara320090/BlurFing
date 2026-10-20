"""Read-only evaluation of canonical photos, human masks and recorded V2 results.

Candidate union includes both applied AND rejected masks. Missing fingertips
must be annotated too. Rejection reasons are NOT visibility classifier labels.
"""
import argparse
import base64
from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from experimental_photo_transport_v2 import UploadedPhoto, validate_transport


def mask(path, shape):
    with Image.open(path) as image:
        if image.mode != 'L' or image.size != shape[::-1]:
            raise ValueError('original_coordinate_binary_L_mask_required')
        value = np.asarray(image).copy()
    if not np.isin(value, [0, 255]).all():
        raise ValueError('binary_mask_required')
    return value == 255


def overlap(predicted, expected):
    intersection = int((predicted & expected).sum())
    union = int((predicted | expected).sum())
    return dict(intersection_pixels=intersection, union_pixels=union,
                iou=intersection / union if union else None,
                recall=intersection / int(expected.sum()) if expected.any() else None,
                precision=intersection / int(predicted.sum()) if predicted.any() else None,
                excess_pixels=int((predicted & ~expected).sum()))


def evaluate(manifest_path):
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    if manifest.get('schema_version') != 'blurfing-photo-evaluation-v1' or not manifest.get('samples'):
        raise ValueError('annotated_samples_required')
    samples = manifest['samples']
    people, groups, hashes = {}, {}, set()
    for row in samples:
        if row.get('split') not in ('development', 'evaluation'):
            raise ValueError('explicit_split_required')
        for name, index in (('participant_alias', people), ('capture_group', groups)):
            value = row.get(name)
            if not isinstance(value, str) or not value or (value in index and index[value] != row['split']):
                raise ValueError('person_or_capture_group_leakage')
            index[value] = row['split']
        if row['source_sha256'] in hashes:
            raise ValueError('duplicate_source')
        hashes.add(row['source_sha256'])
    resolve = lambda value: manifest_path.parent / value
    registry = json.loads(resolve(manifest['consumed_registry']).read_text(encoding='utf-8-sig'))
    # Reuse the established registry validator; no invented/empty history.
    sys.path.insert(0, str(ROOT / 'ai/scripts'))
    from pad_refinement_tiles_v3 import validate_registry
    validate_registry(registry)
    used = {r[k] for r in registry for k in ('source_sha256', 'encoded_RGB_sha256', 'upright_RGB_sha256')}
    results, reasons, seen_pixels = [], Counter(), set()
    for row in samples:
        content = resolve(row['source']).read_bytes()
        upload = UploadedPhoto.decode(content)
        if upload.rgb_sha256 in seen_pixels:
            raise ValueError('duplicate_RGB_even_if_encoded_differently')
        seen_pixels.add(upload.rgb_sha256)
        if hashlib.sha256(content).hexdigest() != row['source_sha256']:
            raise ValueError('source_hash_mismatch')
        if row['split'] == 'evaluation' and ({upload.source_sha256, upload.rgb_sha256} & used or
                row.get('never_used_for_training_or_tuning') is not True):
            raise ValueError('consumed_or_unconfirmed_evaluation_sample')
        response_bytes = resolve(row['response']).read_bytes()
        payload = json.loads(response_bytes)
        validate_transport(payload, upload, request_id=payload['request_id'], engine='synthetic_v23')
        shape = upload.rgb.shape[:2]
        accepted, rejected = [mask(io.BytesIO(base64.b64decode(payload[k + '_permission_mask']['image_base64'])), shape)
                              for k in ('accepted', 'rejected')]
        if row.get('all_visible_fingertips_annotated') is not True or not row.get('regions'):
            raise ValueError('complete_human_review_required')
        visible, annotated = np.zeros(shape, bool), np.zeros(shape, bool)
        regions = []
        for region in row['regions']:
            visibility = region.get('visibility')
            if visibility not in ('visible', 'not_observed', 'uncertain') or region.get('human_reviewed') is not True:
                raise ValueError('explicit_human_visibility_required')
            annotation_bytes = resolve(region['mask']).read_bytes()
            gt = mask(io.BytesIO(annotation_bytes), shape)
            if not gt.any() or np.any(gt & annotated):
                raise ValueError('nonempty_disjoint_human_regions_required')
            annotated |= gt
            if visibility == 'visible':
                visible |= gt
            regions.append(dict(visibility=visibility, pixels=int(gt.sum()),
                                annotation_sha256=hashlib.sha256(annotation_bytes).hexdigest(),
                                candidate_coverage=float(((accepted | rejected) & gt).sum() / gt.sum()),
                                applied_coverage=float((accepted & gt).sum() / gt.sum())))
        reasons.update(r['reason_code'] for r in payload['region_display_bounds'])
        results.append(dict(sample_id=row['sample_id'], split=row['split'], capture_group=row['capture_group'],
                            source_sha256=upload.source_sha256, source_RGB_sha256=upload.rgb_sha256,
                            response_sha256=hashlib.sha256(response_bytes).hexdigest(),
                            candidate_vs_visible=overlap(accepted | rejected, visible),
                            applied_vs_visible=overlap(accepted, visible), regions=regions,
                            candidate_components=payload['candidate_components'],
                            rejected_components=payload['rejected_components']))
    counts = Counter((r['split'], r['capture_group']) for r in samples)
    ready = all(any(split == s and n >= 6 for (split, _), n in counts.items()) for s in ('development', 'evaluation'))
    return dict(schema_version='blurfing-photo-evaluation-report-v1', samples=results,
                manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                planned_minimum_collection_met=ready, rejection_reasons=dict(reasons),
                independence_attested=manifest.get('independence_confirmed_by_provider') is True,
                generalization_approved=False, privacy_validated=False,
                note='Small-sample mask coverage only. Rejection is not a visibility label; matching is a separate evaluation.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        report = evaluate(args.manifest)
        with args.output.open('x', encoding='utf-8') as stream:
            json.dump(report, stream, indent=2, allow_nan=False)
        print('Recorded mask coverage. No generalization/privacy approval.')
    except (OSError, ValueError, KeyError):
        print('Evaluation rejected: check private manifest, split, hashes, masks and V2 contract.')
        raise SystemExit(2)
