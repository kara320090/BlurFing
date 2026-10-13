"""External model adapter exposing class 1+2 body and class 2 tip separately."""
import argparse,json,hashlib
from pathlib import Path
import numpy as np
from PIL import Image
from colfispoof_raw_semantics import RawDeepLabRuntime,prepare,restore,vote_masks


def predict_body(runtime,rgb):
    if rgb.dtype!=np.uint8 or rgb.ndim!=3 or rgb.shape[2]!=3:raise ValueError('uint8_RGB_required')
    bodies=[];tips=[]
    for k in range(4):
        padded,geometry=prepare(np.rot90(rgb,-k).copy());_,labels=runtime.model.run(Image.fromarray(padded))
        bodies.append(restore(np.isin(labels,[1,2]).astype(np.uint8)*2,geometry,k));tips.append(restore(labels,geometry,k))
    body=vote_masks(bodies);tip=vote_masks(tips)
    if (tip&~body).any():raise ValueError('semantic_subset_contract_failed')
    return dict(body=body,tip=tip,body_classes=[1,2],tip_class=2,minimum_votes=2,coordinate_system='encoded_original_pixels')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--external-source',type=Path,required=True);p.add_argument('--model',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise FileExistsError('fresh private output directory required')
    sha=hashlib.sha256(a.input.read_bytes()).hexdigest()
    with Image.open(a.input) as im:rgb=np.asarray(im.convert('RGB')).copy()
    runtime=RawDeepLabRuntime(a.external_source,a.model)
    try:result=predict_body(runtime,rgb)
    finally:runtime.close()
    assert hashlib.sha256(a.input.read_bytes()).hexdigest()==sha;a.output.mkdir(parents=True)
    for key in ['body','tip']:Image.fromarray(result[key].astype(np.uint8)*255).save(a.output/(key+'.png'))
    (a.output/'semantics.json').write_text(json.dumps(dict(source_sha256=sha,image_width=rgb.shape[1],image_height=rgb.shape[0],body_classes=[1,2],tip_class=2,minimum_votes=2,coordinate_system='encoded_original_pixels',body_sha256=hashlib.sha256((a.output/'body.png').read_bytes()).hexdigest(),tip_sha256=hashlib.sha256((a.output/'tip.png').read_bytes()).hexdigest()),indent=2))
