"""GT-free inference crops from the preserved semantic/coarse frontend."""
import argparse,json,hashlib,time
from pathlib import Path
import numpy as np
from PIL import Image
from finger_body_distal_estimator import estimate
from evaluate_finger_body_distal import read_binary
from prepare_pad_refinement_data import guided_bbox,letterbox
from pad_refinement_data_contract_v2 import (VERSION,COORDINATES,source_record,digest,check_dataset,SIZE,PADDING,
    validate_source_id,read_source_rgb,verify_source,read_body,read_mask)


def prepare(inputs,semantic_root,output):
    if any(set(x)!={'sample_id','source','source_sha256'} for x in inputs):raise ValueError('source_identity_only; GT_fields_forbidden')
    for item in inputs:validate_source_id(item['sample_id'])
    if len({i['sample_id'].casefold() for i in inputs})!=len(inputs):raise ValueError('duplicate_source_id')
    output.mkdir(parents=True,exist_ok=False);sources=[];crops=[]
    for item in inputs:
        sid=item['sample_id'];source=Path(item['source']);rgb=read_source_rgb(source,item['source_sha256'])
        record=source_record(source,sid,semantic_root/sid,rgb);verify_source(record,'inference')
        if record['source_sha256']!=item['source_sha256']:raise ValueError('source_changed_during_preparation')
        body=read_body(record);tip=read_mask(record['tip_path'],record['tip_sha256'],rgb.shape[:2]);tick=time.perf_counter();result=estimate(body,tip);seconds=time.perf_counter()-tick
        for i,region in enumerate(result['regions']):
            if region.get('reject_reason') is not None:continue
            bbox=guided_bbox(region['mask']);a,b,c,d=bbox;image,mask,unused,geometry=letterbox(rgb[b:d,a:c],region['mask'][b:d,a:c],np.zeros((d-b,c-a),bool));name=f'{sid}_crop_{i:03d}.npz';np.savez_compressed(output/name,rgb=image,coarse=mask,label=unused);crops.append(dict(source_id=sid,source_sha256=item['source_sha256'],path=name,file_sha256=digest(output/name),bbox=bbox,geometry=geometry))
        Image.fromarray(result['mask'].astype(np.uint8)*255).save(output/(sid+'_coarse.png'));sources.append(record|dict(coarse_seconds=seconds))
    manifest=dict(version=VERSION,purpose='inference',coordinate_system=COORDINATES,input_size=SIZE,context_padding=PADDING,crop_policy='coarse_guided_v1',sources=sources,crops=crops,GT_present=False)
    check_dataset(output,manifest,'inference')
    (output/'manifest.private.json').write_text(json.dumps(manifest,indent=2));return manifest

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--inputs',type=Path,required=True);p.add_argument('--semantic-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();prepare(json.loads(a.inputs.read_text(encoding='utf-8-sig')),a.semantic_root,a.output)
