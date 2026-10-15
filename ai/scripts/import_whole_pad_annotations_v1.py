"""Verify and import reviewed whole-pad exports without changing private inputs."""
import argparse
import hashlib
import io
import json
import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path,PurePosixPath

import numpy as np
from PIL import Image,ImageDraw,ImageOps
from photo_pad_annotation_v1 import VERSION,POLICY,LABELS,inverse_mask,validate_points
from pad_refinement_data_contract_v2 import validate_source_id,native_shape

IMPORT_VERSION='reviewed_whole_pad_import_v1'
MAX_MEMBER=128*1024**2
MAX_TOTAL=2*1024**3


def sha(data):return hashlib.sha256(data).hexdigest()


def read_member(z,name,limit=MAX_MEMBER):
    info=z.getinfo(name)
    if info.file_size>limit:raise ValueError('annotation_member_resource_limit')
    with z.open(info) as stream:data=stream.read(limit+1)
    if len(data)>limit:raise ValueError('annotation_member_resource_limit')
    return data


def snapshot(path,expected_sha,target):
    path=Path(path)
    if not re.fullmatch('[0-9a-f]{64}',expected_sha):raise ValueError('archive_SHA256_required')
    if path.is_symlink() or not path.is_file() or path.stat().st_size>MAX_TOTAL:raise ValueError('annotation_archive_resource_limit')
    h=hashlib.sha256();total=0
    with path.open('rb') as stream,Path(target).open('xb') as output:
        for block in iter(lambda:stream.read(1024**2),b''):
            total+=len(block)
            if total>MAX_TOTAL:raise ValueError('annotation_archive_resource_limit')
            h.update(block);output.write(block)
    if h.hexdigest()!=expected_sha:raise ValueError('annotation_archive_hash_mismatch')


def verify_snapshot(path,expected_sha):
    with zipfile.ZipFile(path) as z:
        names=z.namelist();members=z.infolist()
        if len(names)>642 or len(set(n.casefold() for n in names))!=len(names):raise ValueError('annotation_archive_members_contract')
        if sum(m.file_size for m in members)>MAX_TOTAL:raise ValueError('annotation_archive_resource_limit')
        for m in members:
            p=PurePosixPath(m.filename)
            if (m.is_dir() or p.is_absolute() or '\\' in m.filename or ':' in m.filename or
                    any(x in ['.','..',''] for x in m.filename.split('/')) or
                    (m.external_attr>>16)&0o170000==0o120000 or m.flag_bits&1 or m.file_size>MAX_MEMBER or
                    m.compress_type not in [zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED]):
                raise ValueError('annotation_archive_member_contract')
        hash_data=read_member(z,'files.sha256.json',1024**2);hashes=json.loads(hash_data)
        if not isinstance(hashes,dict) or set(hashes)!=set(names)-{'files.sha256.json'}:raise ValueError('annotation_member_hash_roster_mismatch')
        for name,expected in hashes.items():
            if not isinstance(expected,str) or sha(read_member(z,name))!=expected:raise ValueError('annotation_member_hash_mismatch')
        roster=json.loads(read_member(z,'annotation_roster.private.json',1024**2))
        if (roster.get('version')!=VERSION or roster.get('data_role')!='diagnostic_development' or
                roster.get('independent_final_test') is not False or roster.get('training_performed') is not False or
                not isinstance(roster.get('sources'),list) or not 1<=len(roster['sources'])<=128):
            raise ValueError('reviewed_human_development_roster_required')
        expected_names={'files.sha256.json','annotation_roster.private.json'};rows=[];ids=set();raws=set();pixels=set()
        for row in roster['sources']:
            sid=row['source_id'];validate_source_id(sid)
            if sid.casefold() in ids:raise ValueError('duplicate_annotation_source')
            ids.add(sid.casefold());folder=f'ground_truth_training/{sid}'
            if row.get('GT_folder')!=folder or row.get('human_annotation') is not True:raise ValueError('human_GT_roster_binding')
            source_name=row['source'];source_parts=PurePosixPath(source_name).parts
            if len(source_parts)!=3 or source_parts[:2]!=('images',sid):raise ValueError('annotation_image_path_binding')
            expected_names.add(source_name)
            for filename in ['source.json','ground_truth_mask.png','preview.png','annotation.json']:expected_names.add(folder+'/'+filename)
            raw=read_member(z,source_name);meta=json.loads(read_member(z,folder+'/source.json',1024**2))
            record=json.loads(read_member(z,folder+'/annotation.json',2*1024**2))
            source_sha=sha(raw);mask_raw=read_member(z,folder+'/ground_truth_mask.png')
            status=meta.get('annotation_status')
            if (meta.get('human_annotation') is not True or meta.get('human_review_attestation') is not True or
                    meta.get('annotation_type')!='human_reviewed_fingerprint_pad' or meta.get('mask_semantics')!=POLICY or
                    meta.get('annotation_tool')!=VERSION or meta.get('coordinate_system')!='encoded_original_pixels' or
                    meta.get('polygon_coordinate_system')!='exif_transposed_display_pixels' or
                    meta.get('source_sha256')!=source_sha or meta.get('mask_sha256')!=sha(mask_raw) or
                    meta.get('source_filename')!=source_parts[-1] or status not in LABELS or
                    row.get('annotation_status')!=status or meta.get('data_role')!='diagnostic_development' or
                    meta.get('independent_final_test') is not False):raise ValueError('reviewed_annotation_metadata_contract')
            if (record.get('version')!=VERSION or record.get('policy')!=POLICY or record.get('source_id')!=sid or
                    record.get('source_sha256')!=source_sha or record.get('human_annotation') is not True or
                    record.get('explicit_review_attestation') is not True or record.get('status')!=status or
                    record.get('label')!=status or record.get('pending_points')!=[]):raise ValueError('reviewed_annotation_record_contract')
            for field in ['acquisition_group','group_provenance']:
                values=[item.get(field) or 'unknown' for item in [row,meta,record]]
                if len(set(values))!=1:raise ValueError('annotation_group_binding_mismatch')
            if any(item.get(flag) is not False for item in [meta,record] for flag in ['acquisition_group_verified','person_independence_verified']):
                raise ValueError('annotation_independence_not_verified')
            if record.get('notes')!=meta.get('notes'):raise ValueError('annotation_review_notes_mismatch')
            assets=record.get('review_assets',{})
            if set(assets)!={'source.json','ground_truth_mask.png','preview.png'} or any(assets[n]!=hashes[folder+'/'+n] for n in assets):
                raise ValueError('reviewed_annotation_assets_contract')
            with Image.open(io.BytesIO(raw)) as image:
                orientation=image.getexif().get(274,1)
                native_shape(dict(height=image.height,width=image.width,coordinate_system='encoded_original_pixels'))
                if (image.mode not in ['RGB','L'] or type(orientation) is not int or orientation not in range(1,9) or
                        (meta.get('image_height'),meta.get('image_width'),meta.get('exif_orientation'))!=(image.height,image.width,orientation)):
                    raise ValueError('annotation_image_geometry_contract')
                rgb=np.asarray(image.convert('RGB')).copy();upright=ImageOps.exif_transpose(image).convert('RGB')
                encoded_sha=sha(rgb.tobytes());upright_sha=sha(np.asarray(upright).tobytes())
                size=upright.size
            if meta.get('encoded_RGB_sha256')!=encoded_sha or meta.get('upright_RGB_sha256')!=upright_sha:raise ValueError('annotation_decoded_hash_mismatch')
            if source_sha in raws or pixels.intersection([encoded_sha,upright_sha]):raise ValueError('duplicate_annotation_pixels')
            raws.add(source_sha);pixels.update([encoded_sha,upright_sha])
            with Image.open(io.BytesIO(mask_raw)) as image:
                if image.mode!='L' or image.format!='PNG' or image.size!=rgb.shape[1::-1]:raise ValueError('annotation_mask_geometry_contract')
                mask=np.asarray(image).copy()
            if not np.isin(mask,[0,255]).all():raise ValueError('annotation_mask_nonbinary')
            ops=record.get('ops')
            if not isinstance(ops,list) or len(ops)>256:raise ValueError('annotation_polygon_resource_limit')
            display=Image.new('L',size);draw=ImageDraw.Draw(display);points=0
            for op in ops:
                if not isinstance(op,dict) or set(op)!={'mode','points'} or op['mode'] not in ['add','erase']:raise ValueError('annotation_polygon_contract')
                validate_points(op['points'],*size,True);points+=len(op['points'])
                if points>20000:raise ValueError('annotation_polygon_resource_limit')
                draw.polygon([tuple(p) for p in op['points']],fill=255 if op['mode']=='add' else 0)
            if not np.array_equal(np.asarray(inverse_mask(display,orientation)),mask):raise ValueError('reviewed_polygon_mask_mismatch')
            if (status=='valid_positive' and not mask.any()) or (status=='non_target' and mask.any()):raise ValueError('annotation_label_mask_mismatch')
            if status=='ambiguous_unusable' and not str(meta.get('notes','')).strip():raise ValueError('annotation_ambiguous_reason_required')
            rows.append(dict(source_id=sid,source=source_name,GT_folder=folder,source_sha256=source_sha,
                GT_metadata_sha256=hashes[folder+'/source.json'],GT_mask_sha256=sha(mask_raw),
                encoded_RGB_sha256=encoded_sha,upright_RGB_sha256=upright_sha,width=rgb.shape[1],height=rgb.shape[0],
                source_exif_orientation=orientation,coordinate_system='encoded_original_pixels',annotation_status=status,
                mask_pixels=int((mask==255).sum()),polygon_count=sum(op['mode']=='add' for op in ops),
                acquisition_group=row.get('acquisition_group','unknown'),group_provenance=row.get('group_provenance','unknown'),
                person_independence_verified=False,independent_final_test=False))
        if set(names)!=expected_names:raise ValueError('unexpected_annotation_archive_members')
    return dict(version=IMPORT_VERSION,archive_sha256=expected_sha,data_role='diagnostic_development',
        coordinate_system='encoded_original_pixels',policy=POLICY,source_count=len(rows),sources=rows,
        human_reviewed=True,polygon_mask_exact=True,member_sha256=hashes,
        hash_roster_sha256=sha(hash_data),
        private=True,training_performed=False,independent_final_test=False)


def verify_archive(path,expected_sha):
    with tempfile.TemporaryDirectory(prefix='blurfing-verified-import-') as folder:
        frozen=Path(folder)/'input.zip';snapshot(path,expected_sha,frozen)
        return verify_snapshot(frozen,expected_sha)


def import_archive(path,expected_sha,output):
    output=Path(output)
    if output.exists() or output.is_symlink():raise FileExistsError('fresh_import_output_required')
    output.parent.mkdir(parents=True,exist_ok=True);parent=output.parent.resolve()
    temporary=Path(tempfile.mkdtemp(prefix='.whole-pad-import-',dir=parent))
    try:
        frozen=temporary/'.archive.input.zip';snapshot(path,expected_sha,frozen);report=verify_snapshot(frozen,expected_sha)
        with zipfile.ZipFile(frozen) as z:
            # Only the previously verified allowlist supplies output paths.
            # Reopening a changed archive must never introduce another path.
            for name,expected in report['member_sha256'].items():
                data=read_member(z,name)
                if sha(data)!=expected:raise ValueError('annotation_archive_changed_during_import')
                target=temporary.joinpath(*PurePosixPath(name).parts);target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes(data)
            (temporary/'files.sha256.json').write_bytes(read_member(z,'files.sha256.json',1024**2))
        report_after=verify_snapshot(frozen,expected_sha)
        if report_after!=report:raise ValueError('annotation_archive_changed_during_import')
        frozen.unlink()
        for row in report['sources']:
            row['source_path']=str((output/row['source']).resolve());row['GT_folder']=str((output/row['GT_folder']).resolve())
        (temporary/'import.private.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        os.rename(temporary,output)
    finally:
        if temporary.exists():
            if temporary.is_symlink() or temporary.resolve().parent!=parent or not temporary.name.startswith('.whole-pad-import-'):
                raise RuntimeError('import_cleanup_containment_failed')
            shutil.rmtree(temporary)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--zip',type=Path,required=True)
    parser.add_argument('--sha256',required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    report=import_archive(args.zip,args.sha256,args.output)
    print(json.dumps({k:v for k,v in report.items() if k not in ['sources','member_sha256']}))
