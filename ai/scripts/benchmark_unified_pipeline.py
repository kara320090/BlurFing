"""One warm-up plus ten routed core runs. Nested phase timings are not additive."""
import argparse,json,time,sys,hashlib
from pathlib import Path
import numpy as np
from protect_fingerprint import protect_image

PHASES={('fingerprint_input_router.py','route_input'):'routing',('finger_body_distal_estimator.py','estimate'):'coarse_estimator',('protect_visible_pad_checked_v2.py','observed_seed_pitch'):'pitch_observer',('photo_quality_gate.py','evaluate'):'PHOTO_quality_gate_inclusive',('transform_automatic_fingerprint_poc_v4_boundaryblend_02.py','render'):'PHOTO_renderer_composite',('fingerprint_structure_check.py','check_structure_change'):'structure_validation',('scanner_fingerprint_detector.py','detect_scanner'):'scanner_segmentation_and_ridge',('ridge_evidence_frontend.py','scanner_ridge_evidence'):'ridge_validation',('scanner_renderer_experimental.py','render_scanner'):'scanner_transform',('scanner_structure_guard.py','scanner_structure_guard'):'scanner_structure_validation'}
def benchmark(source,output,semantics=None,repeats=10):
    output=Path(output)
    if output.exists():raise FileExistsError('fresh_private_output_required')
    if repeats<10:raise ValueError('ten_measurements_required')
    output.mkdir(parents=True);rows=[]
    for i in range(repeats+1):
        phases={};starts={};code_cache={}
        def trace(frame,event,arg):
            if event not in ('call','return'):return
            code=frame.f_code
            if code not in code_cache:code_cache[code]=PHASES.get((code.co_filename.replace('\\','/').rsplit('/',1)[-1],code.co_name))
            key=code_cache[code]
            if key:
                if event=='call':starts[id(frame)]=time.perf_counter()
                elif event=='return' and id(frame) in starts:phases[key]=phases.get(key,0.)+time.perf_counter()-starts.pop(id(frame))
        old=sys.getprofile();start=time.perf_counter()
        try:
            sys.setprofile(trace);image,r=protect_image(source,output/str(i),photo_semantics=semantics)
        finally:sys.setprofile(old)
        total=time.perf_counter()-start
        rows.append(dict(run=i,status=r['status'],transformed=r['fingerprints_transformed'],rejected=r['fingerprints_rejected'],phases=phases,timing=r.get('timing',{}),total=total,signature=dict(input_type=r['input_type'],returned=hashlib.sha256(image.tobytes()).hexdigest(),regions=[{k:z.get(k) for k in ['quality_status','reason','mask_pixel_sha256']} for z in r['regions']])));print('benchmark',i,r['status'],flush=True)
    measured=rows[1:];keys=set().union(*(r['phases'] for r in measured));values={key:[r['phases'].get(key,0.) for r in measured] for key in keys};values['total']=[r['total'] for r in measured];values['COLFISPOOF_subprocess_including_startup']=[r['timing'].get('COLFISPOOF',0.) for r in measured]
    stats={k:{name:float(fn(v)) for name,fn in [('mean',np.mean),('median',np.median),('min',np.min),('max',np.max),('std',np.std),('p95',lambda a:np.percentile(a,95))]} for k,v in values.items()}
    report=dict(warmup=1,measurements=repeats,profile_overhead_included=True,nested_timings_not_additive=True,matcher_observation_included=False,structure_gate_feature_extraction_included=True,summary=stats,deterministic=all(r['signature']==rows[0]['signature'] for r in rows),rows=rows);(output/'benchmark.private.json').write_text(json.dumps(report,indent=2));return report
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--photo-semantics',type=Path);a=p.parse_args();benchmark(a.input,a.output,a.photo_semantics)
