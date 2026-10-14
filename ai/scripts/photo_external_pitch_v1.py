"""Explicit external-pitch experimental entrypoint; no frozen observer patching.

Renderer: unchanged low-level whole_pad_skin_relief, not natural_auto_04 /
boundaryblend_02 equivalence. Scope injection uses a private globals dictionary
with the original function code object; no global binding is mutated.
"""
import hashlib,types
import cv2,numpy as np
from external_pitch_evidence import ExternalPitchEvidence

def render(image,mask,seed_roi,scope,evidence,source_sha,image_scale=1.,coordinate_space='native_source_pixels'):
    from whole_pad_skin_relief import render_whole_pad_candidate
    from contactless_finger_width import estimate_finger_width
    from fingerprint_structure_check import check_structure_change
    if image.dtype!=np.uint8 or image.ndim!=3 or image.shape[2]!=3 or mask.dtype!=np.bool_ or mask.shape!=image.shape[:2] or not mask.any():raise ValueError('image_mask_contract')
    conversion=evidence.validate(source_sha,hashlib.sha256(mask.tobytes()).hexdigest(),mask.shape,coordinate_space,image_scale,observed_image_pixel_sha256=hashlib.sha256(cv2.cvtColor(image,cv2.COLOR_RGB2GRAY).tobytes()).hexdigest())
    a,b,c,d=scope;h,w=mask.shape
    if not 0<=a<c<=w or not 0<=b<d<=h or c-a!=d-b:raise ValueError('square_scope_contract')
    inside=np.zeros_like(mask);inside[b:d,a:c]=True
    if (mask&~inside).any():raise ValueError('scope_drops_mask')
    width=estimate_finger_width(image,seed_roi);audit=dict(version='photo_external_pitch_v1',PHOTO_EXTERNAL_PITCH_EXPERIMENTAL=True,PHOTO_DETECTOR_APPROVED=False,PHOTO_PROTECTION_PRODUCTION_READY=False,conversion=conversion,width=width,evidence_hash=evidence.evidence_hash,renderer='unchanged whole_pad_skin_relief; not natural_auto_04/boundaryblend_02 equivalence',applied=False)
    if width['status']!='estimated':return image.copy(),audit|dict(reject_reason='original_width_unavailable',exterior_preserved=True)
    def scoped(original,seed):
        if not np.array_equal(original,image) or list(seed)!=list(seed_roi):raise ValueError('renderer_scope_source_mismatch')
        return scope,mask[b:d,a:c],dict(status='external_pitch_validated_experimental_scope')
    globals_copy=render_whole_pad_candidate.__globals__.copy();globals_copy['propose_visible_pad']=scoped
    function=types.FunctionType(render_whole_pad_candidate.__code__,globals_copy,render_whole_pad_candidate.__name__)
    seed=int(hashlib.sha256(image[seed_roi[1]:seed_roi[3],seed_roi[0]:seed_roi[2]].tobytes()).hexdigest()[:8],16)
    candidate,details=function(image,seed_roi,pitch_native=conversion['pitch_renderer'],seed=seed)
    if not np.array_equal(candidate[~mask],image[~mask]):raise RuntimeError('mask_exterior_changed')
    check=check_structure_change(image,candidate,seed_roi);audit.update(renderer_result=details,structure_check=check,exterior_preserved=True)
    if not check['structure_change_passed']:return image.copy(),audit|dict(reject_reason=check['reason'])
    return candidate,audit|dict(applied=True,reject_reason=None,changed_pixels=int(np.any(candidate!=image,axis=2).sum()))


def frozen_observer_diagnostic(image,seed_roi,mask,source_sha,image_scale=1.,coordinate_space='native_source_pixels'):
    from protect_visible_pad_checked_v2 import observed_seed_pitch
    pitch,measurement,_=observed_seed_pitch(image,seed_roi)
    # This backend does not supply two independent cues and cannot authorize v1.
    return ExternalPitchEvidence(pitch,'pixels',coordinate_space,image_scale,0.,'frozen_seed_pitch','v4',0,0,dict(autocorrelation=dict(valid=False,pitch=None),fft=dict(valid=False,pitch=None),frozen_measurement=measurement),dict(passed=False,orientation_consistent=False,diagnostic_only=True),'',source_sha,hashlib.sha256(mask.tobytes()).hexdigest(),list(mask.shape),'insufficient_patches' if pitch is not None else 'no_periodicity').seal()
