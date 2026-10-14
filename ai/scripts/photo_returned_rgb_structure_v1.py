"""Validate actual returned native RGB with unchanged working-coordinate gates."""
import tempfile,hashlib
from pathlib import Path
import cv2,numpy as np
import photo_region_pipeline_v1 as shared
from contactless_finger_width_body_v1 import estimate_finger_width_body


def returned_structure_check(original,candidate,artifact,axis,report):
    region=report['regions'][0]
    if region.get('applied') is not True:return candidate,report
    import fingerprint_structure_check as structure
    from sourceafis_matcher import run_matcher_job
    height,width=artifact['working_shape'];orientation=artifact['exif_orientation'];scale=artifact['working_scale']
    interpolation=cv2.INTER_AREA if scale<1 else cv2.INTER_CUBIC
    first=cv2.resize(shared.orient(original,orientation),(width,height),interpolation=interpolation)
    final=cv2.resize(shared.orient(candidate,orientation),(width,height),interpolation=interpolation)
    body=cv2.resize(shared.orient(artifact['body'].astype(np.uint8),orientation),(width,height),interpolation=cv2.INTER_NEAREST)>0
    padding=artifact['regions'][0]['padding'];pad=((0,padding['bottom']),(0,padding['right']))
    first=np.pad(first,pad+((0,0),),mode='edge');final=np.pad(final,pad+((0,0),),mode='edge')
    body=np.pad(body,pad,constant_values=False);seed=artifact['regions'][0]['working_seed']
    def observe(image,box):
        if image is not first or list(box)!=seed:raise ValueError('returned_RGB_width_source_contract')
        return estimate_finger_width_body(image,box,axis,body,image_shape=(height,width))
    with shared.renderer_binding._LOCK:
        old=structure.estimate_finger_width,structure.OUT,structure.run_matcher_job
        try:
            structure.estimate_finger_width=observe;structure.OUT=Path(tempfile.mkdtemp(prefix='blurfing_returned_RGB_'))
            structure.run_matcher_job=run_matcher_job
            check=structure.check_structure_change(first,final,seed)
        finally:structure.estimate_finger_width,structure.OUT,structure.run_matcher_job=old
    region['working_renderer_structure_check']=region['structure_check']
    region['returned_RGB_structure_check']=check
    region['structure_check']=check
    report['structure_checked_on_actual_native_return']=True
    if check.get('structure_change_passed') is not True:
        region.update(applied=False,status='returned_RGB_structure_rejected')
        report.update(applied=False,transformation_function_passed=False,transformed_candidate_count=0,
            all_detected_candidates_transformed=False,transformed_pad_count=0,changed_pixels=0,
            status='returned_RGB_structure_rejected_original_returned',returned_rgb_sha256=hashlib.sha256(original.tobytes()).hexdigest())
        return original.copy(),report
    if np.array_equal(original,candidate):raise ValueError('renderer_success_without_native_RGB_change')
    return candidate,report
