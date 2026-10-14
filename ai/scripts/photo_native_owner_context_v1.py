"""Recover native boundary coverage only for exact one-to-one body owners.

Down/up nearest-neighbor geometry can omit original semantic edge pixels.
If one native connected body has exactly one estimator owner AND that owner
has exactly one native body, retain the complete observed native body.
Multiple watershed owners, split/merged components and missing owners remain
unchanged. No nearest/majority assignment, new pixels or anatomical assertion.
"""
import numpy as np
from scipy import ndimage
from finger_body_distal_estimator import validate_candidate_context_allocation

VERSION='one_to_one_native_body_context_v1_experimental'


def restore_contexts(contexts,body):
    if (not isinstance(body,np.ndarray) or body.ndim!=2 or body.dtype!=np.bool_ or min(body.shape)<1 or
            not isinstance(contexts,list) or len(contexts)>256):
        raise ValueError('native_owner_context_contract')
    validate_candidate_context_allocation(*body.shape,2*len(contexts))
    # Native noise can contain millions of components. Retain a bounded dense
    # integer owner-count plane, never one Python container per component.
    labels,count=ndimage.label(body);by_owner=[];owner_counts=np.zeros(count+1,np.uint16)
    for index,context in enumerate(contexts):
        owner=context['body']
        if owner.dtype!=np.bool_ or owner.shape!=body.shape or np.any(owner&~body):raise ValueError('native_owner_context_subset_contract')
        observed=np.unique(labels[owner]);observed=observed[observed!=0]
        by_owner.append(int(observed[0]) if len(observed)==1 else None)
        owner_counts[observed]+=1
    result=[]
    for index,context in enumerate(contexts):
        native=by_owner[index]
        if native is not None and owner_counts[native]==1 and context['reject_reason'] is None:
            owner=labels==native
            result.append(context|dict(body=owner,native_body_component=native,native_owner_policy=VERSION,
                native_body_edge_pixels_restored=int(owner.sum()-context['body'].sum()),anatomical_owner_verified=False))
        else:result.append(context)
    return result
