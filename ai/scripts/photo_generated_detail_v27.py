"""Visible generated relief for precautionary surfaces, never source sharpening.

The floor changes only scalar style summaries passed to the independent
material. Source ridge pixels, phase and orientation are not supplied to it.
"""
import secrets
import numpy as np
from photo_synthetic_replacement_v19 import render as render_v19

VERSION='visible_generated_surface_detail_v27_experimental'
MINIMUM_BAND_STYLE=(1.5,3.,3.,1.2)


def render(rgb,mask,labels,*,seed=None,detail_regions=()):
    if (not isinstance(detail_regions,(tuple,list)) or len(set(detail_regions))!=len(detail_regions)
            or any(type(i) is not int or not 1<=i<=65535 for i in detail_regions)):
        raise ValueError('generated_detail_region_contract')
    present={int(i) for i in np.unique(labels) if i}
    selected=present&set(detail_regions)
    if not selected:return render_v19(rgb,mask,labels,seed=seed)
    if seed is None:seed=secrets.randbits(128)
    if type(seed) is not int or not 0<=seed<2**128:raise ValueError('synthetic_seed_unsigned_128bit_required')
    children={int(np.random.SeedSequence([seed,i]).generate_state(1,dtype=np.uint64)[0]):i for i in present}
    if len(children)!=len(present):raise ValueError('generated_detail_seed_collision')
    def style(child,stats):
        return np.maximum(stats,MINIMUM_BAND_STYLE) if children[child] in selected else stats
    result,report=render_v19(rgb,mask,labels,seed=seed,generated_style=style)
    report['generated_detail_policy']=dict(version=VERSION,region_ids=sorted(selected),
        minimum_band_style=list(MINIMUM_BAND_STYLE),source_ridge_pixels_used=False,
        original_fingerprint_reconstruction=False,visibility_verified=False)
    return result,report
