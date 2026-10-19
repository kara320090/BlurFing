"""Import verified anatomical-mask registries without changing original files."""
import argparse
import io
import json
from pathlib import Path
from PIL import Image
from pad_refinement_data_contract_v2 import checked_bytes
from photo_pad_annotation_v1 import digest, write_json
from photo_visibility_annotation_v1 import Project


def prepare(training_manifest, historical_registry, output):
    output=Path(output)
    if output.exists(): raise FileExistsError('fresh_visibility_project_required')
    training=json.loads(Path(training_manifest).read_text(encoding='utf-8-sig'))
    historical=json.loads(Path(historical_registry).read_text(encoding='utf-8-sig'))
    rows=[]; decoded=set()
    for old, role in [(r,'consumed_training_development') for r in training['sources']]+[(r,'consumed_historical_GT7_forbid_training') for r in historical['rows']]:
        source=checked_bytes(old['source_path'],old['source_sha256'])
        mask=Path(old['GT_folder'])/'ground_truth_mask.png'
        metadata=Path(old['GT_folder'])/'source.json'
        meta_hash=old.get('GT_metadata_sha256') or old['annotation']['metadata_sha256']
        meta=json.loads(checked_bytes(metadata,meta_hash).decode('utf-8-sig'))
        mask_hash=old.get('GT_mask_sha256') or meta['mask_sha256']
        checked_bytes(mask,mask_hash)
        identity=old.get('canonical_identity',old)
        if identity['upright_RGB_sha256'] in decoded: raise ValueError('duplicate_upright_pixels')
        decoded.add(identity['upright_RGB_sha256'])
        with Image.open(io.BytesIO(source)) as im:
            width,height=im.size;orientation=im.getexif().get(274,1);frame_count=getattr(im,'n_frames',1)
        rows.append(dict(source_id=old['source_id'],source_path=old['source_path'],source_sha256=old['source_sha256'],
            mask_path=str(mask),mask_sha256=mask_hash,mask_metadata_sha256=meta_hash,
            encoded_RGB_sha256=identity['encoded_RGB_sha256'],upright_RGB_sha256=identity['upright_RGB_sha256'],
            width=width,height=height,exif_orientation=orientation,frame_used=0,frame_count=frame_count,split_role=role,
            acquisition_group=old.get('acquisition_group'),GT_policy=old.get('GT_policy','historical_boundary_unspecified')))
    output.mkdir(parents=True)
    roster=output/'roster.private.json'
    write_json(roster,dict(version='visibility_roster_v1',data_role='diagnostic_development',sources=rows,
        historical_holdout_consumed=True,person_independence_verified=False,
        input_registry_sha256=[digest(Path(p).read_bytes()) for p in [training_manifest,historical_registry]]))
    project=Project(roster,output/'state')
    summary=dict(sources=len(rows),component_proposals=sum(len(r['proposals']) for r in project.sources.values()),
        reviewed_visibility_images=0,labels_generated=False,roster=str(roster),source_files_modified=False)
    write_json(output/'preparation.private.json',summary)
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--training-manifest',required=True,type=Path);p.add_argument('--historical-registry',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    print(json.dumps(prepare(a.training_manifest,a.historical_registry,a.output),indent=2))
