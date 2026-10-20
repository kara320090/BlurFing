"""Exact sparse-mask crops; leave unsupported SciPy signatures unchanged."""
from contextvars import ContextVar
import cv2
import numpy as np
from scipy import ndimage

enabled=ContextVar('photo_sparse_mask_roi',default=False)
_label=ndimage.label
_distance=ndimage.distance_transform_edt
_holes=ndimage.binary_fill_holes
_isin=np.isin


def bounds(values):
    array=np.asarray(values)
    if array.ndim!=2 or array.size<65536:return None
    x,y,w,h=cv2.boundingRect(np.ascontiguousarray(array!=0,dtype=np.uint8))
    if not w:return (slice(0,0),slice(0,0))
    y0,y1=max(0,y-1),min(array.shape[0],y+h+1)
    x0,x1=max(0,x-1),min(array.shape[1],x+w+1)
    return (slice(y0,y1),slice(x0,x1)) if (y1-y0)*(x1-x0)<array.size*.6 else None


def label(values,structure=None,output=None):
    box=bounds(values) if enabled.get() and output is None else None
    if box is None:return _label(values,structure,output)
    labels,count=_label(np.asarray(values)[box],structure)
    result=np.zeros(np.shape(values),labels.dtype);result[box]=labels
    return result,count


def distance(values,sampling=None,return_distances=True,return_indices=False,distances=None,indices=None):
    box=bounds(values) if (enabled.get() and sampling is None and return_distances and not return_indices
        and distances is None and indices is None) else None
    if box is None:return _distance(values,sampling,return_distances,return_indices,distances,indices)
    result=np.zeros(np.shape(values),np.float64)
    if np.asarray(values)[box].size:result[box]=_distance(np.asarray(values)[box])
    return result


def holes(values,structure=None,output=None,origin=0,**kwargs):
    box=bounds(values) if enabled.get() and output is None and origin==0 and not kwargs else None
    if box is None:return _holes(values,structure,output,origin,**kwargs)
    result=np.zeros(np.shape(values),bool)
    if np.asarray(values)[box].size:result[box]=_holes(np.asarray(values)[box],structure)
    return result


def install():
    ndimage.label=label;ndimage.distance_transform_edt=distance;ndimage.binary_fill_holes=holes
    np.isin=isin


def isin(element,test_elements,assume_unique=False,invert=False,*,kind=None):
    if (enabled.get() and kind is None and isinstance(element,np.ndarray)
            and element.size>=65536 and element.dtype.kind in 'bui'):
        tests=np.asarray(test_elements)
        if tests.ndim<=1 and 0<len(tests.reshape(-1))<=4 and tests.dtype.kind in 'bui':
            values=[int(v) for v in tests.reshape(-1)]
            lo,hi=(0,1) if element.dtype.kind=='b' else (np.iinfo(element.dtype).min,np.iinfo(element.dtype).max)
            if min(values)>=lo and max(values)<=hi:
                result=element==values[0]
                for value in values[1:]:result|=element==value
                return ~result if invert else result
    return _isin(element,test_elements,assume_unique,invert,kind=kind)
