"""CPU/GPU runtime-specific experimental benchmark; all outputs are private.

Uses an isolated persistent TensorFlow worker, one warm-up, then at least ten
sequential complete detector/renderer/matcher runs. No training or GT is read.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import numpy as np
from PIL import Image


def worker(args):
    # Keep TensorFlow/model progress off the JSON-line protocol, including C stdout.
    protocol=os.fdopen(os.dup(1),'w',buffering=1);os.dup2(2,1)
    from colfispoof_raw_semantics import RawDeepLabRuntime
    from colfispoof_body_semantics import predict_body
    runtime=RawDeepLabRuntime(args.external_source,args.model)
    try:
        for line in sys.stdin:
            request=json.loads(line);source=Path(request['source']);folder=Path(request['output']);folder.mkdir(parents=True)
            rgb=np.asarray(Image.open(source).convert('RGB'));tick=time.perf_counter();result=predict_body(runtime,rgb);duration=time.perf_counter()-tick
            for key in ['body','tip']:Image.fromarray(result[key].astype(np.uint8)*255).save(folder/(key+'.png'))
            identity=dict(source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),image_width=rgb.shape[1],image_height=rgb.shape[0],body_sha256=hashlib.sha256((folder/'body.png').read_bytes()).hexdigest(),tip_sha256=hashlib.sha256((folder/'tip.png').read_bytes()).hexdigest())
            (folder/'semantics.json').write_text(json.dumps(identity));protocol.write(json.dumps(dict(COLFISPOOF_seconds=duration))+'\n')
    finally:runtime.close()


def benchmark(args):
    from photo_coarse_adapter import adapt
    from photo_coarse_renderer_adapter_v1 import transform
    from canonical_fingerprint_roi import canonical_roi
    from nbis_matcher import run_nbis_job
    from sourceafis_matcher import run_matcher_job
    import cv2
    if args.repeats<10:raise ValueError('at_least_ten_measurements_required')
    if args.output.exists():raise FileExistsError('fresh_private_output_required')
    args.output.mkdir(parents=True);rows=[]
    cmd=[str(args.tensorflow_python),str(Path(__file__).resolve()),'--worker','--external-source',str(args.external_source),'--model',str(args.model)]
    with (args.output/'worker.log').open('w') as log:
        child=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,text=True,shell=False)
        try:
            for i in range(args.repeats+1):
                folder=args.output/str(i);folder.mkdir();start=time.perf_counter();child.stdin.write(json.dumps(dict(source=str(args.input.resolve()),output=str(folder/'semantics')))+'\n');child.stdin.flush();line=child.stdout.readline()
                if not line:raise RuntimeError('COLFISPOOF_worker_failed_see_private_log')
                model=json.loads(line);model_wall=time.perf_counter()-start;t=time.perf_counter();rgb,artifact=adapt(args.input,folder/'semantics');adapter=time.perf_counter()-t
                returned,details=transform(rgb,artifact);t=time.perf_counter();images={};pairs=[];input_hashes=[];applied={int(r['candidate_id'].split('-')[-1]) for r in details['regions'] if r.get('applied')}
                for entry in artifact['regions']:
                    if entry['component'] not in applied:continue
                    original=entry['roi'];modified=canonical_roi(cv2.cvtColor(returned,cv2.COLOR_RGB2GRAY),original.binary_mask>0,original.source_sha256,'PHOTO',original.ridge_quality,original.detector_name);key=str(entry['component'])
                    for label,im in [('original',original.normalized_roi),('returned',modified.normalized_roi)]:
                        path=folder/(key+'_'+label+'.png');Image.fromarray(im).save(path);images[key+'_'+label]=path;input_hashes.append(hashlib.sha256(im.tobytes()).hexdigest())
                    pairs.extend([dict(key=key+'_self',probe=key+'_original',candidate=key+'_original'),dict(key=key+'_transformed',probe=key+'_original',candidate=key+'_returned')])
                preparation=time.perf_counter()-t;t=time.perf_counter();nbis=run_nbis_job(images,pairs,run_name='photo_experimental_benchmark') if pairs else None;nbis_time=time.perf_counter()-t;t=time.perf_counter();afis=run_matcher_job(images,pairs,run_name='photo_experimental_benchmark') if pairs else None;afis_time=time.perf_counter()-t
                rows.append(dict(run=i,warmup=i==0,applied=details['applied'],timing=dict(COLFISPOOF=model['COLFISPOOF_seconds'],worker_roundtrip=model_wall,coarse_and_canonical=adapter,renderer_and_structure=details['renderer_and_structure_seconds'],matcher_preparation=preparation,NBIS=nbis_time,SourceAFIS=afis_time,end_to_end=time.perf_counter()-start),signature=dict(mask=hashlib.sha256(artifact['coarse_mask'].tobytes()).hexdigest(),returned=hashlib.sha256(returned.tobytes()).hexdigest(),matcher_inputs=input_hashes),nbis=nbis,sourceafis=afis))
                print('benchmark',i,'applied',details['applied'],flush=True)
        finally:
            child.stdin.close()
            try:child.wait(timeout=30)
            except subprocess.TimeoutExpired:child.terminate();child.wait(timeout=10)
    measured=rows[1:];summary={key:dict(mean=float(np.mean(v)),median=float(np.median(v)),min=float(np.min(v)),max=float(np.max(v)),std=float(np.std(v)),p95=float(np.percentile(v,95))) for key in measured[0]['timing'] for v in [[r['timing'][key] for r in measured]]}
    deterministic=all(r['signature']==rows[0]['signature'] for r in rows)
    report=dict(warmup=1,measurements=args.repeats,summary=summary,deterministic=deterministic,successful_runs=sum(r['applied'] for r in measured),rows=rows)
    (args.output/'benchmark.private.json').write_text(json.dumps(report,indent=2));return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--worker',action='store_true');p.add_argument('--input',type=Path);p.add_argument('--output',type=Path);p.add_argument('--external-source',type=Path,required=True);p.add_argument('--model',type=Path,required=True);p.add_argument('--tensorflow-python',type=Path);p.add_argument('--repeats',type=int,default=10);a=p.parse_args()
    if a.worker:worker(a)
    else:
        if not all([a.input,a.output,a.tensorflow_python]):p.error('--input, --output, --tensorflow-python required')
        benchmark(a)
