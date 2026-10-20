"""Native V19/V27 material, independently rendered per existing component ID."""
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
import secrets
import numpy as np
from photo_rejection_resolution_v1 import pixel_hash
from photo_parallel_regions_v32 import _workers,MAX_PARALLEL_RGB_BYTES


def render(engine,rgb,mask,labels,*,seed=None):
    ids=np.unique(labels[mask])
    if _workers.get()==1 or not 1<len(ids)<=8 or rgb.nbytes*len(ids)>MAX_PARALLEL_RGB_BYTES:
        return engine(rgb,mask,labels,seed=seed)
    if seed is None:seed=secrets.randbits(128)
    if type(seed) is not int or not 0<=seed<2**128:raise ValueError('synthetic_seed_unsigned_128bit_required')
    def one(rid):
        target=labels==rid
        partition=np.where(target,labels,0).astype(np.uint16)
        out,report=engine(rgb,target,partition,seed=seed)
        return target,out,report
    with ThreadPoolExecutor(max_workers=_workers.get()) as pool:
        futures=[pool.submit(copy_context().run,one,rid) for rid in ids]
        results=[future.result() for future in futures]
    out=rgb.copy();report=dict(results[0][2]);regions=[];detail=[]
    for target,generated,meta in results:
        out[target]=generated[target];regions.extend(meta['regions'])
        if 'generated_detail_policy' in meta:detail.extend(meta['generated_detail_policy']['region_ids'])
    report.update(regions=regions,replacement_regions=len(regions),replaced_pixels=int(mask.sum()),
        macro_crease_count=sum(meta['macro_crease_count'] for _,_,meta in results),
        unresolved_texture_regions=sum(not row['fingerprint_texture_resolved'] for row in regions),
        actual_changed_pixels=int(np.any(out!=rgb,axis=2).sum()),output_RGB_sha256=pixel_hash(out),mask_sha256=pixel_hash(mask))
    if detail:
        policy=next(meta['generated_detail_policy'] for _,_,meta in results if 'generated_detail_policy' in meta)
        report['generated_detail_policy']=dict(policy,region_ids=sorted(detail))
    return out,report
