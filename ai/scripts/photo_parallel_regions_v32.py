"""Bounded independent appearance jobs; preserve stage ordering and native RGB."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from contextvars import ContextVar,copy_context
import numpy as np
from scipy import ndimage

_workers=ContextVar('photo_region_workers',default=1)
_inside=ContextVar('photo_region_job',default=False)
MAX_PARALLEL_RGB_BYTES=64*1024**2


@contextmanager
def region_workers(workers=2):
    if type(workers) is not int or not 1<=workers<=2:raise ValueError('photo_region_worker_limit')
    token=_workers.set(workers)
    try:yield
    finally:_workers.reset(token)


def split_regions(function,source,generated,applied,labels,**options):
    ids=np.unique(labels[applied])
    if (_workers.get()==1 or _inside.get() or not 1<len(ids)<=8
            or generated.nbytes*len(ids)>MAX_PARALLEL_RGB_BYTES):return None
    if sum(ndimage.label(applied&(labels==rid))[1] for rid in ids)>256:
        raise ValueError('appearance_region_count')
    def calculate(rid):
        token=_inside.set(True)
        try:
            take=applied&(labels==rid)
            out,report=function(source,generated,take,labels,**options)
            return take,out,report
        finally:_inside.reset(token)
    with ThreadPoolExecutor(max_workers=_workers.get()) as pool:
        futures=[pool.submit(copy_context().run,calculate,rid) for rid in ids]
        results=[future.result() for future in futures]
    returned=generated.copy();rows=[];report=None
    for take,out,metadata in results:
        returned[take]=out[take];rows.extend(metadata['regions'])
        if report is None:report=dict(metadata)
    report.update(regions=rows,corrected_components=sum(row['applied'] for row in rows))
    return returned,report
