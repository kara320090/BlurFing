"""Reuse identical observed geometry within one job, with isolated outputs."""
import copy
import hashlib
import numpy as np
from finger_body_distal_estimator import estimate as original
from finger_body_distal_estimator import component_pad as original_component

MAX_BYTES=64*1024**2


def component_pad(component,tip):
    from photo_lossless_io_v29 import _state
    state=_state.get()
    if state is None:return original_component(component,tip)
    key=(component.shape,component.dtype.str,tip.dtype.str,
        hashlib.sha256(component.tobytes()).digest(),hashlib.sha256(tip.tobytes()).digest())
    if key in state.components:
        state.component_hits+=1
        return copy.deepcopy(state.components[key])
    result=original_component(component,tip);size=_size(result)
    if state.component_bytes+size<=MAX_BYTES:
        state.components[key]=copy.deepcopy(result);state.component_bytes+=size
    return result


def install_component_cache():
    # The frozen estimator/training bytes stay intact. Only pure identical
    # subproblems within the active job reuse independent array copies.
    import finger_body_distal_estimator as estimator
    estimator.component_pad=component_pad


def _size(value):
    if isinstance(value,np.ndarray):return value.nbytes
    if isinstance(value,dict):return sum(_size(v) for v in value.values())
    if isinstance(value,(tuple,list)):return sum(map(_size,value))
    return 0


def estimate(body,tip,*,preserve_candidates=False):
    from photo_lossless_io_v29 import _state
    state=_state.get()
    if (state is None or not isinstance(body,np.ndarray) or not isinstance(tip,np.ndarray) or
            body.dtype!=np.bool_ or tip.dtype!=np.bool_ or body.ndim!=2 or body.shape!=tip.shape or
            type(preserve_candidates) is not bool):
        return original(body,tip,preserve_candidates=preserve_candidates)
    key=(body.shape,hashlib.sha256(body.tobytes()).digest(),hashlib.sha256(tip.tobytes()).digest(),preserve_candidates)
    if key in state.coarse:
        result=state.coarse.pop(key);state.coarse[key]=result;state.coarse_hits+=1
        return copy.deepcopy(result)
    result=original(body,tip,preserve_candidates=preserve_candidates);size=_size(result)
    if size<=MAX_BYTES:
        while state.coarse and state.coarse_bytes+size>MAX_BYTES:
            _,old=state.coarse.popitem(last=False);state.coarse_bytes-=_size(old)
        state.coarse[key]=copy.deepcopy(result);state.coarse_bytes+=size
    return result
