"""Development training contract for legacy pads plus reviewed whole-pad targets.

V3 input geometry, architecture, loss and thresholds are preserved. New photos
are one conservative archive cluster, not independently verified acquisitions.
"""
import argparse
import json
import hashlib
from pathlib import Path
import numpy as np
from PIL import Image
from pad_refinement_tiles_v3 import (prepare as prepare_inputs,check_tiles,input_source,
    source_record,hash_json,json_snapshot,unchanged,COORDINATES)
from pad_refinement_data_contract_v2 import (checked_bytes,digest,read_source_rgb,verify_source,
    read_gt,load_crop)
from pad_refinement_experiment_plan_v2 import group_splits
from prepare_pad_refinement_data import letterbox

VERSION='whole_pad_target_dataset_v4_development'
WHOLE='whole_visible_palmar_distal_pad_v1'
LEGACY='legacy_visible_pad_boundary_unspecified'


def group_plan(sources,registry):
    identities=[dict(source_id=s['source_id'],**s['canonical_identity']) for s in sources]
    return group_splits(identities,{s['source_id']:s['acquisition_group'] for s in sources},[r['source_sha256'] for r in registry])


def evidence_sources(evidence):
    """Proof of grouping is fixed independently of masks, folds and scores."""
    legacy=json.loads(checked_bytes(evidence['legacy_manifest_path'],evidence['legacy_manifest_sha256']))
    if legacy.get('purpose')!='training' or legacy.get('version')!='pad_refinement_tiles_data_v3':raise ValueError('legacy_training_evidence_required')
    imported=json.loads(checked_bytes(evidence['import_report_path'],evidence['import_report_sha256']))
    if (imported.get('version')!='reviewed_whole_pad_import_v1' or imported.get('human_reviewed') is not True or
            imported.get('polygon_mask_exact') is not True or imported.get('independent_final_test') is not False or
            imported.get('policy')!=WHOLE):raise ValueError('reviewed_whole_pad_import_evidence_required')
    group='conservative-bundle-'+imported['archive_sha256'][:16]
    rows={}
    for source in legacy['sources']:
        sid=source['source_id']
        if sid in rows or source.get('group_provenance')!='acquisition_folder_and_filename_date':raise ValueError('legacy_group_evidence')
        rows[sid]=dict(source_sha256=source['source_sha256'],GT_metadata_sha256=source['GT_metadata_sha256'],GT_mask_sha256=source['GT_mask_sha256'],
            acquisition_group=source['acquisition_group'],group_provenance=source['group_provenance'],GT_policy=LEGACY)
    for source in imported['sources']:
        sid=source['source_id']
        if sid in rows or source['annotation_status']!='valid_positive':raise ValueError('positive_reviewed_sources_required')
        rows[sid]=dict(source_sha256=source['source_sha256'],GT_metadata_sha256=source['GT_metadata_sha256'],GT_mask_sha256=source['GT_mask_sha256'],
            acquisition_group=group,group_provenance='conservative_reviewed_archive_cluster',GT_policy=WHOLE)
    return rows


def check(root,manifest):
    if (manifest.get('version')!=VERSION or manifest.get('purpose')!='training' or manifest.get('GT_present') is not True or
            manifest.get('independent_final_test') is not False or manifest.get('person_independence_verified') is not False or
            manifest.get('new_acquisition_groups_verified') is not False):raise ValueError('whole_pad_training_header_contract')
    input_path=Path(root)/'manifest.input.private.json';view,view_sha=json_snapshot(input_path)
    if view_sha!=manifest.get('input_manifest_sha256'):raise ValueError('input_manifest_binding_mismatch')
    check_tiles(root,view,'inference');by_id={s['source_id']:s for s in manifest['sources']}
    expected=evidence_sources(manifest['group_evidence'])
    if set(by_id)!=set(expected) or len(by_id)!=len(manifest['sources']):raise ValueError('whole_pad_source_roster_mismatch')
    if manifest['consumed_registry']!=view['consumed_registry']:raise ValueError('consumed_registry_binding_mismatch')
    if [input_source(s) for s in manifest['sources']]!=view['sources']:raise ValueError('GT_free_source_view_mismatch')
    gt_cache={}
    for source in manifest['sources']:
        sid=source['source_id'];proof=expected[sid]
        if any(source.get(k)!=v for k,v in proof.items()):raise ValueError('whole_pad_label_or_group_evidence_mismatch')
        verify_source(source,'training')
        meta=json.loads(checked_bytes(Path(source['GT_folder'])/'source.json',source['GT_metadata_sha256']))
        if proof['GT_policy']==WHOLE and (meta.get('mask_semantics')!=WHOLE or meta.get('human_review_attestation') is not True):
            raise ValueError('whole_pad_explicit_review_policy_required')
        gt_cache[sid]=read_gt(source)
    plan=group_plan(manifest['sources'],manifest['consumed_registry'])
    if plan!=manifest['group_split_plan'] or plan!=view['group_split_plan']:raise ValueError('whole_pad_group_split_mismatch')
    if len(manifest['crops'])!=len(view['crops']):raise ValueError('whole_pad_crop_count_mismatch')
    for record,original in zip(manifest['crops'],view['crops']):
        if {k:v for k,v in record.items() if k not in ['path','file_sha256','input_path','input_file_sha256']}!={k:v for k,v in original.items() if k not in ['path','file_sha256']}:
            raise ValueError('training_geometry_changed_from_input')
        if record['input_path']!=original['path'] or record['input_file_sha256']!=original['file_sha256']:raise ValueError('tile_input_binding_mismatch')
        source=by_id[record['source_id']];arrays=load_crop(root,record,source,'training');base=load_crop(root,original,input_source(source),'inference')
        if any(not np.array_equal(arrays[k],base[k]) for k in ['rgb','coarse']):raise ValueError('training_input_content_changed')
        a,b,c,d=record['bbox'];gt=gt_cache[source['source_id']]
        _,_,label,geometry=letterbox(np.zeros((d-b,c-a,3),np.uint8),np.zeros((d-b,c-a),bool),gt[b:d,a:c])
        if geometry!=record['geometry'] or not np.array_equal(arrays['label'],label):raise ValueError('native_whole_pad_tile_label_mismatch')
    return view


def prepare(inputs,registry,evidence,output):
    output=Path(output);proof=evidence_sources(evidence)
    if {r['source_id'] for r in inputs}!=set(proof) or len(inputs)!=len(proof):raise ValueError('complete_evidence_roster_required')
    native=[];GT={}
    for row in inputs:
        sid=row['source_id'];target=dict(row);GT[sid]=target.pop('GT_folder')
        if any(target.get(k)!=proof[sid][k] for k in ['source_sha256','acquisition_group','group_provenance']):raise ValueError('input_group_evidence_mismatch')
        native.append(target)
    # This entire GT-free manifest and crop plan is published before GT decode.
    view=prepare_inputs(native,registry,output,'inference');sources=[];crops=[]
    for original in view['sources']:
        sid=original['source_id'];folder=Path(GT[sid]);source=dict(original,GT_folder=str(folder.resolve()),
            GT_metadata_sha256=digest(folder/'source.json'),GT_mask_sha256=digest(folder/'ground_truth_mask.png'),GT_policy=proof[sid]['GT_policy'])
        if any(source.get(k)!=v for k,v in proof[sid].items()):raise ValueError('label_evidence_changed')
        verify_source(source,'training');gt=read_gt(source);sources.append(source)
        for original_record in [r for r in view['crops'] if r['source_id']==sid]:
            arrays=load_crop(output,original_record,original,'inference');a,b,c,d=original_record['bbox']
            _,_,label,g=letterbox(np.zeros((d-b,c-a,3),np.uint8),np.zeros((d-b,c-a),bool),gt[b:d,a:c])
            if g!=original_record['geometry']:raise ValueError('training_geometry_changed_from_input')
            name=original_record['path'].replace('_input.npz','_whole_train.npz')
            np.savez_compressed(output/name,rgb=arrays['rgb'],coarse=arrays['coarse'],label=label)
            crops.append(dict(original_record,path=name,file_sha256=digest(output/name),input_path=original_record['path'],input_file_sha256=original_record['file_sha256']))
    # Preserve the original input crop ordering, independent of source order.
    crops.sort(key=lambda r:next(i for i,v in enumerate(view['crops']) if v['path']==r['input_path']))
    manifest=dict(version=VERSION,purpose='training',GT_present=True,sources=sources,crops=crops,
        input_manifest_sha256=digest(output/'manifest.input.private.json'),group_evidence=evidence,
        group_split_plan=group_plan(sources,registry),consumed_registry=registry,
        independent_final_test=False,person_independence_verified=False,new_acquisition_groups_verified=False)
    check(output,manifest)
    (output/'manifest.whole.private.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8');return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['inputs','consumed-registry','evidence','output']:parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
    result=prepare(read(args.inputs),read(args.consumed_registry),read(args.evidence),args.output)
    print(json.dumps(dict(sources=len(result['sources']),tiles=len(result['crops']),version=VERSION)))
