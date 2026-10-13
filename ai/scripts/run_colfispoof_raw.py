"""GT-free raw semantic inference worker (external TensorFlow environment)."""
import argparse,hashlib,json,time
from pathlib import Path
import numpy as np
from PIL import Image
from colfispoof_raw_semantics import RawDeepLabRuntime,MODEL_SHA256


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(inputs, output, external_source, model, repeats=3, benchmark_sample=None):
    if repeats<3:raise ValueError('at_least_three_repeats_required')
    if any(set(item)!={'sample_id','source','source_sha256'} for item in inputs):raise ValueError('only_RGB_source_identity_fields_allowed; no_GT_metadata')
    output=Path(output);output.mkdir(exist_ok=False,parents=True)
    runtime=RawDeepLabRuntime(external_source,model);rows=[]
    try:
        for item in inputs:
            sid=item['sample_id']
            if Path(sid).name!=sid or sid in ['.','..']:raise ValueError('invalid_sample_id')
            path=Path(item['source']);before=sha(path)
            if before!=item['source_sha256']:raise ValueError('source_sha_mismatch')
            with Image.open(path) as im:rgb=np.asarray(im.convert('RGB')).copy()
            folder=output/sid;folder.mkdir();runs=[]
            for repeat in range(repeats):
                print(sid,'repeat',repeat+1,'started',flush=True);result=runtime.predict(rgb);mask=result['mask'];digest=hashlib.sha256(mask.tobytes()).hexdigest()
                Image.fromarray(mask.astype(np.uint8)*255).save(folder/f'consensus_repeat_{repeat+1}.png')
                if repeat==0:
                    for angle,m in zip([0,90,180,270],result['rotation_masks']):Image.fromarray(m.astype(np.uint8)*255).save(folder/f'rotation_{angle}.png')
                runs.append(dict(mask_pixel_sha256=digest,mask_file_sha256=sha(folder/f'consensus_repeat_{repeat+1}.png'),timing=result['timing'],rotations=result['rotations']))
                print(sid,'repeat',repeat+1,'finished',result['timing']['total'],digest,flush=True)
                (folder/'runs.json').write_text(json.dumps(runs,indent=2))
            assert sha(path)==before
            row=dict(sample_id=sid,source_sha256=before,shape=list(rgb.shape[:2]),deterministic=len({r['mask_pixel_sha256'] for r in runs})==1,runs=runs);rows.append(row)
            (output/'inference.json').write_text(json.dumps(dict(rows=rows,model_sha256=MODEL_SHA256,framework=runtime.framework_version,upstream_model_source_sha256=runtime.source_sha256,device='CPU',threads=8,onednn='environment default',primary_votes=2,cleanup='none'),indent=2))
        if benchmark_sample is not None:
            item=next(r for r in inputs if r['sample_id']==benchmark_sample)
            with Image.open(item['source']) as im:rgb=np.asarray(im.convert('RGB')).copy()
            times=[];hashes=[]
            for i in range(11):
                print('benchmark',i,'started',flush=True);result=runtime.predict(rgb);hashes.append(hashlib.sha256(result['mask'].tobytes()).hexdigest())
                if i:times.append(result['timing'])
                print('benchmark',i,'finished',result['timing']['total'],flush=True)
                (output/'benchmark_progress.json').write_text(json.dumps(dict(measured=len(times),timings=times,hashes=hashes),indent=2))
            stats={key:dict(mean=float(np.mean([t[key] for t in times])),median=float(np.median([t[key] for t in times])),p95=float(np.percentile([t[key] for t in times],95))) for key in times[0]}
            (output/'benchmark.json').write_text(json.dumps(dict(device='CPU',sample_id=benchmark_sample,warmup=1,measured=10,deterministic=len(set(hashes))==1,stats_seconds=stats,one_rotation_semantics='mean of the four actually timed rotations within each run',total_scope='RGB already loaded; excludes graph load, source decode and output PNG writes'),indent=2))
    finally:runtime.close()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--inputs',type=Path,required=True,help='private JSON: sample_id, source, source_sha256 only; never GT');p.add_argument('--output',type=Path,required=True);p.add_argument('--external-source',type=Path,required=True);p.add_argument('--model',type=Path,required=True);p.add_argument('--benchmark-sample');a=p.parse_args();run(json.loads(a.inputs.read_text()),a.output,a.external_source,a.model,benchmark_sample=a.benchmark_sample)
