"""Explicit experimental frozen-renderer binding; no core/gate modifications."""
import threading,tempfile,time
from pathlib import Path
import hashlib
import numpy as np
import cv2
from photo_coarse_adapter import orient

_LOCK=threading.RLock()


def transform(rgb,artifact,strength=.5):
    import transform_automatic_fingerprint_poc_v4 as frozen
    import whole_pad_skin_relief as renderer
    import fingerprint_structure_check as structure
    from sourceafis_matcher import run_matcher_job
    from transform_automatic_fingerprint_poc_v4_boundaryblend_02 import transform_fingerprint_photo
    if hashlib.sha256(rgb.tobytes()).hexdigest()!=artifact['source_rgb_sha256']:raise ValueError('source_RGB_hash_mismatch')
    orientation=artifact['exif_orientation'];native_upright=orient(rgb,orientation);wh,ww=artifact['working_shape'];scale=artifact['working_scale'];original=cv2.resize(native_upright,(ww,wh),interpolation=cv2.INTER_AREA if scale<1 else cv2.INTER_CUBIC);h,w=original.shape[:2];parts=[]
    for entry in artifact['regions']:
        entry['roi'].validate(rgb,artifact['source_sha256']);mask=cv2.resize(orient(entry['roi'].binary_mask,orientation),(w,h),interpolation=cv2.INTER_NEAREST)>0;parts.append((entry,mask))
    right=max([e['padding']['right'] for e,_ in parts]+[0]);bottom=max([e['padding']['bottom'] for e,_ in parts]+[0]);working=np.pad(original,((0,bottom),(0,right),(0,0)),mode='edge');lookup={tuple(e['working_seed']):(e,np.pad(m,((0,bottom),(0,right)))) for e,m in parts}
    def scope(image,seed):
        if not np.array_equal(image,working):raise ValueError('working_source_mismatch')
        entry,mask=lookup[tuple(seed)];a,b,c,d=entry['working_scope'];return [a,b,c,d],mask[b:d,a:c],dict(status='experimental_hash_shape_validated_scope',automatic_boundary_accepted=False,detector_approved=False)
    with _LOCK:
        old=(frozen.detect_fingertips,frozen.propose_visible_pad,renderer.propose_visible_pad,structure.OUT,structure.run_matcher_job)
        try:
            frozen.detect_fingertips=lambda image:dict(candidates=[dict(candidate_id=f'coarse-{e["component"]}',seed_roi=e['working_seed']) for e,_ in parts],method='experimental_COLFISPOOF_coarse_binding')
            frozen.propose_visible_pad=scope;renderer.propose_visible_pad=scope;structure.OUT=Path(tempfile.mkdtemp(prefix='blurfing_photo_frozen_'));structure.run_matcher_job=run_matcher_job;tick=time.perf_counter();returned,details=transform_fingerprint_photo(working,strength,return_details=True);elapsed=time.perf_counter()-tick
        finally:frozen.detect_fingertips,frozen.propose_visible_pad,renderer.propose_visible_pad,structure.OUT,structure.run_matcher_job=old
    resized=cv2.resize(returned[:h,:w],(native_upright.shape[1],native_upright.shape[0]),interpolation=cv2.INTER_CUBIC);candidate=orient(resized,orientation,inverse=True);allowed=artifact['coarse_mask'];native=rgb.copy()
    applied_ids={int(r['candidate_id'].split('-')[-1]) for r in details['regions'] if r.get('applied')}
    applied_mask=np.zeros(rgb.shape[:2],bool)
    for entry in artifact['regions']:
        if entry['component'] in applied_ids:applied_mask|=entry['roi'].binary_mask>0
    native[applied_mask]=candidate[applied_mask]
    if not np.array_equal(native[~applied_mask],rgb[~applied_mask]):raise RuntimeError('unapplied_region_changed')
    details['working_changed_pixels']=details['changed_pixels'];details['changed_pixels']=int(np.any(native!=rgb,axis=2).sum());details['transformed_pad_count']=len(applied_ids)
    if native.shape!=rgb.shape or not np.array_equal(native[~allowed],rgb[~allowed]):raise RuntimeError('PHOTO_boundary_exterior_changed')
    details.update(experimental_adapter='photo_coarse_renderer_adapter_v1',input_rotation='exact EXIF permutation plus explicit geometry width normalization',working_scale=scale,working_shape=[h,w],square_padding=dict(right=right,bottom=bottom),pitch_clamped=False,PHOTO_DETECTOR_APPROVED=False,PHOTO_PROTECTION_PRODUCTION_READY=False,exterior_preserved=True,renderer_and_structure_seconds=elapsed,returned_rgb_sha256=hashlib.sha256(native.tobytes()).hexdigest())
    return native,details
