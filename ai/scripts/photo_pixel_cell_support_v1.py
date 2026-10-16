"""Integer pixel-cell overlap support, independent of OpenCV nearest rounding.

A destination cell is true iff it has positive-area overlap with any true
source cell. This is a conservative support envelope, NOT permission to alter
every envelope pixel. Labels need separate ambiguity checks; learned V6 inputs
and existing permission masks are never silently resized with this policy.
"""
import numpy as np
from photo_resize_safety_v1 import validate_resize,MAX_ESTIMATED_WORKING_BYTES

VERSION='positive_area_boolean_pixel_cells_v1_experimental'


def _axis(mask,length,axis):
    source=mask.shape[axis]
    if source==length:return mask.copy()
    indices=np.arange(length,dtype=np.int64)
    starts=indices*source//length
    stops=((indices+1)*source+length-1)//length
    summed=np.cumsum(mask,axis=axis,dtype=np.uint32)
    zero_shape=list(summed.shape);zero_shape[axis]=1
    prefix=np.concatenate([np.zeros(zero_shape,np.uint32),summed],axis=axis)
    return np.take(prefix,stops,axis=axis)>np.take(prefix,starts,axis=axis)


def resize_support(mask,shape):
    if (not isinstance(mask,np.ndarray) or mask.dtype!=np.bool_ or mask.ndim!=2 or min(mask.shape)<1 or
            not isinstance(shape,(list,tuple)) or len(shape)!=2 or any(type(n) is not int or n<1 for n in shape)):
        raise ValueError('pixel_cell_support_contract')
    validate_resize(*mask.shape,1.);validate_resize(*shape,1.)
    h,w=mask.shape;H,W=shape
    intermediate=min(h*W,H*w)
    if 24*(mask.size+H*W+intermediate)>MAX_ESTIMATED_WORKING_BYTES:
        raise ValueError('pixel_cell_support_memory_limit')
    if h*W<=H*w:return _axis(_axis(mask,W,1),H,0)
    return _axis(_axis(mask,H,0),W,1)
