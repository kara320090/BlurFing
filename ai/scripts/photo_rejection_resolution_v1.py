"""Explain real gate failures and export an explicit solid-redaction alternative.

This never turns a rejected fingerprint transform into a successful transform.
The alternative preserves accepted transforms and removes RGB from rejected
permission pixels. Detection completeness and biometric protection remain unproved.
"""
from collections import Counter
import hashlib
import numpy as np
from photo_resize_safety_v1 import validate_resize

VERSION = 'rounded_rejection_resolution_v1'
QUALITY_REJECTIONS = frozenset({
    'component_local_pitch_unobserved', 'component_local_seed_unavailable',
    'original_width_unavailable', 'native_body_width_boundary_unobserved',
    'insufficient_features', 'structure_change_not_demonstrated',
    'rounded_protection_owner_unavailable', 'rounded_protection_owner_ambiguous',
    'rounded_geometry_unresolved',
})


def pixel_hash(array):
    return hashlib.sha256(array.tobytes()).hexdigest()


def explain_regions(report):
    """Classify evidence already measured; no guessed cause or rerendering."""
    rows = []
    for region in report['regions']:
        geometry = region.get('geometry', {})
        details = region.get('renderer_details', {}).get('regions', [])
        check = details[0].get('structure_check', {}) if len(details) == 1 else {}
        evidence = check.get('minutiae', {})
        before, after = evidence.get('before_count'), evidence.get('after_count')
        reason = region.get('reason')
        cause = 'transform_applied' if region['status'] == 'transformed' else 'unclassified_rejection'
        if reason == 'insufficient_features' and type(before) is int and type(after) is int:
            # Mirrors the documented frozen predicate for explanation only.
            # Decisions remain authoritative in the existing renderer report.
            cause = ('original_and_returned_features_insufficient' if before < 10 and after < 10
                     else 'original_features_insufficient' if before < 10
                     else 'returned_features_insufficient' if after < 10
                     else 'feature_evidence_inconsistent')
        elif reason in ('component_local_pitch_unobserved', 'component_local_seed_unavailable'):
            cause = 'no_accepted_local_ridge_spacing' if reason.endswith('pitch_unobserved') else 'no_supported_observation_window'
        elif reason in ('rounded_protection_owner_unavailable', 'rounded_protection_owner_ambiguous'):
            cause = 'permission_fragment_owner_unresolved'
        elif reason == 'rounded_geometry_unresolved':
            cause = 'rounded_geometry_unresolved'
        elif reason in ('original_width_unavailable', 'native_body_width_boundary_unobserved'):
            cause = 'body_width_unavailable'
        elif reason == 'structure_change_not_demonstrated':
            cause = 'returned_structure_change_insufficient'
        attempts = geometry.get('observation_seed_attempts', [])
        rows.append(dict(region_id=region['region_id'], candidate_id=region.get('candidate_id'),
            status=region['status'], reason=reason, cause=cause, mask_pixels=region['mask_pixels'],
            original_feature_count=before, returned_feature_count=after,
            feature_criterion=check.get('criterion'), feature_counts_by_scope=check.get('counts'),
            observed_pitch_working=geometry.get('observed_pitch_working'),
            observation_window_count=len(attempts),
            legacy_observation_window_count=len(geometry.get('legacy_V10_pitch_attempts', [])),
            final_native_RGB_inspected=bool(details and details[0].get('returned_RGB_structure_check'))))
    return dict(version=VERSION, regions=rows,
        reason_counts=dict(Counter(r['cause'] for r in rows)),
        reason_pixels=dict(Counter({cause:sum(r['mask_pixels'] for r in rows if r['cause']==cause)
                                   for cause in {r['cause'] for r in rows}})),
        diagnostics_change_gate_decisions=False, feature_extraction_failure_is_protection_success=False,
        count_semantics='connected permission components, not anatomical fingers')


def cover_rejected(rgb, returned, permission, accepted, labels, report):
    """Explicit alternative for valid quality rejections, never runtime failures."""
    if (not isinstance(rgb, np.ndarray) or rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3 or
            not isinstance(returned, np.ndarray) or returned.dtype != np.uint8 or returned.shape != rgb.shape):
        raise ValueError('rejection_resolution_RGB_contract')
    validate_resize(*rgb.shape[:2], 1.)
    for mask in (permission, accepted):
        if not isinstance(mask, np.ndarray) or mask.dtype != np.bool_ or mask.shape != rgb.shape[:2]:
            raise ValueError('rejection_resolution_mask_contract')
    if (not isinstance(labels, np.ndarray) or labels.dtype != np.uint16 or labels.shape != permission.shape or
            not np.array_equal(labels > 0, permission) or np.any(accepted & ~permission) or
            not np.array_equal(returned[~accepted], rgb[~accepted])):
        raise ValueError('rejection_resolution_partition_contract')
    if (report.get('reject_reason') or report.get('error') or report.get('detect_only') or
            report.get('status') not in ('success', 'partial_success', 'rejected') or
            report.get('prediction_pixel_sha256') != pixel_hash(permission) or
            report.get('returned_RGB_sha256') != pixel_hash(returned)):
        raise ValueError('rejection_resolution_report_contract')
    rows = report['regions']
    ids = [r['region_id'] for r in rows]
    if (any(type(i) is not int or i < 1 for i in ids) or len(set(ids)) != len(ids) or
            set(ids) != set(np.unique(labels)) - {0}):
        raise ValueError('rejection_resolution_region_contract')
    validated = np.zeros_like(permission)
    applied = 0
    for row in rows:
        mask = labels == row['region_id']
        if row.get('error'):
            raise ValueError('rejection_resolution_processing_error: region '
                             + str(row['region_id']) + ': ' + str(row['error']) + ': ' + str(row.get('reason')))
        if (row['mask_pixels'] != int(mask.sum()) or
                row['mask_pixel_sha256'] != pixel_hash(mask)):
            raise ValueError('rejection_resolution_region_binding_mismatch')
        if row['status'] == 'transformed':
            details = row.get('renderer_details', {}).get('regions', [])
            if (len(details) != 1 or details[0].get('applied') is not True or
                    details[0].get('returned_RGB_structure_check', {}).get('structure_change_passed') is not True or
                    not np.any(returned[mask] != rgb[mask])):
                raise ValueError('rejection_resolution_unverified_transform')
            validated |= mask
            applied += 1
        elif row['status'] != 'rejected' or row.get('reason') not in QUALITY_REJECTIONS:
            raise ValueError('rejection_resolution_not_a_normal_quality_rejection')
    if (not np.array_equal(validated, accepted) or report.get('fingerprints_transformed') != applied or
            report.get('fingerprints_rejected') != len(rows)-applied):
        raise ValueError('rejection_resolution_accepted_contract')
    fallback = permission & ~accepted
    covered = returned.copy()
    covered[fallback] = 0
    if (not np.array_equal(covered[~permission], rgb[~permission]) or
            not np.array_equal(covered[accepted], returned[accepted]) or np.any(covered[fallback] != 0)):
        raise RuntimeError('rejection_resolution_actual_RGB_contract')
    status = ('no_candidates' if not permission.any() else 'native_transform_only' if not fallback.any()
              else 'transform_with_solid_redaction' if accepted.any() else 'solid_redaction_only')
    metadata = dict(version=VERSION, status=status, native_transform_status=report['status'],
        native_transformed_regions=applied, native_rejected_regions=len(rows)-applied,
        method='accepted_native_transform_plus_explicit_solid_black_for_rejected_permission',
        transform_pixels=int(accepted.sum()), solid_redaction_pixels=int(fallback.sum()),
        candidate_pixels=int(permission.sum()), untreated_candidate_pixels=0,
        actual_changed_pixels=int(np.any(covered != rgb, axis=2).sum()),
        candidate_area_handled=bool(permission.any()), full_photo_protection_verified=False,
        privacy_validated=False, detector_misses_possible=True, biometric_validation_performed=False,
        original_RGB_outside_permission_preserved=True, native_gate_decisions_unchanged=True,
        rejected_transform_counted_as_success=False, output_RGB_sha256=pixel_hash(covered),
        source_RGB_sha256=pixel_hash(rgb), permission_sha256=pixel_hash(permission),
        accepted_sha256=pixel_hash(accepted), fallback_sha256=pixel_hash(fallback))
    return covered, fallback, metadata


def save_resolution_artifacts(source, identity, rgb, returned, permission, accepted, labels, report, output):
    """Export a separately named alternative, leaving native files/status intact."""
    import html, json
    from pathlib import Path
    from PIL import Image
    from final_png_color_metadata_v1 import save_final_rgb_png
    output = Path(output)
    covered, fallback, metadata = cover_rejected(rgb, returned, permission, accepted, labels, report)
    diagnostics = explain_regions(report)
    save_final_rgb_png(source, identity['original_source_sha256'], covered, output/'covered.png',
                       identity['source_exif_orientation'])
    exif = Image.Exif(); exif[274] = identity['source_exif_orientation']
    with (output/'fallback_mask.png').open('xb') as stream:
        Image.fromarray(fallback.astype(np.uint8)*255).save(stream, format='PNG', exif=exif)
    with Image.open(output/'fallback_mask.png') as saved:
        if not np.array_equal(np.asarray(saved) > 0, fallback) or saved.getexif()[274] != exif[274]:
            raise RuntimeError('rejection_resolution_saved_mask_contract')
    metadata.update(output_path=str((output/'covered.png').resolve()),
                    comparison_path=str((output/'resolution.html').resolve()))
    details = dict(resolution=metadata, diagnostics=diagnostics)
    with (output/'rejection_diagnostics.private.json').open('x', encoding='utf-8') as stream:
        json.dump(details, stream, indent=2)
    titles = {
        'original_features_insufficient':'원본에서 검사에 필요한 특징점 부족',
        'returned_features_insufficient':'변환 후 특징점 부족 — 변환 전후 모두 10개 이상 기준에 걸림',
        'original_and_returned_features_insufficient':'원본과 변환 후 모두 특징점 부족',
        'no_accepted_local_ridge_spacing':'일관된 지문 간격 관측 실패',
        'no_supported_observation_window':'같은 영역 안에서 측정할 공간 부족',
        'permission_fragment_owner_unresolved':'작은 후보 조각의 손가락 소속 미확정',
        'body_width_unavailable':'손가락 폭 확인 실패',
        'rounded_geometry_unresolved':'손끝 모양 확인 실패',
        'returned_structure_change_insufficient':'변환 후 구조 변화 부족',
        'transform_applied':'실제 무늬 변환 적용',
    }
    summary = ''.join('<li>'+html.escape(titles.get(k,k))+f': {n}개 연결 영역</li>'
                      for k,n in diagnostics['reason_counts'].items())
    page = f'''<!doctype html><meta charset="utf-8"><title>BlurFing 거절 원인과 보완 결과</title>
<style>body{{font-family:Arial,sans-serif;margin:24px}}.grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}}img{{width:100%;max-height:680px;object-fit:contain}}p,li{{line-height:1.6}}</style>
<h1>지문 변환과 미적용 영역 가림</h1>
<p>무늬 변환: {report['fingerprints_transformed']}개 적용 / {report['fingerprints_rejected']}개 거절.
거절 영역 {metadata['solid_redaction_pixels']:,}화소를 별도 보완본에서 검게 가렸습니다.
이 수는 손가락 수가 아니라 연결 영역 수입니다.</p>
<div class="grid"><section><h2>원본</h2><a href="original.png"><img src="original.png"></a></section>
<section><h2>무늬 변환 결과</h2><p>거절된 부분은 원본입니다.</p><a href="protected.png"><img src="protected.png"></a></section>
<section><h2>미적용 부분을 가린 보완본</h2><p>covered.png · 검은 가림을 무늬 변환 성공으로 집계하지 않습니다.</p><a href="covered.png"><img src="covered.png"></a></section></div>
<h2>거절 이유</h2><ul>{summary}</ul>
<p>보완본은 검출된 후보 안의 미적용 영역을 가립니다. 검출 누락과 후보 경계 오차는 남을 수 있으며, 사진 전체의 지문 보호 성능 검증은 완료되지 않았습니다.</p>'''
    with (output/'resolution.html').open('x', encoding='utf-8') as stream:stream.write(page)
    return details
