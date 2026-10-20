"""Explicit reviewed V23 demo: render, verify saved RGB, publish a local report."""
import hashlib
import html
import io
import json
from pathlib import Path
import numpy as np
from PIL import Image, ImageCms, ImageOps
from photo_visibility_annotation_v1 import Project
from photo_visibility_reviewed_batch_v1 import run_batch
from protection_runtime_sources_v1 import capture_runtime_sources, assert_runtime_sources_unchanged

APPEARANCE = 'junction_v23'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def preview(rgb, icc, destination):
    image = Image.fromarray(rgb)
    if icc:
        image = ImageCms.profileToProfile(image, ImageCms.ImageCmsProfile(io.BytesIO(icc)),
                                         ImageCms.createProfile('sRGB'), outputMode='RGB')
    image.thumbnail((800, 800))
    image.save(destination)


def publish_report(project, output, batch):
    """Read back the actual PNG; never regenerate the comparison result."""
    output = Path(output)
    (output/'previews').mkdir(exist_ok=False)
    rows = []
    body = ['''<!doctype html><html lang="ko"><meta charset="utf-8">
<title>BlurFing V23 검토 기반 실행 결과</title>
<style>body{font:16px/1.6 system-ui;max-width:1450px;margin:30px auto;padding:20px;background:#f5f7f9}
section{background:white;padding:20px;margin:20px 0}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
img{max-width:100%;max-height:650px}a{color:#1653a0}.notice{background:#fff0d2;padding:15px}
@media(max-width:700px){.grid{grid-template-columns:1fr}}</style>
<h1>V23 · 사람이 검토한 영역의 인공 지문 교체</h1>
<p class="notice">지문선이 보인다고 사람이 확인한 영역만 처리했습니다. 불확실·미관찰 영역은 원본입니다.
이 화면은 일반 보호 성능이나 자동 검출 정확도의 검증 결과가 아닙니다. 저장 전 누락된 손끝과 남은 지문을 확인하세요.</p>
<p>왼쪽 원본 · 가운데 실제 저장 결과 · 오른쪽 적용 마스크(흰색). 미리보기는 화면 크기에 맞췄으며 다운로드 PNG는 원래 해상도입니다.</p>''']
    for item in batch['rows']:
        sid = item['source_id']
        # IDs come from the verified project, never from an untrusted result path.
        if sid not in project.sources or Path(sid).name != sid or '/' in sid or '\\' in sid:
            raise ValueError('known_simple_source_id_required')
        folder = output/'results'/sid
        report = json.loads((folder/'result.private.json').read_text('utf-8'))
        original, _ = project.arrays(sid)
        with Image.open(folder/'returned.png') as image:
            icc = image.info.get('icc_profile')
            returned = np.asarray(ImageOps.exif_transpose(image).convert('RGB'))
        with Image.open(folder/'applied_mask_upright.png') as image:
            applied = np.asarray(image) > 0
        digest = hashlib.sha256(returned.tobytes()).hexdigest()
        if (returned.shape != original.shape or applied.shape != original.shape[:2]
                or digest != report['output_RGB_sha256'] or digest != item['output_RGB_sha256']
                or report['appearance'] != APPEARANCE
                or not np.array_equal(returned[~applied], original[~applied])
                or int(applied.sum()) != report['applied_mask_pixels']):
            raise RuntimeError('demo_saved_output_verification_failed')
        source = project.sources[sid]
        with Image.open(source['source_path']) as image:
            source_icc = image.info.get('icc_profile')
        preview(original, source_icc, output/'previews'/f'{sid}-original.png')
        preview(returned, icc, output/'previews'/f'{sid}-returned.png')
        preview(np.repeat((applied.astype(np.uint8)*255)[..., None], 3, axis=2),
                None, output/'previews'/f'{sid}-mask.png')
        statuses = {}
        for region in report['regions']:
            statuses[region['status']] = statuses.get(region['status'], 0) + 1
        row = dict(source_id=sid, applied_regions=report['applied_region_count'],
                   review_required=report['review_required_count'], region_status_counts=statuses,
                   PNG_sha256=sha(folder/'returned.png'), output_RGB_sha256=digest,
                   saved_RGB_verified=True, outside_applied_RGB_preserved=True)
        rows.append(row)
        safe = html.escape(sid)
        body.append(f'<section><h2>{safe}</h2><p>적용 {row["applied_regions"]}영역 · 확인 필요 {row["review_required"]}영역 · '
                    f'미관찰로 미적용 {statuses.get("not_applied_human_not_observed",0)}영역</p>'
                    f'<p><a href="results/{safe}/returned.png" download>결과 PNG 저장/열기</a> · '
                    f'<a href="results/{safe}/applied_mask_upright.png">적용 마스크</a></p><div class="grid">')
        for variant, label in [('original', '원본'), ('returned', '실제 저장 결과'), ('mask', '적용 영역')]:
            body.append(f'<div>{label}<br><img src="previews/{safe}-{variant}.png" alt="{label}"></div>')
        body.append('</div></section>')
    body.append('<p>원본 파일은 보존됩니다. 마스크 밖 픽셀 보존은 누락된 지문까지 보호됐다는 뜻이 아닙니다.</p></html>')
    result = dict(version='reviewed_V23_demo_v1', appearance=APPEARANCE, rows=rows,
                  privacy_validated=False, independent_validation=False,
                  automatic_visibility_approved=False, saved_RGB_verified=True)
    (output/'verification.private.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    (output/'report.html').write_text('\n'.join(body), encoding='utf-8')
    return result


def run(roster, state, output, *, source_ids, seed=None):
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise FileExistsError('fresh_demo_output_required')
    if not source_ids:
        raise ValueError('explicit_source_selection_required')
    if not (Path(state)/'project.json').is_file():
        raise ValueError('existing_completed_review_required')
    snapshot = capture_runtime_sources()
    project = Project(roster, state)
    state_before = {str(p): sha(p) for p in project.state.rglob('*.json')}
    output.mkdir(parents=True, exist_ok=False)
    marker = output/'INCOMPLETE.txt'
    marker.write_text('Demo incomplete. Do not treat partial outputs as a completed result.', encoding='utf-8')
    batch = run_batch(roster, state, output/'results', source_ids=source_ids, seed=seed, appearance=APPEARANCE)
    verification = publish_report(project, output, batch)
    if state_before != {str(p): sha(p) for p in project.state.rglob('*.json')}:
        raise RuntimeError('demo_human_review_changed')
    for sid in source_ids:
        project.arrays(sid)
    provenance = assert_runtime_sources_unchanged(snapshot)
    (output/'runtime-source.private.json').write_text(json.dumps(provenance, indent=2), encoding='utf-8')
    marker.unlink()
    return dict(status='completed_reviewed_V23_demo', output=str(output.resolve()),
                report=str((output/'report.html').resolve()), sources=len(verification['rows']),
                applied_regions=batch['applied_regions'], review_required=batch['review_required'],
                saved_RGB_verified=True, privacy_validated=False)


if __name__ == '__main__':
    from protect_fingerprint import JSONArgumentParser, cli_progress_to_stderr
    p = JSONArgumentParser(description=__doc__)
    for key in ('roster', 'state', 'output'):
        p.add_argument('--'+key, type=Path, required=True)
    p.add_argument('--source-id', action='append', required=True)
    p.add_argument('--seed', type=int)
    args = p.parse_args()
    try:
        with cli_progress_to_stderr():
            result = run(args.roster, args.state, args.output, source_ids=args.source_id, seed=args.seed)
        print(json.dumps(result))
    except Exception as error:
        print(json.dumps(dict(status='error', error=type(error).__name__, reason=str(error))))
        raise SystemExit(1)
