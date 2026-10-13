"""Explicit v1 experimental consumer. All image/evidence outputs are private."""
import argparse,json,hashlib
from dataclasses import asdict
from pathlib import Path
import cv2,numpy as np
from scipy import ndimage
from PIL import Image
from photo_coarse_adapter import adapt,orient,seed_square,square_scope
from external_ridge_pitch_observer import observe
from photo_external_pitch_v1 import render,frozen_observer_diagnostic

def protect(source,semantics,output):
    output=Path(output)
    if output.exists():raise FileExistsError('fresh_private_output_required')
    rgb,a=adapt(source,semantics);h,w=a['working_shape'];upright=orient(rgb,a['exif_orientation']);image=cv2.resize(upright,(w,h),interpolation=cv2.INTER_AREA if a['working_scale']<1 else cv2.INTER_CUBIC);body=cv2.resize(orient(a['body'].astype(np.uint8),a['exif_orientation']),(w,h),interpolation=cv2.INTER_NEAREST)>0;labels,n=ndimage.label(a['coarse_mask']);returned=rgb.copy();records=[];output.mkdir(parents=True)
    for i in range(1,n+1):
        native=labels==i;mask=cv2.resize(orient(native.astype(np.uint8),a['exif_orientation']),(w,h),interpolation=cv2.INTER_NEAREST)>0
        if (mask&~body).any():raise ValueError('pad_outside_finger_body')
        seed=seed_square(mask);scope,pad=square_scope(mask);e=observe(image,mask,a['source_sha256'],a['working_scale'],'normalized_working_pixels');f=frozen_observer_diagnostic(image,seed,mask,a['source_sha256'],a['working_scale'],'normalized_working_pixels');record=dict(component=i,evidence=asdict(e),frozen_diagnostic=asdict(f),applied=False)
        if e.pitch_value is not None and f.pitch_value is not None:record['internal_external_relative_difference']=abs(e.pitch_value-f.pitch_value)/((e.pitch_value+f.pitch_value)/2)
        try:
            if any(pad.values()):raise ValueError('renderer_padding_required')
            candidate,details=render(image,mask,seed,scope,e,a['source_sha256'],a['working_scale'],'normalized_working_pixels');record['transform']=details;record['applied']=details['applied'];record['reject_reason']=details['reject_reason']
        except ValueError as exc:record['reject_reason']=str(exc)
        if record['applied']:
            native_result=orient(cv2.resize(candidate,(upright.shape[1],upright.shape[0]),interpolation=cv2.INTER_CUBIC),a['exif_orientation'],True);returned[native]=native_result[native]
        records.append(record)
    if not np.array_equal(returned[~a['coarse_mask']],rgb[~a['coarse_mask']]):raise RuntimeError('mask_exterior_changed')
    if hashlib.sha256(Path(source).read_bytes()).hexdigest()!=a['source_sha256']:raise RuntimeError('source_changed')
    report=dict(version='photo_external_pitch_v1',source_sha256=a['source_sha256'],image_shape=list(rgb.shape[:2]),working_shape=[h,w],working_scale=a['working_scale'],coordinate_system='encoded_original_pixels',components=records,transformed=sum(r['applied'] for r in records),changed_pixels=int(np.any(returned!=rgb,axis=2).sum()),exterior_preserved=True,returned_RGB_sha256=hashlib.sha256(returned.tobytes()).hexdigest(),PHOTO_EXTERNAL_PITCH_EXPERIMENTAL=True,PHOTO_DETECTOR_APPROVED=False,PHOTO_PROTECTION_PRODUCTION_READY=False)
    Image.fromarray(returned).save(output/'returned.png');(output/'audit.private.json').write_text(json.dumps(report,indent=2,default=lambda v:v.item() if isinstance(v,np.generic) else str(v)));return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--semantics',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    from protect_fingerprint import cli_progress_to_stderr
    with cli_progress_to_stderr():report=protect(a.input,a.semantics,a.output)
    print(json.dumps(report,default=lambda v:v.item() if isinstance(v,np.generic) else str(v)))
