"""Stable per-pad outcomes. Low quality is a normal fail-closed rejection."""
import hashlib,json,os,subprocess,tempfile,time
from pathlib import Path
import numpy as np
from PIL import Image
from scipy import ndimage
from photo_coarse_adapter_v2 import adapt
from photo_coarse_renderer_adapter_v1 import transform

STATES=('TRANSFORMED','REJECT_WIDTH_UNAVAILABLE','REJECT_PITCH_UNOBSERVED','REJECT_PITCH_UNSTABLE','REJECT_INSUFFICIENT_FEATURES','REJECT_RENDERER_CONTRACT','REJECT_OTHER')
def state(reason):
    if reason in ['original_width_unavailable','native_body_width_boundary_unobserved']:return STATES[1]
    if reason in ['pitch_unobserved','no_periodicity','no_ridges','body_supported_pitch_unobserved','body_supported_seed_unavailable']:return STATES[2]
    if reason in ['pitch_unstable','cue_disagreement','unstable_orientation','insufficient_patches','multi_patch_disagreement']:return STATES[3]
    if reason=='insufficient_features':return STATES[4]
    if reason in ['renderer_pitch_out_of_range','renderer_padding_required','square_scope_contract','scope_drops_mask','coarse_pad_too_small_for_seed']:return STATES[5]
    return STATES[6]

def pitch_failure_reason(measurement):
    for attempt in measurement.get('attempts',[]):
        observed=attempt.get('measurement',{})
        if observed.get('status') in ['inconsistent','scale_disagreement']:return 'pitch_unstable'
        if any(z.get('status')=='inconsistent' or z.get('selection',{}).get('status')=='inconsistent' for z in observed.get('scales',[])):return 'pitch_unstable'
    return 'pitch_unobserved'

def summarize(regions):
    n=len(regions);applied=sum(r['quality_status']=='TRANSFORMED' for r in regions)
    return dict(status='success' if n and applied==n else 'partial_success' if applied else 'rejected',fingerprints_detected=n,fingerprints_transformed=applied,fingerprints_rejected=n-applied,regions=regions,quality_gate_version='photo_quality_gate_v2',PHOTO_DETECTOR_APPROVED=False,PHOTO_PROTECTION_PRODUCTION_READY=False,PHOTO_FAIL_CLOSED_PIPELINE_READY=True)

def evaluate(source,semantics=None,detect_only=False):
    tick=time.perf_counter();inference=0.
    if semantics is None:
        config=[os.environ.get(k) for k in ['BLURFING_COLFISPOOF_PYTHON','BLURFING_COLFISPOOF_SOURCE','BLURFING_COLFISPOOF_MODEL']]
        if not all(config):
            rgb=np.asarray(Image.open(source).convert('RGB')).copy();return rgb,summarize([])|dict(reject_reason='photo_runtime_not_configured',timing=dict(total=time.perf_counter()-tick))
        folder=Path(tempfile.mkdtemp(prefix='blurfing_photo_semantics_'))/'semantics';start=time.perf_counter()
        cmd=[config[0],str(Path(__file__).with_name('colfispoof_body_semantics.py')),'--input',str(Path(source).resolve()),'--output',str(folder),'--external-source',config[1],'--model',config[2]]
        subprocess.run(cmd,check=True,timeout=300,shell=False,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE);inference=time.perf_counter()-start;semantics=folder
    start=time.perf_counter();rgb,a=adapt(source,semantics);adapter=time.perf_counter()-start;labels,n=ndimage.label(a['coarse_mask']);before=a['coarse_mask'].copy()
    if detect_only:returned=rgb.copy();details=dict(regions=[],transformed_pad_count=0,exterior_preserved=True)
    elif a.get('working_shape') is None:returned=rgb.copy();details=dict(regions=[],transformed_pad_count=0,exterior_preserved=True)
    else:returned,details=transform(rgb,a)
    statuses={int(r['candidate_id'].split('-')[-1]):r for r in details['regions']};rejected={r['component']:r for r in a['rejected']};regions=[]
    for i in range(1,n+1):
        native=labels==i;r=statuses.get(i,{});reason=rejected.get(i,{}).get('reject_reason') or r.get('structure_check',{}).get('reason') or r.get('status') or ('detect_only' if detect_only else 'renderer_contract_not_satisfied');applied=bool(r.get('applied'));quality='TRANSFORMED' if applied else state(reason)
        evidence=rejected.get(i,{}).get('pitch_measurement',{})
        if reason=='pitch_unobserved':reason=pitch_failure_reason(evidence);quality=state(reason)
        if not applied and not np.array_equal(returned[native],rgb[native]):raise RuntimeError('rejected_pad_pixels_changed')
        regions.append(dict(region_id=i,status='transformed' if applied else 'rejected',quality_status=quality,reason=None if applied else reason,feature_evidence=r.get('structure_check',{}).get('minutiae'),observed_pitch_working=r.get('primary_observation',{}).get('pitch_native'),pitch_evidence_summary=[dict(method=z.get('preprocessing'),status=z.get('measurement',{}).get('status'),patch_count=z.get('measurement',{}).get('count')) for z in evidence.get('attempts',[])],mask_pixels=int(native.sum()),mask_pixel_sha256=hashlib.sha256(native.tobytes()).hexdigest()))
    if not np.array_equal(before,a['coarse_mask']) or not np.array_equal(returned[~before],rgb[~before]):raise RuntimeError('mask_exterior_changed')
    return returned,summarize(regions)|dict(exterior_preserved=True,changed_pixels=int(np.any(returned!=rgb,axis=2).sum()),returned_RGB_sha256=hashlib.sha256(returned.tobytes()).hexdigest(),detector='COLFISPOOF_class1+2_finger_body_distal_v2',renderer='frozen natural_auto_04 + boundaryblend_02 through existing experimental adapter',coarse_mask=before,adapter_version=a.get('adapter_version'),resize_audit=a.get('resize_audit'),timing=dict(COLFISPOOF=inference,coarse_and_canonical=adapter,renderer_and_structure=details.get('renderer_and_structure_seconds',0.),total=time.perf_counter()-tick))
