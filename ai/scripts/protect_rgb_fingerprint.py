import numpy as np

def validate_roi(image, roi):
    a=np.asarray(image)
    if a.ndim!=3 or a.shape[2]!=3 or a.dtype!=np.uint8:
        raise ValueError('Expected HxWx3 uint8 RGB')
    if len(roi)!=4 or any(isinstance(v,(bool,np.bool_)) or not isinstance(v,(int,np.integer)) for v in roi):
        raise ValueError('ROI must contain four integer pixel coordinates')
    x0,y0,x1,y1=map(int,roi)
    if not (0<=x0<x1<=a.shape[1] and 0<=y0<y1<=a.shape[0]):
        raise ValueError('ROI must be inside image; no implicit clipping')
    if x1-x0!=y1-y0 or x1-x0<32:
        raise ValueError('Use square fingertip ROI at least 32 native pixels')
    return a,(x0,y0,x1,y1)
