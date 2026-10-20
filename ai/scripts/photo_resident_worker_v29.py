"""Owned warmed photo worker. Stdio carries paths/IDs, never image payloads."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys


def validate_job(job):
    if (not isinstance(job,dict) or set(job)!={'id','input','output','request_id'} or
            any(not isinstance(v,str) or not v for v in job.values()) or
            re.fullmatch('[0-9a-f]{32}',job['id']) is None):raise ValueError('photo_worker_job_contract')
    source,output=Path(job['input']),Path(job['output'])
    if (not source.is_absolute() or not output.is_absolute() or source.is_symlink() or output.is_symlink()
            or not source.is_file() or output.exists() or source.name!='input.png' or output.name!='output'
            or source.resolve().parent!=output.resolve().parent):raise ValueError('fresh_photo_worker_paths_required')
    return source,output


def main():
    p=argparse.ArgumentParser();p.add_argument('--model',type=Path,required=True);p.add_argument('--registry',type=Path,required=True)
    p.add_argument('--development-replay',action='store_true');a=p.parse_args()
    wire=sys.stdout;sys.stdout=sys.stderr
    from photo_resident_resources_v29 import Resources
    from protection_runtime_sources_v1 import capture_runtime_sources,assert_runtime_sources_unchanged
    from infer_whole_pad_context_v6 import load_model
    from export_photo_permissions_v1 import run
    from photo_lossless_io_v29 import lossless_io
    snapshot=capture_runtime_sources()
    roi=os.environ.get('BLURFING_PHOTO_HAND_ROI','false')
    if roi not in ('true','false'):raise ValueError('explicit_hand_ROI_boolean_required')
    if roi=='true':
        from photo_hand_roi_v30 import run as roi_run
        original=run
        def run(source,output,**options):
            if options.pop('photo_engine')!='synthetic_v23':raise ValueError('ROI_requires_synthetic_photo')
            return roi_run(source,output,**options)
    def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    assets={path:digest(path) for path in (a.registry,a.model/'final_config.private.json',a.model/'final_context_whole_pad.pt')}
    load_model(a.model)
    resources=Resources()
    def send(value):wire.write(json.dumps(value,separators=(',',':'))+'\n');wire.flush()
    try:
        assert_runtime_sources_unchanged(snapshot)
        send(dict(status='ready',protocol='photo-resident-v29'))
        while True:
            line=sys.stdin.readline(16385)
            if not line:break
            if len(line)>16384 or not line.endswith('\n'):raise ValueError('photo_worker_frame_limit')
            job=json.loads(line);source,output=validate_job(job)
            assert_runtime_sources_unchanged(snapshot)
            if any(digest(path)!=sha for path,sha in assets.items()):raise ValueError('photo_assets_changed_restart_required')
            with lossless_io():
                run(source,output,photo_engine='synthetic_v23',photo_model=a.model,consumed_registry=a.registry,
                    request_id=job['request_id'],development_replay=a.development_replay,execution_context=resources)
            if any(digest(path)!=sha for path,sha in assets.items()):raise ValueError('photo_assets_changed_restart_required')
            assert_runtime_sources_unchanged(snapshot)
            send(dict(status='ok',id=job['id']))
    finally:resources.close()
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception:raise SystemExit(1)
