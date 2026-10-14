"""Exact pixel ownership grouping, not fragment filtering or overlap argmax."""
import numpy as np
from photo_learned_pad_pipeline_v1 import associate_learned_body_axis
from photo_resize_safety_v1 import validate_resize


def partition(mask,contexts):
    if not isinstance(mask,np.ndarray) or mask.dtype!=np.bool_ or mask.ndim!=2 or min(mask.shape)<1:
        raise ValueError('owner_partition_mask_contract')
    validate_resize(*mask.shape,1.)
    if not isinstance(contexts,list) or len(contexts)>256:raise ValueError('owner_partition_context_limit')
    coverage=np.zeros(mask.shape,np.uint16);owner_id=np.zeros(mask.shape,np.uint16)
    seen=set()
    for i,context in enumerate(contexts,1):
        owner=context['body'];identity=context['candidate_id']
        if owner.dtype!=np.bool_ or owner.shape!=mask.shape or identity in seen:raise ValueError('owner_partition_context_contract')
        seen.add(identity);inside=mask&owner;coverage[inside]+=1;owner_id[inside]=i
    labels=np.zeros(mask.shape,np.uint16);records=[]
    def add(native,reason,association=None,owner=None,identity=None):
        if not native.any():return
        component=len(records)+1;labels[native]=component
        records.append(dict(plan=dict(component=component,status='planned' if reason is None else 'rejected',
                            reject_reason=reason,working_scale=1.,mask_pixels=int(native.sum())),
                            reason=reason,association=association,owner=owner,candidate_id=identity))
    for i,context in enumerate(contexts,1):
        native=mask&(coverage==1)&(owner_id==i)
        if not native.any():continue
        try:
            association,owner=associate_learned_body_axis(native,[context])
            association['estimator_region_index']=context['estimator_region_index']
            association['association_policy']='unique_pixel_body_owner_group_all_fragments'
            for key in ['native_body_component','native_owner_policy','native_body_edge_pixels_restored','anatomical_owner_verified']:
                if key in context:association[key]=context[key]
            add(native,None,association,owner,context['candidate_id'])
        except ValueError as error:add(native,str(error),identity=context['candidate_id'])
    add(mask&(coverage==0),'learned_body_owner_unavailable')
    add(mask&(coverage>1),'learned_body_owner_ambiguous')
    if not np.array_equal(labels>0,mask):raise ValueError('owner_partition_pixel_loss')
    return dict(labels=labels,records=records)
