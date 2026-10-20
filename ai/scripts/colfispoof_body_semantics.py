"""External model adapter exposing class 1+2 body and class 2 tip separately."""
import argparse,json,hashlib,os
from pathlib import Path
import numpy as np
from PIL import Image
from colfispoof_raw_semantics import RawDeepLabRuntime,prepare,restore,vote_masks


def predict_body(runtime,rgb):
    if rgb.dtype!=np.uint8 or rgb.ndim!=3 or rgb.shape[2]!=3:raise ValueError('uint8_RGB_required')
    bodies=[];tips=[]
    for k in range(4):
        padded,geometry=prepare(np.rot90(rgb,-k).copy());_,labels=runtime.model.run(Image.fromarray(padded))
        # Nearest-neighbour selection commutes with per-pixel class membership.
        # Select the exact legacy OpenCV source indices before classifying a
        # 4608-wide label map twice. Keep odd padding and inverse mapping intact.
        height,width=padded.shape[:2]
        ys=np.minimum((np.arange(height)*(labels.shape[0]/height)).astype(np.intp),labels.shape[0]-1)
        xs=np.minimum((np.arange(width)*(labels.shape[1]/width)).astype(np.intp),labels.shape[1]-1)
        small=labels[np.ix_(ys,xs)]
        bodies.append(restore(((small==1)|(small==2)).astype(np.uint8)*2,geometry,k));tips.append(restore(small,geometry,k))
    body=vote_masks(bodies);tip=vote_masks(tips)
    if (tip&~body).any():raise ValueError('semantic_subset_contract_failed')
    return dict(body=body,tip=tip,body_classes=[1,2],tip_class=2,minimum_votes=2,coordinate_system='encoded_original_pixels')

def write_prediction(runtime,source,output):
    source,output=Path(source),Path(output)
    if output.exists():raise FileExistsError('fresh private output directory required')
    sha=hashlib.sha256(source.read_bytes()).hexdigest()
    with Image.open(source) as im:rgb=np.asarray(im.convert('RGB')).copy()
    result=predict_body(runtime,rgb)
    if hashlib.sha256(source.read_bytes()).hexdigest()!=sha:raise ValueError('semantic_source_changed')
    output.mkdir(parents=True)
    for key in ['body','tip']:Image.fromarray(result[key].astype(np.uint8)*255).save(output/(key+'.png'))
    (output/'semantics.json').write_text(json.dumps(dict(source_sha256=sha,image_width=rgb.shape[1],image_height=rgb.shape[0],body_classes=[1,2],tip_class=2,minimum_votes=2,coordinate_system='encoded_original_pixels',body_sha256=hashlib.sha256((output/'body.png').read_bytes()).hexdigest(),tip_sha256=hashlib.sha256((output/'tip.png').read_bytes()).hexdigest(),execution_device=runtime.device),indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--external-source',type=Path,required=True);p.add_argument('--model',type=Path,required=True);a=p.parse_args()
    runtime=RawDeepLabRuntime(a.external_source,a.model,
        device=os.environ.get('BLURFING_COLFISPOOF_DEVICE','cpu'),
        dll_directories=json.loads(os.environ.get('BLURFING_COLFISPOOF_DLL_DIRS','[]')))
    try:write_prediction(runtime,a.input,a.output)
    finally:runtime.close()
