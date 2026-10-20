"""Owned IMAGE-mode hand model; observations are fresh for every input."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys


def main():
    p=argparse.ArgumentParser();p.add_argument('--model',required=True);args=p.parse_args()
    wire=sys.stdout;sys.stdout=sys.stderr
    import mediapipe_hand_worker_v1 as hand
    model=Path(args.model)
    def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    pins={path:digest(path) for path in (model,Path(hand.__file__),Path(__file__))}
    if pins[model]!=hand.MODEL_SHA256:raise ValueError('official_hand_model_SHA256_mismatch')
    def verify():
        if any(digest(path)!=sha for path,sha in pins.items()):raise ValueError('hand_assets_changed_restart_required')
    def send(value):wire.write(json.dumps(value,separators=(',',':'))+'\n');wire.flush()
    with hand.create_detector(model) as detector:
        verify();send(dict(status='ready',protocol='photo-hand-resident-v31'))
        while True:
            line=sys.stdin.readline(16385)
            if not line:break
            if len(line)>16384 or not line.endswith('\n'):raise ValueError('hand_frame_limit')
            job=json.loads(line)
            if (not isinstance(job,dict) or set(job)!={'id','input','output'} or
                    any(not isinstance(v,str) or not v for v in job.values()) or
                    re.fullmatch('[0-9a-f]{32}',job['id']) is None):raise ValueError('hand_frame_contract')
            source,output=Path(job['input']),Path(job['output'])
            if not source.is_absolute() or not output.is_absolute() or source.is_symlink() or output.exists() or output.is_symlink():
                raise ValueError('fresh_hand_paths_required')
            verify();hand.run(source,model,output,detector=detector);verify()
            send(dict(status='ok',id=job['id']))
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception:raise SystemExit(1)
