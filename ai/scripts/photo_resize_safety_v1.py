"""Deterministic allocation bounds, not detector/renderer quality thresholds."""
import math
MAX_DIMENSION=32768
MAX_WORKING_PIXELS=32*1024*1024
MAX_ESTIMATED_WORKING_BYTES=2*1024**3
WORKING_BYTES_PER_PIXEL=64 # conservative multi-buffer planning estimate, not process RSS
class ResizeSafetyError(ValueError):
    def __init__(self,reason,audit):super().__init__(reason);self.reason=reason;self.audit=audit

def validate_resize(height,width,scale,channels=3,itemsize=1):
    audit=dict(source_height=height,source_width=width,scale=scale,channels=channels,itemsize=itemsize,max_dimension=MAX_DIMENSION,max_working_pixels=MAX_WORKING_PIXELS,max_estimated_working_bytes=MAX_ESTIMATED_WORKING_BYTES,working_bytes_per_pixel=WORKING_BYTES_PER_PIXEL)
    def reject(reason):raise ResizeSafetyError(reason,audit)
    try:
        if any(not math.isfinite(float(v)) or float(v)<=0 for v in [height,width,scale,channels,itemsize]):reject('adapter_resize_invalid')
        if any(float(v)!=int(v) for v in [height,width,channels,itemsize]):reject('adapter_resize_invalid')
        hf=float(height)*float(scale);wf=float(width)*float(scale)
        if not math.isfinite(hf) or not math.isfinite(wf):reject('adapter_resize_invalid')
        h=max(1,round(hf));w=max(1,round(wf)) # identical historical rounding, no scale clamp
        pixels=h*w;allocation=pixels*int(channels)*int(itemsize);planning=pixels*WORKING_BYTES_PER_PIXEL
        audit.update(requested_height=h,requested_width=w,requested_pixels=pixels,requested_array_bytes=allocation,estimated_working_bytes=planning)
        if max(h,w)>MAX_DIMENSION or pixels>MAX_WORKING_PIXELS or planning>MAX_ESTIMATED_WORKING_BYTES:reject('adapter_memory_limit_exceeded')
        return (h,w),audit
    except (OverflowError,TypeError):reject('adapter_resize_invalid')

def clip_bbox(bbox,width,height):
    if len(bbox)!=4 or not all(math.isfinite(float(v)) for v in bbox):raise ValueError('adapter_resize_invalid')
    x0,y0,x1,y1=map(int,bbox);x0=max(0,min(width,x0));x1=max(0,min(width,x1));y0=max(0,min(height,y0));y1=max(0,min(height,y1))
    if x1<=x0 or y1<=y0:raise ValueError('adapter_resize_invalid')
    return [x0,y0,x1,y1]
