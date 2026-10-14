"""Private cache-based v1 consumer + matcher benchmark; excludes COLFISPOOF inference."""
import argparse,json,time,hashlib
from pathlib import Path
import cv2,numpy as np
from PIL import Image
from scipy import ndimage
from protect_photo_external_pitch_v1 import protect
from photo_coarse_adapter import adapt
from canonical_fingerprint_roi import canonical_roi
from nbis_matcher import run_nbis_job
from sourceafis_matcher import run_matcher_job

def benchmark(source,semantics,output,repeats=10):
    output=Path(output)
    if output.exists():raise FileExistsError('fresh_private_output_required')
    if repeats<10:raise ValueError('at_least_ten_measurements')
    output.mkdir(parents=True);rgb,a=adapt(source,semantics);labels,_=ndimage.label(a['coarse_mask']);rows=[]
    for i in range(repeats+1):
        folder=output/str(i);folder.mkdir();start=time.perf_counter();report=protect(source,semantics,folder/'consumer');consumer=time.perf_counter()-start;returned=np.asarray(Image.open(folder/'consumer/returned.png'));images={};pairs=[]
        for r in report['components']:
            if not r['applied']:continue
            key=str(r['component']);mask=labels==r['component'];e=r['evidence'];quality=dict(pitch_native=e['pitch_value']/e['image_scale'],orientation=e['orientation_deg'],credible_fraction=e['accepted_patch_count']/max(1,e['patch_count']))
            for name,frame in [('original',rgb),('returned',returned)]:
                roi=canonical_roi(cv2.cvtColor(frame,cv2.COLOR_RGB2GRAY),mask,a['source_sha256'],'PHOTO',quality,'photo_external_pitch_v1');path=folder/(key+'_'+name+'.png');Image.fromarray(roi.normalized_roi).save(path);images[key+'_'+name]=path
            pairs.extend([dict(key=key+'_self',probe=key+'_original',candidate=key+'_original'),dict(key=key+'_transformed',probe=key+'_original',candidate=key+'_returned')])
        t=time.perf_counter();nbis=run_nbis_job(images,pairs,run_name='external_pitch_benchmark') if pairs else None;nt=time.perf_counter()-t;t=time.perf_counter();afis=run_matcher_job(images,pairs,run_name='external_pitch_benchmark') if pairs else None;at=time.perf_counter()-t
        rows.append(dict(run=i,applied_count=report['transformed'],consumer=consumer,NBIS=nt,SourceAFIS=at,total=time.perf_counter()-start,signature=dict(evidence=[r['evidence']['evidence_hash'] for r in report['components']],returned=report['returned_RGB_sha256'],matcher_inputs=[hashlib.sha256(p.read_bytes()).hexdigest() for p in images.values()]),nbis=nbis,sourceafis=afis));print('benchmark',i,report['transformed'],flush=True)
    measured=rows[1:];summary={key:{name:float(fn([r[key] for r in measured])) for name,fn in [('mean',np.mean),('median',np.median),('min',np.min),('max',np.max),('std',np.std),('p95',lambda x:np.percentile(x,95))]} for key in ['consumer','NBIS','SourceAFIS','total']};report=dict(warmup=1,measurements=repeats,scope='source-bound semantic cache consumer + matchers; excludes COLFISPOOF inference',summary=summary,deterministic=all(r['signature']==rows[0]['signature'] for r in rows),rows=rows);(output/'benchmark.private.json').write_text(json.dumps(report,indent=2));return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--semantics',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--repeats',type=int,default=10);a=p.parse_args();benchmark(a.input,a.semantics,a.output,a.repeats)
