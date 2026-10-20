"""Actual HTTP rehearsal with strict V2 validation and fresh private evidence.

This measures HTTP + local file readback, NOT Android or privacy effectiveness.
Input must already be an sRGB, EXIF-normalized canonical RGB8 PNG.
"""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import urlsplit
import uuid

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from experimental_photo_transport_v2 import (ENGINE_METHODS, MAX_TRANSPORT_BYTES, UploadedPhoto, validate_transport)


def address(value):
    parsed = urlsplit(value)
    if (parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or
            (parsed.scheme == 'http' and parsed.hostname not in ('localhost', '127.0.0.1', '::1'))):
        raise ValueError('https_or_loopback_address_required')
    return value.rstrip('/')


def rehearsal(source, base_url, output, runs=3, *, client=None):
    if type(runs) is not int or not 1 <= runs <= 10:
        raise ValueError('runs_must_be_1_to_10')
    base_url = address(base_url)
    content = Path(source).read_bytes()
    upload = UploadedPhoto.decode(content)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    (output / 'source.png').write_bytes(content)
    (output / 'INCOMPLETE').touch()
    report = dict(schema_version='blurfing-photo-rehearsal-v1', boundary='backend_http_and_disk_readback_only',
                  started_at=datetime.now(timezone.utc).isoformat(), source_sha256=upload.source_sha256,
                  source_RGB_sha256=upload.rgb_sha256, engine='synthetic_v23', runs=[],
                  android_e2e_verified=False, physical_devices_verified=False, privacy_validated=False,
                  independent_final_test=False, actual_model_execution_attested=False)
    try:
        report['client_commit'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.SubprocessError):
        report['client_commit'] = 'unknown'
    owned = client is None
    client = client or httpx.Client(timeout=660, follow_redirects=False, trust_env=False)
    try:
        for index in range(runs):
            folder = output / f'run-{index + 1:02d}'
            folder.mkdir()
            request_id = str(uuid.uuid4())
            row = dict(attempt=index + 1, request_id=request_id, contract_and_readback_verified=False)
            started = time.monotonic()
            try:
                fields = dict(request_id=request_id, method=ENGINE_METHODS['synthetic_v23'],
                              scope='automatic_photo', strength='0.5')
                with client.stream('POST', base_url + '/v2/photo/protect', data=fields,
                                   files={'image': ('source.png', content, 'image/png')}) as response:
                    row['http_status'] = response.status_code
                    response.raise_for_status()
                    if response.headers.get('content-type', '').split(';')[0] != 'application/json':
                        raise ValueError('json_response_required')
                    body = bytearray()
                    for chunk in response.iter_bytes(65536):
                        if len(body) + len(chunk) > MAX_TRANSPORT_BYTES:
                            raise ValueError('response_byte_limit')
                        body.extend(chunk)
                payload = validate_transport(json.loads(body), upload, request_id=request_id, engine='synthetic_v23')
                png = base64.b64decode(payload['image_base64'], validate=True)
                target = folder / 'returned.png'
                target.write_bytes(png)
                if target.read_bytes() != png:
                    raise ValueError('saved_png_readback_mismatch')
                (folder / 'response.private.json').write_text(json.dumps(payload, allow_nan=False), encoding='utf-8')
                for name in ('accepted', 'rejected'):
                    (folder / (name + '.png')).write_bytes(base64.b64decode(payload[name + '_permission_mask']['image_base64']))
                row.update(contract_and_readback_verified=True, status=payload['status'],
                           candidate_components=payload['candidate_components'], applied_components=payload['transformed_components'],
                           rejected_components=payload['rejected_components'], server_processing_ms=payload['processing_ms'],
                           returned_png_sha256=hashlib.sha256(png).hexdigest(),
                           returned_RGB_sha256=payload['returned_RGB_sha256'],
                           reasons=[r['reason_code'] for r in payload['region_display_bounds']])
            except (OSError, ValueError, httpx.HTTPError) as error:
                # Never include response text, image content, URL or local paths.
                row['error_kind'] = type(error).__name__
            finally:
                row['http_and_readback_ms'] = round((time.monotonic() - started) * 1000)
                report['runs'].append(row)
        report['three_consecutive_http_runs_within_120s'] = (runs >= 3 and all(
            r['contract_and_readback_verified'] and r.get('applied_components', 0) > 0
            and r['http_and_readback_ms'] <= 120000 for r in report['runs']))
        (output / 'report.private.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
        (output / 'INCOMPLETE').unlink()
        return report
    finally:
        if owned:
            client.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--output', required=True, type=Path, help='New private directory; never an existing run.')
    parser.add_argument('--runs', type=int, default=3)
    parser.add_argument('--acknowledge-private-upload', action='store_true', required=True)
    args = parser.parse_args()
    try:
        report = rehearsal(args.input, args.base_url, args.output, args.runs)
        print(json.dumps({k: report[k] for k in ('boundary', 'three_consecutive_http_runs_within_120s', 'android_e2e_verified')}))
        raise SystemExit(0 if report['three_consecutive_http_runs_within_120s'] else 2)
    except (OSError, ValueError, httpx.HTTPError):
        print('Rehearsal failed; no inference/protection approval. Check private evidence and input contract.')
        raise SystemExit(2)
