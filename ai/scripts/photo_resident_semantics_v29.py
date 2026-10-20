"""Private stdio worker retaining only the configured semantic model, not results."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys


def main():
    p=argparse.ArgumentParser();p.add_argument('--external-source',required=True);p.add_argument('--model',required=True);a=p.parse_args()
    # Keep stdout exclusively for small protocol frames, including on imports.
    wire=sys.stdout;sys.stdout=sys.stderr
    import numpy as np
    from PIL import Image
    from colfispoof_raw_semantics import RawDeepLabRuntime,resolve_preprocessing
    from colfispoof_body_semantics import write_prediction
    def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    paths=[Path(a.model),resolve_preprocessing(a.external_source)/'Segmentation/DeepLabModel.py',
        Path(__file__),Path(__file__).with_name('colfispoof_raw_semantics.py'),Path(__file__).with_name('colfispoof_body_semantics.py')]
    pins={p:digest(p) for p in paths}
    runtime=RawDeepLabRuntime(a.external_source,a.model,device=os.environ.get('BLURFING_COLFISPOOF_DEVICE','cpu'),
        dll_directories=json.loads(os.environ.get('BLURFING_COLFISPOOF_DLL_DIRS','[]')))
    def send(value):wire.write(json.dumps(value,separators=(',',':'))+'\n');wire.flush()
    try:
        # Graph/kernel initialization uses synthetic pixels before readiness.
        runtime.model.run(Image.fromarray(np.zeros((1024,1024,3),np.uint8)))
        send(dict(status='ready',protocol='photo-semantic-resident-v29'))
        while True:
            line=sys.stdin.readline(16385)
            if not line:break
            if len(line)>16384 or not line.endswith('\n'):raise ValueError('worker_frame_limit')
            job=json.loads(line)
            if not isinstance(job,dict) or set(job)!={'id','input','output'}:raise ValueError('worker_frame_contract')
            if any(not isinstance(job[k],str) or not job[k] for k in job):raise ValueError('worker_frame_contract')
            if any(digest(p)!=sha for p,sha in pins.items()):raise ValueError('semantic_assets_changed_restart_required')
            write_prediction(runtime,job['input'],job['output'])
            if any(digest(p)!=sha for p,sha in pins.items()):raise ValueError('semantic_assets_changed_restart_required')
            send(dict(status='ok',id=job['id']))
    finally:runtime.close()
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception:raise SystemExit(1)
