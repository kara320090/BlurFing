"""Prepare private coarse-guided crops. GT determines labels, never crop boxes."""
import argparse,json,hashlib
from pathlib import Path
import cv2
import numpy as np
from PIL import Image

ALLOWED=('TRN-001','TRN-002','TRN-003','TRN-004','TRN-006','TRN-010','TRN-014','TRN-016','TRN-020','TRN-022')
SIZE=256
PADDING=.35


def guided_bbox(mask):
    y,x=np.where(mask)
    if not len(x):raise ValueError('empty_coarse_proposal')
    h,w=mask.shape;a,b,c,d=int(x.min()),int(y.min()),int(x.max())+1,int(y.max())+1;padding=round(PADDING*max(c-a,d-b))
    return [max(0,a-padding),max(0,b-padding),min(w,c+padding),min(h,d+padding)]


def letterbox(rgb,coarse,label):
    h,w=coarse.shape;scale=SIZE/max(h,w);nw,nh=max(1,round(w*scale)),max(1,round(h*scale));left=(SIZE-nw)//2;top=(SIZE-nh)//2
    image=np.zeros((SIZE,SIZE,3),np.uint8);c=np.zeros((SIZE,SIZE),np.uint8);g=c.copy();sl=np.s_[top:top+nh,left:left+nw]
    image[sl]=cv2.resize(rgb,(nw,nh),interpolation=cv2.INTER_AREA);c[sl]=cv2.resize(coarse.astype(np.uint8),(nw,nh),interpolation=cv2.INTER_NEAREST);g[sl]=cv2.resize(label.astype(np.uint8),(nw,nh),interpolation=cv2.INTER_NEAREST)
    return image,c,g,dict(width=w,height=h,scaled_width=nw,scaled_height=nh,left=left,top=top)


def prepare(roster,annotations,semantic_root,output,test_source_hashes):
    from finger_body_distal_estimator import estimate
    from evaluate_distal_pad_gt7 import validate_annotation
    from evaluate_finger_body_distal import read_binary
    rows=[r for r in roster if r['sample_id'] in ALLOWED]
    if {r['sample_id'] for r in rows}!=set(ALLOWED) or len(rows)!=10:raise ValueError('exact ten-source roster required')
    if any(r['source_sha256'] in test_source_hashes for r in rows):raise ValueError('GT7_train_overlap')
    output.mkdir(parents=True,exist_ok=False);sources=[];crops=[]
    for row in rows:
        sid=row['sample_id'];source=Path(row['source_path']);identity=json.loads((semantic_root/sid/'semantics.json').read_text());gt,info=validate_annotation(annotations/sid,source)
        if info['status']!='valid_positive':raise ValueError('unusable_training_annotation: '+sid)
        if identity['source_sha256']!=info['source_sha256']:raise ValueError('source_semantics_mismatch')
        with Image.open(source) as im:rgb=np.asarray(im.convert('RGB')).copy()
        body=read_binary(semantic_root/sid/'body.png',rgb.shape[:2],identity['body_sha256']);tip=read_binary(semantic_root/sid/'tip.png',rgb.shape[:2],identity['tip_sha256']);result=estimate(body,tip);count=0
        # Neither GT shape geometry nor label components are used for boxes.
        for i,region in enumerate(result['regions']):
            if region.get('reject_reason') is not None:continue
            coarse=region['mask'];bbox=guided_bbox(coarse);a,b,c,d=bbox;image,mask,label,geometry=letterbox(rgb[b:d,a:c],coarse[b:d,a:c],gt[b:d,a:c]);name=f'{sid}_crop_{i:03d}.npz';np.savez_compressed(output/name,rgb=image,coarse=mask,label=label)
            crops.append(dict(source_id=sid,path=name,bbox=bbox,geometry=geometry));count+=1
        sources.append(dict(source_id=sid,source_sha256=info['source_sha256'],source_path=str(source),GT_folder=str(annotations/sid),body_path=str(semantic_root/sid/'body.png'),width=rgb.shape[1],height=rgb.shape[0],crop_count=count))
    manifest=dict(version='pad_refinement_data_v1',sources=sources,crops=crops,input_size=SIZE,context_padding=PADDING,GT7_source_hashes=list(test_source_hashes),GT7_train_overlap=0,coarse_version='finger_body_distal_v2_experimental',blocked_sources=[s['source_id'] for s in sources if not s['crop_count']]);(output/'manifest.private.json').write_text(json.dumps(manifest,indent=2));return manifest

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--roster',type=Path,required=True);p.add_argument('--annotations',type=Path,required=True);p.add_argument('--semantic-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--test-hashes',type=Path,required=True);a=p.parse_args();r=json.loads(a.roster.read_text());prepare(r['samples'],a.annotations,a.semantic_root,a.output,json.loads(a.test_hashes.read_text()))
