"""Explicit derived BODY provenance for the opt-in RGB/crease boundary path."""
import hashlib,json
from pathlib import Path
import numpy as np
from PIL import Image
from pad_refinement_data_contract_v2 import (verify_source,read_body,read_mask,native_shape,
    checked_bytes,digest,read_source_rgb)
from photo_rgb_body_refinement_v1 import refine_body,VERSION as EDGE_VERSION,CONFIG as EDGE_CONFIG
from photo_crease_pad_v1 import crease_pads
from photo_pose_native_pipeline_v1 import geometry_from_worker
from photo_coarse_cache_v31 import estimate

KIND='RGB_REFINED_BODY_V1'


def verify_derived_semantics(source,semantic,purpose):
    if purpose!='inference':raise ValueError('RGB_refined_BODY_is_inference_only')
    original=semantic.get('original_source_record')
    if not isinstance(original,dict):raise ValueError('RGB_body_original_record_required')
    parent=json.loads(checked_bytes(original['semantics_path'],original['semantics_sha256']))
    if parent.get('kind')==KIND or 'original_source_record' in parent:
        raise ValueError('nested_RGB_body_derivation_forbidden')
    verify_source(original,'inference')
    for key in ['source_id','source_path','source_sha256','source_RGB_sha256','source_exif_orientation','coordinate_system','height','width']:
        if source.get(key)!=original.get(key):raise ValueError('RGB_body_source_lineage_mismatch:'+key)
    if (semantic.get('kind')!=KIND or semantic.get('body_sha256')!=source.get('body_sha256') or
        semantic.get('tip_sha256')!=source.get('tip_sha256') or semantic.get('source_sha256')!=source.get('source_sha256') or
        semantic.get('coordinate_system')!='encoded_original_pixels' or semantic.get('raw_COLFISPOOF_output') is not False):
        raise ValueError('RGB_body_derived_binding_mismatch')
    edge=semantic.get('edge_refinement',{});body=read_body(source);parent_body=read_body(original)
    if (edge.get('version')!=EDGE_VERSION or edge.get('configuration')!=EDGE_CONFIG or
        edge.get('input_RGB_sha256')!=source['source_RGB_sha256'] or
        edge.get('original_body_pixel_sha256')!=hashlib.sha256(parent_body.tobytes()).hexdigest() or
        edge.get('refined_body_pixel_sha256')!=hashlib.sha256(body.tobytes()).hexdigest()):
        raise ValueError('RGB_body_edge_provenance_mismatch')
    parent_tip=read_mask(original['tip_path'],original['tip_sha256'],native_shape(original))
    tip=read_mask(source['tip_path'],source['tip_sha256'],native_shape(source))
    if not np.array_equal(tip,parent_tip&body):raise ValueError('RGB_body_tip_lineage_mismatch')


def prepare(source,rgb,before,rounding,worker,output,*,partial_observed_pose=False,learned_support=None):
    """Preserve original assets and write separately hash-bound derived masks."""
    verify_source(source,'inference')
    if not np.array_equal(rgb,read_source_rgb(source['source_path'],source['source_sha256'])):
        raise ValueError('RGB_body_original_pixels_changed')
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    body=read_body(source);tip=read_mask(source['tip_path'],source['tip_sha256'],native_shape(source))
    if learned_support is not None and (
        not isinstance(learned_support,np.ndarray) or learned_support.dtype!=np.bool_
        or learned_support.shape!=body.shape or np.any(learned_support&~body)):
        raise ValueError('partial_pose_learned_support_contract')
    refined,edge=refine_body(rgb,body,rounding)
    tip=tip&refined
    for name,mask in [('body',refined),('tip',tip)]:
        Image.fromarray(mask.astype(np.uint8)*255).save(output/(name+'.png'))
    derived=dict(source,body_path=str((output/'body.png').resolve()),body_sha256=digest(output/'body.png'),
        tip_path=str((output/'tip.png').resolve()),tip_sha256=digest(output/'tip.png'),
        semantics_path=str((output/'semantics.json').resolve()))
    # Coarse/tile records remain exclusively in the original detector manifest.
    for key in ['coarse_path','coarse_sha256','crop_count']:derived.pop(key,None)
    semantic=dict(kind=KIND,source_sha256=source['source_sha256'],coordinate_system=source['coordinate_system'],
        body_sha256=derived['body_sha256'],tip_sha256=derived['tip_sha256'],raw_COLFISPOOF_output=False,
        original_source_record=source,edge_refinement=edge,original_geometry=rounding,
        GT_used=False,anatomical_boundary_verified=False)
    (output/'semantics.json').write_text(json.dumps(semantic,indent=2),encoding='utf-8')
    derived['semantics_sha256']=digest(output/'semantics.json');verify_source(derived,'inference')
    if type(partial_observed_pose) is not bool:raise ValueError('partial_observed_pose_flag_must_be_boolean')
    pose_detail=None
    if partial_observed_pose and worker is not None:
        from photo_partial_pose_v25 import geometry_from_worker as partial_geometry
        pose,pose_detail=partial_geometry(derived,rgb,worker,
            learned_support=(learned_support&refined if learned_support is not None else None))
        pose_detail['learned_support_before_RGB_refinement_sha256']=(
            hashlib.sha256(learned_support.tobytes()).hexdigest() if learned_support is not None else None)
    else:
        pose=geometry_from_worker(derived,rgb,worker) if worker is not None and worker['hand_count']==1 else None
    coarse=estimate(refined,tip,preserve_candidates=True)['mask']
    mask,metadata=crease_pads(rgb,before&refined,coarse,refined,tip,pose_geometry=pose)
    (output/'source.private.json').write_text(json.dumps(derived,indent=2),encoding='utf-8')
    metadata['RGB_edge_refinement']=edge
    if partial_observed_pose:metadata['partial_pose']=pose_detail
    return derived,mask,metadata,pose
