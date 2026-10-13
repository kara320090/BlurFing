"""Actual-Windows single-case parity probe; cannot establish full equivalence."""
import argparse,json,platform,sys,hashlib,tempfile
from pathlib import Path
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'scripts'))
from protect_fingerprint import protect_image,cli_progress_to_stderr

def validate(source,reference_json,reference_image,output):
    if platform.system()!='Windows':return dict(status='NOT_RUN',reason='actual_Windows_execution_required',WINDOWS_FULL_EQUIVALENCE_VERIFIED=False)
    reference=json.loads(Path(reference_json).read_text())
    if hashlib.sha256(Path(source).read_bytes()).hexdigest()!=reference['source_sha256']:raise ValueError('source_hash_mismatch')
    image,r=protect_image(source,output);expected=np.asarray(Image.open(reference_image).convert('RGB'));same_shape=image.shape==expected.shape
    fields=['input_type','status','fingerprints_detected','fingerprints_transformed','fingerprints_rejected'];same_outcome=all(r[k]==reference[k] for k in fields);regions=lambda data:[{k:z.get(k) for k in ['quality_status','reason','mask_pixel_sha256']} for z in data['regions']];same_regions=regions(r)==regions(reference);pixel_equal=same_shape and np.array_equal(image,expected)
    report=dict(status='measured',CASE_EQUIVALENCE_PASS=bool(pixel_equal and same_outcome and same_regions),same_source=True,same_shape=same_shape,same_outcome=same_outcome,same_region_signatures=same_regions,pixel_identical=bool(pixel_equal),max_pixel_error=int(np.abs(image.astype(int)-expected.astype(int)).max()) if same_shape else None,WINDOWS_FULL_EQUIVALENCE_VERIFIED=False,scope='one case only; complete PHOTO/scanner/rejection/GUI/runtime matrix still required')
    (Path(output)/'windows_case.private.json').write_text(json.dumps(report,indent=2));return report
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--reference-json',type=Path,required=True);p.add_argument('--reference-image',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    with cli_progress_to_stderr():report=validate(a.input,a.reference_json,a.reference_image,a.output)
    print(json.dumps(report))
