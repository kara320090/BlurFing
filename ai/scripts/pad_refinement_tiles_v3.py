"""Hash-bound experimental tile datasets with a separate GT-free input view."""
import argparse
import hashlib
import io
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps
from finger_body_distal_estimator import estimate
from prepare_pad_refinement_data import letterbox
from pad_refinement_data_contract_v2 import (check_assets, checked_bytes, digest,
    native_shape, read_source_rgb, source_record, verify_source, read_body,
    read_mask, read_gt, load_crop, validate_source_id, COORDINATES)
from pad_refinement_experiment_plan_v2 import plan_crops, POLICY, POLICY_SHA256, group_splits

VERSION = 'pad_refinement_tiles_data_v3'
CROP_POLICY = 'native_body_tiles_v3_experimental'
MERGE = 'mean_of_native_restored_probabilities_v1'


def hash_json(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',',':')).encode()).hexdigest()


def json_snapshot(path):
    data=Path(path).read_bytes()
    return json.loads(data.decode('utf-8-sig')),hashlib.sha256(data).hexdigest()


def unchanged(path,expected):
    if digest(path)!=expected:raise ValueError('frozen_run_inputs_or_code_changed')


def image_identity(path):
    """RGBA is allowed only for exclusion identities, with historical RGB decode."""
    sha = digest(path)
    with Image.open(io.BytesIO(checked_bytes(path,sha))) as image:
        native_shape(dict(height=image.height,width=image.width,coordinate_system=COORDINATES))
        if image.mode not in ['RGB','RGBA','L']:raise ValueError('identity_image_mode')
        encoded = np.asarray(image.convert('RGB')).copy()
        upright = np.asarray(ImageOps.exif_transpose(image).convert('RGB')).copy()
    return dict(source_sha256=sha,encoded_RGB_sha256=hashlib.sha256(encoded.tobytes()).hexdigest(),
                upright_RGB_sha256=hashlib.sha256(upright.tobytes()).hexdigest())


def validate_registry(registry):
    if not isinstance(registry,list) or not registry:raise ValueError('consumed_registry_required')
    required={'source_sha256','encoded_RGB_sha256','upright_RGB_sha256','role'}
    for row in registry:
        if not isinstance(row,dict) or set(row)!=required or row['role'] not in ['consumed_GT7','consumed_holdout']:
            raise ValueError('consumed_registry_contract')
        for key in required-{'role'}:
            value=row[key]
            if not isinstance(value,str) or len(value)!=64 or any(c not in '0123456789abcdef' for c in value):
                raise ValueError('consumed_registry_hash_contract')
    if len({r['source_sha256'] for r in registry if r['role']=='consumed_GT7'})!=7:
        raise ValueError('seven_verified_GT7_identities_required')
    holdouts={tuple(sorted([r['encoded_RGB_sha256'],r['upright_RGB_sha256']]))
              for r in registry if r['role']=='consumed_holdout'}
    if len(holdouts)<8:raise ValueError('eight_consumed_holdout_appearances_required')


def exclude_consumed(identity,registry):
    validate_registry(registry)
    for row in registry:
        if identity['source_sha256']==row['source_sha256'] or (
                {identity['encoded_RGB_sha256'],identity['upright_RGB_sha256']} &
                {row['encoded_RGB_sha256'],row['upright_RGB_sha256']}):
            raise ValueError('consumed_source_or_decoded_pixels_forbidden')


def input_source(source):
    return {k:v for k,v in source.items() if not k.startswith('GT')}


def input_view(manifest):
    if manifest['purpose']=='inference':return manifest
    crops=[]
    for record in manifest['crops']:
        row={k:v for k,v in record.items() if not k.startswith('input_')}
        row.update(path=record['input_path'],file_sha256=record['input_file_sha256'])
        crops.append(row)
    return manifest | dict(purpose='inference',GT_present=False,
                           sources=[input_source(s) for s in manifest['sources']],crops=crops)


def split_plan(identities,groups,registry,purpose):
    if purpose=='training' or (len(set(g.casefold() for g in groups.values()))>=2 and
                                all(g.casefold()!='unknown' for g in groups.values())):
        return group_splits(identities,groups,[r['source_sha256'] for r in registry])
    return dict(version='inference_no_training_split',source_count=len(identities),
                independent_final_test=False,training_performed=False)


def check_header(manifest,purpose):
    if (not isinstance(manifest,dict) or manifest.get('version')!=VERSION or manifest.get('purpose')!=purpose or
            purpose not in ['training','inference'] or manifest.get('GT_present') is not (purpose=='training') or
            manifest.get('coordinate_system')!=COORDINATES or manifest.get('input_size')!=256 or
            manifest.get('context_padding')!=0. or manifest.get('crop_policy')!=CROP_POLICY or
            manifest.get('merge_policy')!=MERGE or manifest.get('tile_policy')!=dict(POLICY) or
            hashlib.sha256(json.dumps(manifest.get('tile_policy'),sort_keys=True).encode()).hexdigest()!=POLICY_SHA256 or
            manifest.get('tile_policy_sha256')!=POLICY_SHA256 or
            hash_json(manifest.get('consumed_registry'))!=manifest.get('consumed_registry_sha256') or
            manifest.get('independent_final_test') is not False):
        raise ValueError('tiles_V3_manifest_contract')
    validate_registry(manifest['consumed_registry'])


def check_input_source(root,source,records,registry):
    """Snapshot all model inputs for one source before its first forward."""
    if any(k.startswith('GT') for k in source):raise ValueError('GT_fields_forbidden_in_inference')
    verify_source(source,'inference');identity=image_identity(source['source_path'])
    if identity!=source.get('canonical_identity'):raise ValueError('canonical_identity_mismatch')
    exclude_consumed(identity,registry)
    body=read_body(source);coarse=read_mask(source['coarse_path'],source['coarse_sha256'],native_shape(source))
    plan=plan_crops({k:source[k] for k in ['height','width','coordinate_system','source_sha256']},body,coarse)
    if plan!=source.get('tile_plan') or hash_json(plan)!=source.get('tile_plan_sha256') or plan['status']!='planned':
        raise ValueError('tile_plan_identity_or_coverage_contract')
    if [r['bbox'] for r in records]!=plan['boxes']:raise ValueError('complete_ordered_tile_plan_required')
    if any(k.startswith('input_') for r in records for k in r):raise ValueError('training_links_forbidden_in_inference')
    arrays=[load_crop(root,r,source,'inference') for r in records]
    rgb=read_source_rgb(source['source_path'],source['source_sha256'])
    for record,actual in zip(records,arrays):
        a,b,c,d=record['bbox'];x,mask,_,g=letterbox(rgb[b:d,a:c],coarse[b:d,a:c],np.zeros((d-b,c-a),bool))
        if g!=record['geometry'] or not np.array_equal(actual['rgb'],x) or not np.array_equal(actual['coarse'],mask):
            raise ValueError('native_source_crop_content_mismatch')
    return body,arrays


def check_tiles(root,manifest,purpose):
    check_header(manifest,purpose);registry=manifest['consumed_registry']
    if purpose=='training':check_tiles(root,input_view(manifest),'inference')
    sources=check_assets(root,manifest,purpose)
    identities=[];groups={}
    for sid,source in sources.items():
        identity=image_identity(source['source_path'])
        if identity!=source.get('canonical_identity'):raise ValueError('canonical_identity_mismatch')
        exclude_consumed(identity,registry)
        body=read_body(source);coarse=read_mask(source['coarse_path'],source['coarse_sha256'],native_shape(source))
        expected=plan_crops({k:source[k] for k in ['height','width','coordinate_system','source_sha256']},body,coarse)
        if (expected['status']!='planned' or expected!=source.get('tile_plan') or
                hash_json(expected)!=source.get('tile_plan_sha256')):
            raise ValueError('tile_plan_identity_or_coverage_contract')
        records=[r for r in manifest['crops'] if r['source_id']==sid]
        if [r['bbox'] for r in records]!=expected['boxes']:raise ValueError('complete_ordered_tile_plan_required')
        if purpose=='inference' and any(k.startswith('input_') for r in records for k in r):
            raise ValueError('training_links_forbidden_in_inference')
        rgb=read_source_rgb(source['source_path'],source['source_sha256'])
        gt=read_gt(source) if purpose=='training' else None
        for record in records:
            actual=load_crop(root,record,source,purpose);a,b,c,d=record['bbox']
            x,mask,label,g=letterbox(rgb[b:d,a:c],coarse[b:d,a:c],gt[b:d,a:c] if gt is not None else np.zeros((d-b,c-a),bool))
            if (g!=record['geometry'] or not np.array_equal(actual['rgb'],x) or not np.array_equal(actual['coarse'],mask) or
                    not np.array_equal(actual['label'],label)):
                raise ValueError('native_source_crop_content_mismatch')
        group=source.get('acquisition_group');validate_source_id(group)
        if purpose=='training' and (group.casefold()=='unknown' or source.get('group_provenance')!='acquisition_folder_and_filename_date'):
            raise ValueError('explicit_acquisition_provenance_required')
        groups[sid]=group
        identities.append(dict(source_id=sid,**identity))
    splits=split_plan(identities,groups,registry,purpose)
    if manifest.get('group_split_plan')!=splits:raise ValueError('group_split_plan_mismatch')
    if purpose=='training':
        for record in manifest['crops']:
            a=load_crop(root,record,sources[record['source_id']],'training')
            b=load_crop(root,dict(record,path=record['input_path'],file_sha256=record['input_file_sha256']),sources[record['source_id']],'inference')
            if not all(np.array_equal(a[k],b[k]) for k in ['rgb','coarse']):raise ValueError('training_input_view_mismatch')
    return sources


def prepare(inputs,registry,output,purpose='training'):
    validate_registry(registry)
    if purpose not in ['training','inference'] or not isinstance(inputs,list) or not inputs:
        raise ValueError('tile_preparation_inputs_required')
    expected={'source_id','source_path','source_sha256','semantics','acquisition_group','group_provenance'}
    if purpose=='training':expected.add('GT_folder')
    if any(not isinstance(r,dict) or set(r)!=expected for r in inputs):raise ValueError('explicit_inputs_contract')
    for row in inputs:validate_source_id(row['source_id'])
    if len({r['source_id'].casefold() for r in inputs})!=len(inputs):raise ValueError('duplicate_source_id')
    if output.exists():raise FileExistsError('fresh_output_required')
    sources=[];identities=[];groups={}
    # All geometry is frozen before target arrays are read. Capture GT byte
    # identities beforehand, but never pass them to source inference/planning.
    for row in inputs:
        sid=row['source_id'];rgb=read_source_rgb(row['source_path'],row['source_sha256'])
        source=source_record(row['source_path'],sid,row['semantics'],rgb,
                             row.get('GT_folder') if purpose=='training' else None)
        if source['source_sha256']!=row['source_sha256']:raise ValueError('source_changed_during_prepare')
        verify_source(input_source(source),'inference')
        identity=image_identity(source['source_path']);exclude_consumed(identity,registry)
        body=read_body(source);tip=read_mask(source['tip_path'],source['tip_sha256'],body.shape)
        coarse=estimate(body,tip)['mask'];plan=plan_crops({k:source[k] for k in ['height','width','coordinate_system','source_sha256']},body,coarse)
        if plan['status']!='planned':raise ValueError('whole_source_plan_rejected:'+plan.get('reason','empty'))
        group=row['acquisition_group'];validate_source_id(group)
        if purpose=='training' and (group.casefold()=='unknown' or row['group_provenance']!='acquisition_folder_and_filename_date'):
            raise ValueError('explicit_acquisition_provenance_required')
        source.update(canonical_identity=identity,acquisition_group=group,group_provenance=row['group_provenance'],
                      tile_plan=plan,tile_plan_sha256=hash_json(plan),crop_count=len(plan['boxes']))
        sources.append(source);identities.append(dict(source_id=sid,**identity));groups[sid]=group
    splits=split_plan(identities,groups,registry,purpose)
    output.mkdir(parents=True,exist_ok=False);input_crops=[]
    for source in sources:
        sid=source['source_id'];verify_source(input_source(source),'inference')
        rgb=read_source_rgb(source['source_path'],source['source_sha256']);body=read_body(source)
        tip=read_mask(source['tip_path'],source['tip_sha256'],body.shape);coarse=estimate(body,tip)['mask']
        if hashlib.sha256(coarse.tobytes()).hexdigest()!=source['tile_plan']['coarse_pixel_sha256']:
            raise ValueError('coarse_changed_during_prepare')
        path=output/(sid+'_coarse.png');Image.fromarray(coarse.astype(np.uint8)*255).save(path)
        source.update(coarse_path=str(path.resolve()),coarse_sha256=digest(path))
        for i,box in enumerate(source['tile_plan']['boxes']):
            a,b,c,d=box;x,mask,zero,g=letterbox(rgb[b:d,a:c],coarse[b:d,a:c],np.zeros((d-b,c-a),bool))
            name=f'{sid}_tile_{i:03d}_input.npz';np.savez_compressed(output/name,rgb=x,coarse=mask,label=zero)
            input_crops.append(dict(source_id=sid,source_sha256=source['source_sha256'],path=name,
                                    file_sha256=digest(output/name),bbox=box,geometry=g))
    header=dict(version=VERSION,coordinate_system=COORDINATES,input_size=256,context_padding=0.,
                crop_policy=CROP_POLICY,merge_policy=MERGE,tile_policy=dict(POLICY),tile_policy_sha256=POLICY_SHA256,
                consumed_registry=registry,consumed_registry_sha256=hash_json(registry),group_split_plan=splits,
                independent_final_test=False)
    view=header | dict(purpose='inference',GT_present=False,sources=[input_source(s) for s in sources],crops=input_crops)
    check_tiles(output,view,'inference')
    (output/'manifest.input.private.json').write_text(json.dumps(view,indent=2),encoding='utf-8')
    if purpose=='inference':return view
    crops=[];by_id={s['source_id']:s for s in sources}
    for source in sources:
        verify_source(source,'training');gt=read_gt(source)
        for record in [r for r in input_crops if r['source_id']==source['source_id']]:
            arrays=load_crop(output,record,input_source(source),'inference');a,b,c,d=record['bbox']
            # Labels use exactly the already-published geometry, not GT boxes.
            _,_,label,g=letterbox(np.zeros((d-b,c-a,3),np.uint8),np.zeros((d-b,c-a),bool),gt[b:d,a:c])
            if g!=record['geometry']:raise ValueError('label_geometry_mismatch')
            name=record['path'].replace('_input.npz','_train.npz')
            np.savez_compressed(output/name,rgb=arrays['rgb'],coarse=arrays['coarse'],label=label)
            crops.append(dict(record,path=name,file_sha256=digest(output/name),input_path=record['path'],input_file_sha256=record['file_sha256']))
    manifest=header | dict(purpose='training',GT_present=True,sources=sources,crops=crops)
    check_tiles(output,manifest,'training')
    (output/'manifest.private.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    return manifest


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--inputs',type=Path,required=True)
    p.add_argument('--consumed-registry',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--purpose',choices=['training','inference'],default='training');a=p.parse_args()
    prepare(json.loads(a.inputs.read_text(encoding='utf-8-sig')),json.loads(a.consumed_registry.read_text(encoding='utf-8-sig')),a.output,a.purpose)
