"""GT-free inference crops from the preserved semantic/coarse frontend."""
import argparse,json,hashlib,time
from pathlib import Path
import numpy as np
from PIL import Image
from finger_body_distal_estimator import estimate
from evaluate_finger_body_distal import read_binary
from prepare_pad_refinement_data import guided_bbox,letterbox


def prepare(inputs,semantic_root,output):
    if any(set(x)!={'sample_id','source','source_sha256'} for x in inputs):raise ValueError('source_identity_only; GT_fields_forbidden')
    output.mkdir(parents=True,exist_ok=False);sources=[];crops=[]
    for item in inputs:
        sid=item['sample_id'];source=Path(item['source']);identity=json.loads((semantic_root/sid/'semantics.json').read_text())
        if hashlib.sha256(source.read_bytes()).hexdigest()!=item['source_sha256'] or identity['source_sha256']!=item['source_sha256']:raise ValueError('source_hash_mismatch')
        with Image.open(source) as im:rgb=np.asarray(im.convert('RGB')).copy()
        body=read_binary(semantic_root/sid/'body.png',rgb.shape[:2],identity['body_sha256']);tip=read_binary(semantic_root/sid/'tip.png',rgb.shape[:2],identity['tip_sha256']);tick=time.perf_counter();result=estimate(body,tip);seconds=time.perf_counter()-tick
        for i,region in enumerate(result['regions']):
            if region.get('reject_reason') is not None:continue
            bbox=guided_bbox(region['mask']);a,b,c,d=bbox;image,mask,unused,geometry=letterbox(rgb[b:d,a:c],region['mask'][b:d,a:c],np.zeros((d-b,c-a),bool));name=f'{sid}_crop_{i:03d}.npz';np.savez_compressed(output/name,rgb=image,coarse=mask,label=unused);crops.append(dict(source_id=sid,path=name,bbox=bbox,geometry=geometry))
        Image.fromarray(result['mask'].astype(np.uint8)*255).save(output/(sid+'_coarse.png'));sources.append(dict(source_id=sid,source_path=str(source),source_sha256=item['source_sha256'],body_path=str(semantic_root/sid/'body.png'),width=rgb.shape[1],height=rgb.shape[0],coarse_seconds=seconds))
    manifest=dict(sources=sources,crops=crops,GT_present=False);(output/'manifest.private.json').write_text(json.dumps(manifest,indent=2));return manifest

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--inputs',type=Path,required=True);p.add_argument('--semantic-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();prepare(json.loads(a.inputs.read_text()),a.semantic_root,a.output)
