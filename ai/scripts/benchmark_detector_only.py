"""Detector-only warm-up + repeat timing for private development inputs.

Never renders or invokes matchers. It explicitly cannot establish end-to-end
protection benchmark completion. Raw mask digests test deterministic proposals
as well as accepted artifact semantics, so empty accepted masks are not enough.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time
import numpy as np
import automatic_boundary_v1 as detector
from detection_artifact import read_input, digest


def benchmark(source,output,repeats=10):
    if repeats<10:raise ValueError('At least ten measured repetitions required')
    rgb,expected,_=read_input(source);runs=[];signatures=[]
    for index in range(repeats+1):
        masks=[];old=detector._local_pad
        def observed(image,candidate):
            mask,quality=old(image,candidate)
            if mask is not None:masks.append(hashlib.sha256(mask.tobytes()).hexdigest())
            return mask,quality
        try:
            detector._local_pad=observed;start=time.perf_counter();r=detector.detect_boundaries(rgb);elapsed=time.perf_counter()-start
        finally:detector._local_pad=old
        signature=dict(raw_mask_hashes=masks,rejections=r['rejected'],regions=[dict(status=q['status'],reason=q['reject_reason'],scope=q['scope'],pitch=q['pitch_native'],mask_sha256=hashlib.sha256(q['mask'].tobytes()).hexdigest()) for q in r['regions']])
        signatures.append(hashlib.sha256(json.dumps(signature,sort_keys=True).encode()).hexdigest())
        if index:runs.append(dict(detection=r['candidate_generation_seconds'],boundary=r['boundary_and_pitch_seconds'],detector_total=elapsed,approved_regions=sum(q['status']=='accepted' for q in r['regions'])))
        print('warmup' if not index else f'measured {index}/{repeats}',flush=True)
    if digest(source)!=expected:raise ValueError('source_changed')
    if len(set(signatures))!=1:raise ValueError('nondeterministic_detector')
    stats={}
    for k in ['detection','boundary','detector_total']:
        x=[r[k] for r in runs];stats[k]=dict(mean=float(np.mean(x)),median=float(np.median(x)),min=float(min(x)),max=float(max(x)),std=float(np.std(x)),p95=float(np.percentile(x,95)))
    data=dict(warmup=1,repeats=repeats,deterministic=True,stats=stats,runs=runs,transform=None,nbis=None,sourceafis=None,end_to_end=None,full_protection_benchmark_complete=False)
    output.mkdir(parents=True,exist_ok=False);(output/'benchmark.json').write_text(json.dumps(data,indent=2));return data

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',required=True,type=Path);p.add_argument('--output',required=True,type=Path);p.add_argument('--repeats',type=int,default=10);a=p.parse_args();benchmark(a.input,a.output,a.repeats)
