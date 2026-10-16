"""Opt-in quarter-turn probability ensemble; existing view inference stays frozen.

Four complete model views include their original coarse/context/tile policy.
The sorted per-pixel reduction is independent of cyclic view order. This gives
quarter-turn consistency only when a view predictor is deterministic from its
RGB/BODY/TIP inputs. It does not establish correct detection or privacy.
"""
import hashlib
import numpy as np
from photo_resize_safety_v1 import validate_resize,MAX_ESTIMATED_WORKING_BYTES

VERSION='quarter_turn_sorted_probability_orbit_v1_experimental'


def _sha(value):return hashlib.sha256(value.tobytes()).hexdigest()


def combine_restored_probabilities(views):
    if not isinstance(views,(list,tuple)) or len(views)!=4:
        raise ValueError('four_probability_views_required')
    first=views[0]
    if not isinstance(first,np.ndarray) or first.ndim!=2 or min(first.shape)<1:
        raise ValueError('probability_shape_contract')
    validate_resize(*first.shape,1.)
    if first.size*24+4*64*first.shape[1]*12>MAX_ESTIMATED_WORKING_BYTES:
        raise ValueError('orbit_probability_memory_limit')
    for value in views:
        if (not isinstance(value,np.ndarray) or value.shape!=first.shape or value.dtype!=np.float32 or
                not np.isfinite(value).all() or np.any(value<0) or np.any(value>1)):
            raise ValueError('finite_float32_probability_views_required')
    result=np.empty(first.shape,np.float32)
    for y in range(0,first.shape[0],64):
        # Sorting fixes summation order too, including threshold-near values.
        values=np.sort(np.stack([p[y:y+64] for p in views]),axis=0)
        result[y:y+64]=values.mean(axis=0,dtype=np.float64).astype(np.float32)
    return result


def predict_orbit(rgb,body,tip,predict_one):
    if (not isinstance(rgb,np.ndarray) or rgb.dtype!=np.uint8 or rgb.ndim!=3 or rgb.shape[2]!=3 or
            not isinstance(body,np.ndarray) or not isinstance(tip,np.ndarray) or body.dtype!=np.bool_ or
            tip.dtype!=np.bool_ or body.shape!=rgb.shape[:2] or tip.shape!=body.shape or np.any(tip&~body)):
        raise ValueError('orbit_RGB_semantic_contract')
    validate_resize(*body.shape,1.)
    before=tuple(_sha(a) for a in (rgb,body,tip));views=[];bindings=[]
    for turn in range(4):
        arrays=tuple(np.rot90(a,turn).copy() for a in (rgb,body,tip))
        pins=tuple(_sha(a) for a in arrays)
        value=predict_one(*arrays)
        if tuple(_sha(a) for a in arrays)!=pins:raise ValueError('orbit_predictor_mutated_input')
        if not isinstance(value,np.ndarray) or value.shape!=arrays[1].shape:
            raise ValueError('orbit_predictor_shape_contract')
        restored=np.rot90(value,-turn).copy()
        # Validate before retaining a view, not just after all model calls.
        if restored.dtype!=np.float32 or not np.isfinite(restored).all() or np.any(restored<0) or np.any(restored>1):
            raise ValueError('finite_float32_probability_views_required')
        views.append(restored)
        bindings.append(dict(quarter_turn=turn,RGB_sha256=pins[0],BODY_sha256=pins[1],TIP_sha256=pins[2],
                             probability_sha256=_sha(value)))
    if tuple(_sha(a) for a in (rgb,body,tip))!=before:raise ValueError('orbit_source_changed')
    probability=combine_restored_probabilities(views)
    return probability,dict(version=VERSION,views=bindings,model_views=4,default_enabled=False,
        model_retrained=False,independent_final_test=False,privacy_validated=False,
        consistency_condition='deterministic identical-input view inference; sorted mean reduction',
        final_probability_sha256=_sha(probability))
