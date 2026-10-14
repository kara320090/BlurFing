"""Explicit private-data benchmark; warmup excluded, successes kept separate.

Results are private by default. An accepted legacy control input is not proof
that new review-gated detector proposals are safe or accurate.
"""
import argparse,json,time
from pathlib import Path
import numpy as np
from detection_artifact import write_detection,transform_artifact
from nbis_matcher import run_nbis_job
from sourceafis_matcher import run_matcher_job


def stats(values):
    a=np.asarray(values,float)
    return dict(mean=float(a.mean()),median=float(np.median(a)),min=float(a.min()),max=float(a.max()),std=float(a.std()),p95=float(np.percentile(a,95))) if len(a) else None


def benchmark(source,output,repeats=10,matchers=False):
    if repeats<10:raise ValueError('At least ten measured iterations required')
    folder=Path(output);folder.mkdir(parents=True,exist_ok=False);rows=[]
    for i in range(repeats+1):
        start=time.perf_counter();artifact=write_detection(source,folder/f'detect_{i:03d}');timing=json.loads((artifact.parent/'detection_timing.json').read_text());returned,details=transform_artifact(source,artifact);nbis=None;sa=None;nt=0.;st=0.
        if matchers and details['applied']:
            regions=[r for r in details['regions'] if r.get('applied')]
            images={};pairs=[]
            for j,r in enumerate(regions):
                f=Path(r['structure_check']['result_folder']);o=f'r{j}_original';m=f'r{j}_modified';images[o]=f/'Original_frame.png';images[m]=f/'Modified_frame.png';pairs.extend([dict(key=f'r{j}_self',probe=o,candidate=o),dict(key=f'r{j}_changed',probe=o,candidate=m)])
            tick=time.perf_counter();nbis=run_nbis_job(images,pairs,run_name=f'artifact_bench_{i}');nt=time.perf_counter()-tick
            tick=time.perf_counter();sa=run_matcher_job(images,pairs,run_name=f'artifact_bench_{i}');st=time.perf_counter()-tick
        row=dict(iteration=i,warmup=i==0,applied=details['applied'],detection_seconds=timing['detection_seconds'],boundary_seconds=timing['boundary_seconds'],transform_seconds=details.get('transform_seconds',0.),nbis_seconds=nt,sourceafis_seconds=st,total_seconds=time.perf_counter()-start,changed_pixels=details['changed_pixels'],outside_preserved=details['outside_all_masks_preserved'],regions=details.get('transformed_candidate_count',0),nbis=nbis,sourceafis=sa)
        rows.append(row);(folder/'benchmark_private.json').write_text(json.dumps(rows,indent=2));print(json.dumps({k:v for k,v in row.items() if k not in ['nbis','sourceafis']}),flush=True)
    measured=rows[1:];ok=[r for r in measured if r['applied']];no=[r for r in measured if not r['applied']]
    summary=dict(warmup=1,repetitions=repeats,applied_runs=len(ok),unchanged_runs=len(no),timing_success={k:stats([r[k] for r in ok]) for k in ['detection_seconds','boundary_seconds','transform_seconds','nbis_seconds','sourceafis_seconds','total_seconds']},timing_unchanged={k:stats([r[k] for r in no]) for k in ['detection_seconds','boundary_seconds','total_seconds']})
    (folder/'benchmark_summary.json').write_text(json.dumps(summary,indent=2));return summary


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',required=True,type=Path);p.add_argument('--output',required=True,type=Path);p.add_argument('--repeats',type=int,default=10);p.add_argument('--matchers',action='store_true');a=p.parse_args();print(json.dumps(benchmark(a.input,a.output,a.repeats,a.matchers),indent=2))

if __name__=='__main__':main()
