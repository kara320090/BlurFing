"""Explicit opt-in coarse PHOTO integration; never enables the default PHOTO API.

All output files are private. A source-bound semantic cache can be generated with
colfispoof_body_semantics.py in the isolated TensorFlow environment first.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time
import numpy as np
from PIL import Image
from photo_coarse_adapter import adapt
from photo_coarse_renderer_adapter_v1 import transform


def run(source,semantics,output,strength=.5):
    output=Path(output)
    if output.exists():raise FileExistsError('fresh private output directory required')
    tick=time.perf_counter();rgb,artifact=adapt(source,semantics);adapter_seconds=time.perf_counter()-tick
    returned,details=transform(rgb,artifact,strength)
    output.mkdir(parents=True)
    Image.fromarray(returned).save(output/'returned.png')
    masks=[]
    for entry in artifact['regions']:
        name=f"pad_{entry['component']}.png";Image.fromarray(entry['roi'].binary_mask).save(output/name)
        masks.append(entry['roi'].metadata()|dict(mask_path=name,mask_sha256=hashlib.sha256((output/name).read_bytes()).hexdigest(),working_seed=entry['working_seed'],working_scope=entry['working_scope']))
    report=dict(schema_version='photo-coarse-experimental-v1',source_sha256=artifact['source_sha256'],image_width=rgb.shape[1],image_height=rgb.shape[0],coordinate_system='encoded_original_pixels',exif_orientation=artifact['exif_orientation'],working_scale=artifact['working_scale'],working_shape=artifact['working_shape'],detected_pad_count=artifact['detected_pad_count'],canonical_pad_count=len(masks),regions=masks,rejected=artifact['rejected'],adapter_seconds=adapter_seconds,transform=details,PHOTO_DETECTOR_APPROVED=False,PHOTO_PROTECTION_PRODUCTION_READY=False)
    (output/'result.private.json').write_text(json.dumps(report,indent=2,default=lambda x:x.item() if isinstance(x,np.generic) else str(x)))
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--semantics',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--strength',type=float,choices=[0,.5],default=.5);a=p.parse_args()
    print(json.dumps(run(a.input,a.semantics,a.output,a.strength),default=lambda x:x.item() if isinstance(x,np.generic) else str(x)))
