"""Opt-in semantic-TIP + observed-pose proposal, without the V6 tile pipeline.

Only independent semantic TIP observations authorize a digit. Unsupported
    digits stay unselected; no rectangle, learned-mask surrogate or best seed is
used. Existing RGB boundary refinement/crease anchoring still decides caps.
This experimental speed/coverage tradeoff is distinct from the V6 path.
"""
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image

VERSION='semantic_TIP_observed_pose_v32_experimental'


def partition(mask,owners,selected_labels,*,maximum=128):
    """Atomic observed-digit groups, including disconnected rejected pieces.

    No mask pixel is removed or promoted. One uncertain piece rejects its
    entire digit group. Leftover pixels form one unassigned review group.
    """
    from photo_partial_pose_v25 import partition_candidates
    partition_candidates(mask,owners,selected_labels,maximum=maximum)
    labels=np.zeros(mask.shape,np.uint16);count=0
    for owner in selected_labels:
        take=mask&(owners==owner)
        if take.any():count+=1;labels[take]=count
    remainder=mask&~np.isin(owners,selected_labels)
    if remainder.any():count+=1;labels[remainder]=count
    if count>maximum:raise ValueError('partial_pose_candidate_limit')
    if not np.array_equal(labels>0,mask):raise RuntimeError('semantic_pose_candidate_pixel_loss')
    return labels,count


def propose(source,model,registry_path,output,*,allow_development_replay=False,
        minimal_artifacts=True,partial_observed_pose=True,execution_context=None):
    from photo_source_rgb_v1 import canonical_rgb
    from photo_consumed_replay_v1 import development_replay
    from photo_new_input_v23 import review_candidates,json_write,file_hash
    from photo_partial_pose_v25 import geometry_from_worker
    from photo_pose_native_pipeline_v1 import verify_worker
    from photo_rounded_pad_v1 import rounded_pads
    from photo_crease_native_adapter_v1 import prepare
    from photo_region_pipeline_v1 import load_semantics
    from pad_refinement_data_contract_v2 import source_record,verify_source
    import pad_refinement_tiles_v3 as tiles
    if execution_context is None or not minimal_artifacts or not partial_observed_pose:
        raise ValueError('semantic_pose_requires_owned_automatic_context')
    source,output=Path(source),Path(output)
    rgb,identity=canonical_rgb(source);before=file_hash(source)
    registry,registry_sha=tiles.json_snapshot(registry_path);tiles.validate_registry(registry)
    with development_replay(registry,[tiles.image_identity(source)],enabled=allow_development_replay):
        tiles.exclude_consumed(tiles.image_identity(source),registry)
    observation=output/'hand.private.json';semantics=output/'semantics'
    with ExitStack() as jobs:
        semantic=jobs.enter_context(execution_context.semantic_job(source.resolve(),semantics.resolve()))
        hand=jobs.enter_context(execution_context.hand_job(source.resolve(),observation.resolve()))
        semantic.finish();hand.finish()
    body,tip,_=load_semantics(source,rgb,semantics)
    record=source_record(source,'INPUT',semantics,rgb);verify_source(record,'inference')
    worker=json.loads(observation.read_text('utf-8'));verify_worker(record,rgb,worker)
    pose,diagnostic=geometry_from_worker(record,rgb,worker,learned_support=None)
    owners=np.zeros(body.shape,np.uint8);mask=np.zeros(body.shape,bool);baseline=mask.copy();review_baseline=baseline.copy()
    unanchored=mask.copy();boundary=dict(candidates=[],axis_source='observed_pose_IP_DIP_to_TIP')
    owner_binding=None
    if pose is not None:
        # No estimator result is fabricated. Coarse inputs are deliberately
        # empty and unused by the observed-pose branch of the existing adapter.
        baseline,rounding=rounded_pads(pose['permission_labels']>0,np.zeros_like(body),body,tip,pose_geometry=pose)
        review_baseline=baseline.copy()
        from photo_pose_extent_guard_v32 import bounded_caps
        baseline,rounding=bounded_caps(baseline,rounding,pose)
        derived,mask,boundary,pose=prepare(record,rgb,baseline,rounding,worker,output/'crease',
            partial_observed_pose=True,pose_only=True,search_crease=False)
        if pose is None:raise ValueError('semantic_pose_lost_after_RGB_refinement')
        owners=pose['owner_labels'];selected=[axis['label'] for axis in pose['axes']]
        for row in boundary['candidates']:
            if row.get('unanchored_candidate_excluded'):
                axis=next(a for a in pose['axes'] if 'pose-'+a['digit']==row['candidate_id'])
                unanchored|=owners==axis['label']
        unanchored|=~np.isin(owners,selected)
        owner_binding=dict(pixel_sha256=hashlib.sha256(owners.tobytes()).hexdigest(),selected_labels=selected)
    candidate,selection=review_candidates(review_baseline,mask,unanchored)
    for name,array in [('proposal',candidate),('boundary_refined_mask',mask),('unanchored_owners',unanchored)]:
        Image.fromarray(array.astype(np.uint8)*255).save(output/(name+'.png'))
    if owner_binding is not None:Image.fromarray(owners).save(output/'pose_owners.png')
    boundary.update(proposal_engine=VERSION,V6_learned_pad_model_used=False,semantic_TIP_support_required=True,
        initial_pose=diagnostic,unobserved_digits_inferred=False,whole_photo_coverage_verified=False)
    json_write(output/'boundary.private.json',boundary)
    json_write(output/'proposal.private.json',dict(source_sha256=before,input_type='PHOTO',candidate_selection=selection,
        partial_pose=owner_binding,candidate_only=True,human_reviewed=False,independent_validation=False,
        proposal_engine=VERSION,V6_learned_pad_model_used=False,semantic_TIP_support_required=True))
    verify_source(record,'inference');tiles.unchanged(source,before);tiles.unchanged(registry_path,registry_sha)
