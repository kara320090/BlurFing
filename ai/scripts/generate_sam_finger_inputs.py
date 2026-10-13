"""Linux SAM producer; prompts are generated from RGB only, never human GT.

Two subprocess environments can be used: existing CV geometry environment for
prompts, existing read-only SAM environment for model inference. No dependency
installation is required in either environment.
"""
import argparse
import json
from pathlib import Path
import time
import cv2
import numpy as np
from PIL import Image,ImageOps
from sam_pad_detector import digest


def make_prompts(source):
    from automatic_boundary_v1 import _view_candidates,_rotation
    with Image.open(source) as im:rgb=np.asarray(ImageOps.exif_transpose(im).convert('RGB'))
    h,w=rgb.shape[:2];ratio=min(1.,1600/max(h,w));rows=[];seen=[]
    for k in range(4):
        view=np.rot90(rgb,k).copy();vh,vw=view.shape[:2];inv=cv2.invertAffineTransform(_rotation(k,h,w))
        for strict in [False,True]:
            for c in _view_candidates(view,1600,red_chroma_only=strict):
                cx=(c['seed_roi'][0]+c['seed_roi'][2])/2;cy=(c['seed_roi'][1]+c['seed_roi'][3])/2;width=c['width_native'];tip=c['tip_xy'][1];center=np.array([cx,cy,1.])@inv.T
                if any(np.linalg.norm(center-np.array(p))<.55*min(width,ww) for p,ww in seen):continue
                seen.append((center,width))
                points=np.array([[cx,tip+.65*width,1.],[cx-width,tip+.65*width,1.],[cx+width,tip+.65*width,1.]])@inv.T;labels=np.array([1,0,0]);valid=(points[:,0]>=0)&(points[:,0]<w)&(points[:,1]>=0)&(points[:,1]<h)
                corners=np.array([[max(0,cx-.9*width),max(0,tip-.15*width),1.],[min(vw-1,cx+.9*width),min(vh-1,tip+3*width),1.]])@inv.T
                box=np.array([corners[:,0].min(),corners[:,1].min(),corners[:,0].max(),corners[:,1].max()])*ratio
                tip_upright=np.array([c['tip_xy'][0],c['tip_xy'][1],1.])@inv.T
                rows.append(dict(tip_xy_upright=tip_upright.tolist(),points_working=(points[valid]*ratio).tolist(),labels=labels[valid].tolist(),box_working=box.tolist(),rotation_quadrants=k))
    return dict(source_sha256=digest(source),upright_width=w,upright_height=h,working_ratio=ratio,prompts=rows,prompt_source='automatic RGB-only geometric/ridge proposals; no manual/GT prompts')


def generate(source,output,predictor,model_sha,prompts):
    before=digest(source)
    with Image.open(source) as im:orientation=im.getexif().get(274,1);native_size=im.size;rgb=np.asarray(ImageOps.exif_transpose(im).convert('RGB'))
    h,w=rgb.shape[:2]
    if prompts['source_sha256']!=before or (prompts['upright_width'],prompts['upright_height'])!=(w,h):raise ValueError('prompt_source_mismatch')
    ratio=prompts['working_ratio'];working=cv2.resize(rgb,(round(w*ratio),round(h*ratio)),interpolation=cv2.INTER_AREA);output.mkdir(parents=True,exist_ok=False);tick=time.perf_counter();predictor.set_image(working);records=[];kept=[]
    inverse_exif={2:Image.Transpose.FLIP_LEFT_RIGHT,3:Image.Transpose.ROTATE_180,4:Image.Transpose.FLIP_TOP_BOTTOM,5:Image.Transpose.TRANSPOSE,6:Image.Transpose.ROTATE_90,7:Image.Transpose.TRANSVERSE,8:Image.Transpose.ROTATE_270}
    for i,row in enumerate(prompts['prompts']):
        masks,scores,_=predictor.predict(point_coords=np.array(row['points_working']),point_labels=np.array(row['labels']),box=np.array(row['box_working']),multimask_output=True)
        selected=int(np.argmax(scores));mask=cv2.resize(masks[selected].astype(np.uint8),(w,h),interpolation=cv2.INTER_NEAREST)>0
        im=Image.fromarray(mask.astype(np.uint8)*255)
        if orientation in inverse_exif:im=im.transpose(inverse_exif[orientation])
        mask=np.asarray(im)>0
        if any(np.count_nonzero(mask&old)/max(1,np.count_nonzero(mask|old))>.85 for old in kept):continue
        kept.append(mask);name=f'finger_{i:03d}.png';im.save(output/name)
        ux,uy=row['tip_xy_upright'];nw,nh=native_size
        tip_map={1:[ux,uy],2:[nw-1-ux,uy],3:[nw-1-ux,nh-1-uy],4:[ux,nh-1-uy],5:[uy,ux],6:[uy,nh-1-ux],7:[nw-1-uy,nh-1-ux],8:[nw-1-uy,ux]}
        tip_hint=tip_map.get(orientation,[ux,uy])
        records.append(dict(tip_hint_native=tip_hint,tip_hint_source='RGB-only fingertip proposal, not GT',mask_path=name,mask_sha256=digest(output/name),sam_predicted_iou=float(scores[selected]),prompt=row,selection='highest SAM predicted score; overlap dedup >0.85; no GT'))
    data=dict(schema_version='sam-finger-input-v1',source_sha256=before,image_width=native_size[0],image_height=native_size[1],coordinate_system='encoded_original_pixels',exif_orientation=orientation,working_ratio=ratio,model_sha256=model_sha,prompt_source=prompts['prompt_source'],masks=records,sam_seconds=time.perf_counter()-tick)
    if digest(source)!=before:raise ValueError('source_changed')
    (output/'sam_fingers.json').write_text(json.dumps(data,indent=2));return data

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['prompts','infer']);p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--checkpoint',type=Path);p.add_argument('--prompts',type=Path);a=p.parse_args()
    if a.mode=='prompts':
        if a.output.exists():raise ValueError('Output exists')
        a.output.write_text(json.dumps(make_prompts(a.input),indent=2))
    else:
        if a.checkpoint is None or a.prompts is None:p.error('infer requires --checkpoint and --prompts')
        import torch
        from segment_anything import sam_model_registry,SamPredictor
        torch.set_num_threads(4);torch.use_deterministic_algorithms(True);model=sam_model_registry['vit_b'](checkpoint=str(a.checkpoint));model.to(device='cpu');predictor=SamPredictor(model)
        with torch.inference_mode():print(json.dumps(generate(a.input,a.output,predictor,digest(a.checkpoint),json.loads(a.prompts.read_text())),indent=2))
