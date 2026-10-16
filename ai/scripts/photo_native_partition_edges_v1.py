"""Restore only unambiguous native raster gaps next to estimator owners.

The radius is the diagonal of one estimator pixel in source coordinates.
Already assigned pixels never change owner. A gap reached by multiple owners
remains unresolved, as do distant BODY pixels. No new BODY is synthesized.
"""
import math
import cv2
import numpy as np
from photo_rounded_pad_v1 import _mask

VERSION='unique_native_quantization_band_v1'


def restore_edges(contexts,body):
    _mask(body)
    if len(contexts)>256:raise ValueError('native_edge_context_limit')
    seen=np.zeros_like(body);coverage=np.zeros(body.shape,np.uint16);winner=np.zeros_like(coverage)
    for context in contexts:
        owner=context['body'];_mask(owner)
        if owner.shape!=body.shape or np.any(owner&~body) or np.any(seen&owner):
            raise ValueError('native_edge_owner_partition_contract')
        seen|=owner
    missing=body&~seen
    for i,context in enumerate(contexts,1):
        if context['reject_reason'] is not None:continue
        scale=float(context['parent']['working_scale'])
        if not np.isfinite(scale) or scale<=0:raise ValueError('native_edge_scale_contract')
        radius=math.ceil(math.sqrt(2)/scale)
        if radius>256:continue  # Explicitly leave an excessive/unresolved band.
        band=cv2.dilate(context['body'].astype(np.uint8),cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(radius*2+1,radius*2+1)))>0
        reached=band&missing;coverage[reached]+=1;winner[reached]=i
    return [context|dict(body=context['body']|((coverage==1)&(winner==i)),native_edge_policy=VERSION,
        native_partition_edge_pixels_restored=int(((coverage==1)&(winner==i)).sum())) for i,context in enumerate(contexts,1)]
