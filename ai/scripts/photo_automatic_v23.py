"""Automatic V23 renderer with explicit ridge or precautionary surface selection.

This is a new, explicitly uncalibrated selection policy. It does not promote
diagnostic output to a human label, relax legacy gates, or claim full coverage.
The surface policy never reclassifies uncertain ridge visibility as observed.
Unanchored boundaries and unresolved rendering remain non-application outcomes.
"""
import json
import time
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
from scipy import ndimage
from photo_visibility_peak_train_probe_v4 import CONFIG, _geometry
from photo_visibility_joint_witness_v11 import inspect_patch
from photo_visibility_support_v1 import full_area_support
from photo_visibility_reviewed_apply_v1 import render_selected_regions, pixels
from photo_experimental_transport_v1 import (
    ValidatedExperimentalPhotoResult, encoded_mask, png, verify_wire_png,
    MAX_RETURNED_PNG_BYTES,
)

ENGINE = 'synthetic_v23'
POLICY = 'anchored_joint_witness_v1_experimental'
SURFACE_POLICY = 'model_anchored_surface_precaution_v26_experimental'
PRECAUTIONARY_REASON = 'TRANSFORMED_PRECAUTIONARY_SURFACE'
AUTOMATIC_POLICIES = ('surface_v26', 'strict_ridge_v23')
MAX_INSPECTED_WINDOWS = 4096
MAX_CANDIDATES = 128


def observe(rgb, mask, *, max_windows=MAX_INSPECTED_WINDOWS):
    """Bounded deterministic search; a negative is uncertainty, never absence."""
    if (rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3
            or mask.dtype != np.bool_ or mask.shape != rgb.shape[:2]
            or type(max_windows) is not int or not 1 <= max_windows <= MAX_INSPECTED_WINDOWS):
        raise ValueError('automatic_observation_contract')
    yy, xx = np.where(mask)
    record = dict(version=POLICY, observed=False, visibility='uncertain',
                  absence_inferred=False, inspected_windows=0, budget_exhausted=False,
                  classifier_validated=False, human_GT=False, levels=[])
    if not len(xx):
        return record
    y0,y1,x0,x1 = int(yy.min()),int(yy.max()+1),int(xx.min()),int(xx.max()+1)
    crop = rgb[y0:y1,x0:x1]
    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY).astype(np.float64)
    support = mask[y0:y1,x0:x1]
    record['source_bbox_xyxy'] = [x0,y0,x1,y1]
    visited_sizes = set()
    for limit in (640, 1280):
        ratio = min(1., limit / max(gray.shape))
        size = (max(1, round(gray.shape[1]*ratio)), max(1, round(gray.shape[0]*ratio)))
        if size in visited_sizes:
            continue
        visited_sizes.add(size)
        small = cv2.resize(gray, size, interpolation=cv2.INTER_AREA)
        allowed = full_area_support(support, size)
        level = dict(shape_yx=[size[1],size[0]], resize_yx=[size[1]/gray.shape[0],size[0]/gray.shape[1]])
        record['levels'].append(level)
        for n in CONFIG.windows:
            xs = list(range(0,size[0]-n+1,CONFIG.stride))
            ys = list(range(0,size[1]-n+1,CONFIG.stride))
            accepted = np.zeros((len(ys),len(xs)),bool)
            geometry = _geometry(n)
            for iy,y in enumerate(ys):
                for ix,x in enumerate(xs):
                    if not allowed[y:y+n,x:x+n].all():
                        continue
                    if record['inspected_windows'] >= max_windows:
                        record['budget_exhausted'] = True
                        return record
                    record['inspected_windows'] += 1
                    witness,_ = inspect_patch(small[y:y+n,x:x+n],geometry)
                    if witness is None:
                        continue
                    accepted[iy,ix] = True
                    cc,count = ndimage.label(accepted,np.ones((3,3),np.uint8))
                    sizes = np.bincount(cc.ravel(),minlength=count+1);sizes[0] = 0
                    if sizes.max() >= CONFIG.min_connected_windows:
                        record.update(observed=True,visibility='ridge_evidence_observed_uncalibrated',
                                      connected_windows=int(sizes.max()),window=n,
                                      witness_working_xy=[x,y],witness=witness)
                        return record
    return record


def apply_candidates(rgb, labels, boundary_mask, *, seed=None, observer=observe, surface_permission=None, fit_pool=None):
    if (rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3
            or labels.dtype != np.uint16 or labels.shape != rgb.shape[:2]
            or boundary_mask.dtype != np.bool_ or boundary_mask.shape != labels.shape
            or np.any(boundary_mask & (labels == 0))):
        raise ValueError('automatic_candidate_contract')
    if surface_permission is not None and (
            not isinstance(surface_permission,np.ndarray) or surface_permission.dtype!=np.bool_
            or surface_permission.shape!=labels.shape or np.any(surface_permission&~boundary_mask)):
        raise ValueError('automatic_surface_permission_contract')
    ids = [int(i) for i in np.unique(labels) if i]
    if len(ids) > MAX_CANDIDATES:
        raise ValueError('automatic_candidate_limit')
    selected=[];rows=[];evidence=[]
    for rid in ids:
        target=labels==rid
        if np.any(target & ~boundary_mask):
            observation=dict(observed=False,visibility='uncertain',reason='REJECT_BOUNDARY_UNCERTAIN')
        else:
            observation=observer(rgb,target)
            observation=dict(observation,reason='TRANSFORMED' if observation['observed'] else
                             ('REJECT_OBSERVATION_BUDGET' if observation['budget_exhausted'] else 'REJECT_VISIBILITY_UNCERTAIN'))
        precautionary=(not observation['observed'] and surface_permission is not None
                       and bool(surface_permission[target].all()))
        if precautionary:
            observation=dict(observation,reason=PRECAUTIONARY_REASON,
                selection_source='model_supported_surface_precaution',ridge_visibility_confirmed=False)
        elif observation['observed']:
            observation['selection_source']='raw_ridge_witness'
        if observation['observed'] or precautionary:
            selected.append(rid)
        evidence.append(dict(region_id=rid,**observation))
        rows.append(dict(region_id=rid,automatic_decision=observation['visibility'],
                         reason_code=observation['reason'],status='pending_render' if rid in selected else 'review_required'))
    from photo_junction_fit_runtime_v1 import fit_session
    precautionary_ids={r['region_id'] for r in evidence if r['reason']==PRECAUTIONARY_REASON}
    with fit_session(**(dict(pool=fit_pool) if fit_pool is not None else {})):
        returned,applied,report=render_selected_regions(rgb,labels,selected,rows,seed=seed,appearance='junction_v23',
            **(dict(generated_detail_regions=sorted(precautionary_ids)) if precautionary_ids else {}))
    # The common renderer has no authority to assign human provenance.
    report.update(version='automatic_synthetic_v23_v26',
                  selection_basis=SURFACE_POLICY if surface_permission is not None else POLICY,
                  human_reviewed=False,evidence=evidence,automatic_visibility_approved=False)
    for row in report['regions']:
        if row['status']=='synthetic_applied_unverified':
            row['reason_code']=PRECAUTIONARY_REASON if row['region_id'] in precautionary_ids else 'TRANSFORMED'
        elif row['region_id'] in selected:
            row['reason_code']='REJECT_RENDERER_UNRESOLVED'
    report['precautionary_applied_region_count']=sum(
        r['reason_code']==PRECAUTIONARY_REASON for r in report['regions'])
    return returned,applied,report


def recover_proposal(rgb, mask, boundary, proposal):
    """Only new automatic path uses V24 recovery; legacy/UI masks are retained."""
    from photo_local_axis_v24 import recover
    from pad_refinement_data_contract_v2 import verify_source,read_body,read_mask,native_shape
    from finger_body_distal_estimator import estimate
    from photo_candidate_context_v1 import candidate_contexts
    from photo_native_owner_context_v1 import restore_contexts
    from photo_native_partition_edges_v1 import restore_edges
    metadata_path=Path(proposal)/'boundary.private.json'
    if not metadata_path.is_file():
        return mask,boundary,dict(version='local_axis_observed_crease_v24',regions=[])
    metadata=json.loads(metadata_path.read_text('utf-8'))
    failed={r['candidate_id'] for r in metadata['candidates'] if r.get('unanchored_candidate_excluded')}
    if not failed:
        return mask,boundary,dict(version='local_axis_observed_crease_v24',regions=[])
    if metadata.get('axis_source') == 'observed_pose_IP_DIP_to_TIP':
        # Pose digit owners and estimator owners have different identities.
        # An unresolved pose cap stays unapproved; never look it up as an
        # estimator candidate or discard already valid neighbouring digits.
        return mask,boundary,dict(version='local_axis_observed_crease_v24',regions=[
            dict(candidate_id=identity,recovered=False,reason='observed_pose_boundary_unresolved')
            for identity in sorted(failed)])
    source=json.loads((Path(proposal)/'crease/source.private.json').read_text('utf-8'))
    verify_source(source,'inference')
    if source['source_RGB_sha256']!=pixels(rgb):
        raise ValueError('local_axis_source_binding')
    body=read_body(source);tip=read_mask(source['tip_path'],source['tip_sha256'],native_shape(source))
    contexts=restore_edges(restore_contexts(candidate_contexts(estimate(body,tip,preserve_candidates=True),body),body),body)
    if not failed <= {c['candidate_id'] for c in contexts}:
        raise ValueError('local_axis_owner_binding')
    return recover(rgb,mask,boundary,contexts,failed)


def transport(rgb, returned, labels, applied, report, source_sha, request_id, elapsed_ms):
    """Verify exact per-region permissions before emitting the existing wire contract."""
    if (rgb.dtype != np.uint8 or returned.dtype != np.uint8 or rgb.shape != returned.shape
            or labels.dtype != np.uint16 or labels.shape != rgb.shape[:2]
            or applied.dtype != np.bool_ or applied.shape != labels.shape):
        raise ValueError('automatic_transport_arrays')
    changed=np.any(returned!=rgb,axis=2)
    if np.any(changed & ~applied) or np.any(applied & (labels==0)):
        raise ValueError('automatic_transport_preservation')
    refused=(labels>0)&~applied
    rows=[];transformed=0;ids={int(i) for i in np.unique(labels) if i}
    if len(report['regions'])!=len(ids) or {r['region_id'] for r in report['regions']}!=ids:
        raise ValueError('automatic_transport_regions')
    for r in report['regions']:
        target=labels==r['region_id'];yy,xx=np.where(target)
        accepted=bool(applied[target].all())
        if applied[target].any()!=accepted or (changed[target].any() and not accepted):
            raise ValueError('automatic_transport_atomic_region')
        if accepted and not changed[target].any():
            raise ValueError('automatic_transport_no_change')
        if accepted!=(r['status']=='synthetic_applied_unverified'):
            raise ValueError('automatic_transport_status')
        transformed+=int(accepted)
        h,w=labels.shape
        if accepted and r['reason_code'] not in ('TRANSFORMED', PRECAUTIONARY_REASON):
            raise ValueError('automatic_transport_selection_reason')
        rows.append(dict(region_id=r['region_id'],status='transformed' if accepted else 'rejected',
            reason_code=r['reason_code'],mask_pixels=int(target.sum()),
            changed_RGB_pixels=int(changed[target].sum()),permission_boolean_sha256=pixels(target),
            x=int(xx.min())/w,y=int(yy.min())/h,width=int(xx.max()+1-xx.min())/w,height=int(yy.max()+1-yy.min())/h,
            bounds_are_not_filled_permission=True))
    content=png(returned)
    verify_wire_png(content,returned,'RGB',2,1)
    if len(content)>MAX_RETURNED_PNG_BYTES:
        raise ValueError('automatic_output_PNG_byte_limit')
    count=len(rows)
    result=ValidatedExperimentalPhotoResult(ENGINE,'success' if transformed and transformed==count else
        'partial_success' if transformed else 'rejected',source_sha,pixels(rgb),pixels(returned),
        rgb.shape[1],rgb.shape[0],1,count,transformed,count-transformed,int(changed.sum()),
        encoded_mask(applied,1),encoded_mask(refused,1),tuple(rows),content)
    return result.response(request_id,elapsed_ms)


def run(source, output, *, photo_model, consumed_registry, request_id, development_replay=False,
        automatic_policy='surface_v26',execution_context=None):
    from export_photo_permissions_v1 import _request, ArtifactGuard
    from photo_new_input_v23 import propose
    from protection_runtime_sources_v1 import capture_runtime_sources, assert_runtime_sources_unchanged
    from fingerprint_input_router import route_input
    from photo_experimental_transport_v1 import require_request_id
    import pad_refinement_tiles_v3 as tiles
    require_request_id(request_id)
    if automatic_policy not in AUTOMATIC_POLICIES:
        raise ValueError('unsupported_automatic_selection_policy')
    if type(development_replay) is not bool or photo_model is None:
        raise ValueError('automatic_model_and_explicit_replay_required')
    output=Path(output)
    if output.exists() or output.is_symlink():
        raise FileExistsError('fresh_automatic_output_required')
    rgb,source_sha=_request(source)
    route=route_input(rgb)
    registry,_=tiles.json_snapshot(consumed_registry);tiles.validate_registry(registry)
    snapshot=capture_runtime_sources();started=time.perf_counter()
    guard=ArtifactGuard(output)
    for path in (Path(source),Path(consumed_registry),Path(photo_model)/'final_config.private.json',
                 Path(photo_model)/'final_context_whole_pad.pt'):
        guard.pin(path,external=True)
    output.mkdir(parents=True,exist_ok=False)
    (output/'INCOMPLETE.txt').write_text('Automatic processing not completed.',encoding='utf-8')
    if route['input_type']!='PHOTO':
        # An ambiguous/non-photo input is a non-application outcome, not a
        # processor crash or evidence that the image contains no fingerprints.
        labels=np.zeros(rgb.shape[:2],np.uint16);applied=np.zeros(rgb.shape[:2],bool)
        report=dict(regions=[],input_route=route,reason='input_route_requires_review',
                    absence_inferred=False,human_reviewed=False,privacy_validated=False)
        value=transport(rgb,rgb,labels,applied,report,source_sha,request_id,int((time.perf_counter()-started)*1000))
        guard.unchanged();assert_runtime_sources_unchanged(snapshot)
        Image.fromarray(rgb).save(output/'returned.png')
        (output/'result.private.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        target=output/'result.transport.json'
        target.write_text(json.dumps(value,separators=(',',':')),encoding='utf-8')
        (output/'INCOMPLETE.txt').unlink()
        return target
    proposal=output/'proposal';proposal.mkdir()
    propose(source,photo_model,consumed_registry,proposal,
            allow_development_replay=development_replay,minimal_artifacts=True,partial_observed_pose=True,
            **(dict(execution_context=execution_context) if execution_context is not None else {}))
    binding,_=guard.json(proposal/'proposal.private.json')
    for name in ('proposal.png','boundary_refined_mask.png'):
        guard.pin(proposal/name)
    with Image.open(proposal/'proposal.png') as im: mask=np.asarray(im)>0
    with Image.open(proposal/'boundary_refined_mask.png') as im: boundary=np.asarray(im)>0
    if (binding['source_sha256']!=source_sha or binding['candidate_selection']['proposal_pixel_sha256']!=pixels(mask)
            or mask.shape!=rgb.shape[:2]):
        raise ValueError('automatic_proposal_binding')
    mask,boundary,boundary_report=recover_proposal(rgb,mask,boundary,proposal)
    Image.fromarray(mask.astype(np.uint8)*255).save(output/'candidate_mask.png')
    surface_permission=np.zeros(rgb.shape[:2],bool)
    if binding.get('partial_pose') is not None:
        from photo_partial_pose_v25 import partition_candidates
        guard.pin(proposal/'pose_owners.png')
        with Image.open(proposal/'pose_owners.png') as im: owners=np.array(im)
        if pixels(owners)!=binding['partial_pose']['pixel_sha256']:
            raise ValueError('automatic_pose_owner_binding')
        labels,count=partition_candidates(mask,owners,binding['partial_pose']['selected_labels'],maximum=MAX_CANDIDATES)
        # Only already hash-bound, model-supported observed digit ownership
        # can authorize a surface replacement. Estimator-only and unselected
        # suggestions never acquire this permission from their rectangle.
        surface_permission=boundary&np.isin(owners,binding['partial_pose']['selected_labels'])
    else:
        labels,count=ndimage.label(mask,np.ones((3,3),np.uint8))
    if count>MAX_CANDIDATES:
        raise ValueError('automatic_candidate_limit')
    labels=labels.astype(np.uint16)
    returned,applied,report=apply_candidates(rgb,labels,boundary,
        surface_permission=surface_permission if automatic_policy=='surface_v26' else None,
        **(dict(fit_pool=execution_context.fit_pool) if execution_context is not None else {}))
    report['automatic_policy']=automatic_policy
    Image.fromarray(surface_permission.astype(np.uint8)*255).save(output/'surface_permission.png')
    report['boundary_recovery']=boundary_report
    value=transport(rgb,returned,labels,applied,report,source_sha,request_id,int((time.perf_counter()-started)*1000))
    Image.fromarray(returned).save(output/'returned.png')
    Image.fromarray(applied.astype(np.uint8)*255).save(output/'applied_mask.png')
    guard.unchanged()
    report['runtime_sources']=assert_runtime_sources_unchanged(snapshot)
    (output/'result.private.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    target=output/'result.transport.json'
    target.write_text(json.dumps(value,separators=(',',':'),allow_nan=False),encoding='utf-8')
    guard.unchanged();assert_runtime_sources_unchanged(snapshot)
    (output/'INCOMPLETE.txt').unlink()
    return target
