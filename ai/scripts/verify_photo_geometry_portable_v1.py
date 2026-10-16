"""Portable synthetic geometry reference; not full model or Linux parity proof."""
import argparse,hashlib,json,platform,sys
from pathlib import Path
import numpy as np
from photo_pixel_cell_support_v1 import resize_support
from photo_rotation_orbit_v1 import combine_restored_probabilities
from photo_owner_boundary_repair_v2 import repair_contexts
from photo_pitch_spectrum_diagnostic_v1 import diagnose_profile

VERSION='portable_photo_geometry_checks_v1'
def _sha(a):return hashlib.sha256(a.tobytes(order='C')).hexdigest()

def reference():
    checks={};cases=0
    for h,w in [(2,4),(17,29),(39,71)]:
        y,x=np.indices((h,w));mask=((y*13+x*19)%7)<2
        for H,W in [(1,1),(3,5),(21,37)]:
            result=resize_support(mask,(H,W));checks[f'cell-{h}-{w}-{H}-{W}']=_sha(result)
            for k in range(4):
                shape=(W,H) if k%2 else (H,W)
                if not np.array_equal(resize_support(np.rot90(mask,k).copy(),shape),np.rot90(result,k)):
                    raise RuntimeError('cell_rotation_failed')
                cases+=1
            if np.any(mask&~resize_support(result,list(mask.shape))):raise RuntimeError('cell_roundtrip_loss')
    y,x=np.indices((19,31));views=[(((y*13+x*17+k*3)%16).astype(np.float32)/16) for k in range(4)]
    mean=combine_restored_probabilities(views);checks['sorted_orbit_probability']=_sha(mean)
    for k in range(4):
        if not np.array_equal(mean,combine_restored_probabilities(views[k:]+views[:k])):raise RuntimeError('orbit_order_failed')
        cases+=1
    body=np.ones((17,29),bool);left=body.copy();left[:,13:]=False;right=body.copy();right[:,:14]=False
    mask=np.ones_like(body);mask[:2]=False
    contexts=[dict(body=left,candidate_id='left',reject_reason=None),dict(body=right,candidate_id='right',reject_reason=None)]
    repaired,audit=repair_contexts(contexts,body,mask)
    if audit['restored_pixels']!=0:raise RuntimeError('ambiguous_owner_assigned')
    checks['ambiguous_owners']=[_sha(r['body']) for r in repaired]
    gap=body.copy();gap[3:5,4:7]=False
    permission=np.zeros_like(body);permission[3:9,4:7]=True
    repaired,audit=repair_contexts([dict(body=gap,candidate_id='single',reject_reason=None)],body,permission)
    if audit['restored_pixels']!=6:raise RuntimeError('unique_owner_not_restored')
    checks['unique_owner']=_sha(repaired[0]['body']);cases+=2
    spectral={}
    for period in [3.2,4.2,8.,12.5,23.8,26.4]:
        value=128+50*np.cos(2*np.pi*np.arange(64)/period+.7)
        report=diagnose_profile(value,period)
        spectral[str(period)]=report['dominant_bin'];cases+=1
    checks['spectral_peak_bins']=spectral
    return dict(contract=VERSION,checks=checks,invariant_cases=cases,
        scope='synthetic geometry/reduction/diagnostics only; no CNN, renderer, matcher or privacy validation')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--compare',type=Path)
    args=parser.parse_args()
    if args.output.exists():raise FileExistsError('fresh_reference_output_required')
    result=reference();matched=None
    if args.compare is not None:
        expected=json.loads(args.compare.read_text(encoding='utf-8'))
        if expected.get('contract')!=VERSION or expected.get('checks')!=result['checks']:
            raise ValueError('portable_geometry_reference_mismatch')
        matched=True
    result.update(platform=platform.system(),python=platform.python_version(),numpy=np.__version__,
        compared_reference_exact=matched,full_model_parity_verified=False)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as stream:
        stream.write(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(status='passed',invariant_cases=result['invariant_cases'],compared_reference_exact=matched,
        platform=result['platform'],full_model_parity_verified=False)))

if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps(dict(status='error',error=type(error).__name__)));raise SystemExit(1)
