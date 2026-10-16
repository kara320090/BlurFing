"""Versioned, conservative repair of learned permission/owner boundary gaps.

Only an unassigned connected permission piece with one adjacent observed owner
and adjacent existing permission for that owner can be linked. Decisions use
the original ownership plane simultaneously. Ambiguous, invalid and isolated
pieces stay unassigned. No predicted pixel is added, removed or relabeled to
an anatomical finger; this is an unapproved association experiment.
"""
import numpy as np
from scipy import ndimage
from finger_body_distal_estimator import validate_candidate_context_allocation

VERSION='unique_adjacent_permission_owner_v2_experimental'
MAX_GAPS=256


def repair_contexts(contexts, body, permission):
    if (not isinstance(contexts,list) or len(contexts)>256 or
            not isinstance(body,np.ndarray) or body.dtype!=np.bool_ or body.ndim!=2 or
            min(body.shape)<1 or not isinstance(permission,np.ndarray) or
            permission.dtype!=np.bool_ or permission.shape!=body.shape or np.any(permission&~body)):
        raise ValueError('owner_boundary_repair_input_contract')
    validate_candidate_context_allocation(*body.shape,2*len(contexts)+4)
    coverage=np.zeros(body.shape,np.uint16);ids=np.zeros(body.shape,np.uint16);seen=set()
    for index,context in enumerate(contexts,1):
        if not isinstance(context,dict):raise ValueError('owner_boundary_repair_context_contract')
        owner=context.get('body');identity=context.get('candidate_id')
        if (not isinstance(owner,np.ndarray) or owner.dtype!=np.bool_ or owner.shape!=body.shape or
                np.any(owner&~body) or not isinstance(identity,str) or identity in seen):
            raise ValueError('owner_boundary_repair_context_contract')
        seen.add(identity);coverage[owner]+=1;ids[owner]=index
    gaps=permission&(coverage==0);labels,count=ndimage.label(gaps)
    report=dict(version=VERSION,unassigned_before=int(gaps.sum()),unassigned_after=int(gaps.sum()),
        restored_pixels=0,restored_pieces=0,pieces=[],permission_pixels=int(permission.sum()),
        prediction_changed=False,anatomical_owner_verified=False,default_enabled=False,
        decisions_from_original_owners=True)
    if count>MAX_GAPS:
        return contexts,report|dict(reason='boundary_gap_resource_limit',gap_components=int(count))
    additions={}
    cross=ndimage.generate_binary_structure(2,1)
    for component,window in enumerate(ndimage.find_objects(labels),1):
        y,x=window
        outer=(slice(max(0,y.start-1),min(body.shape[0],y.stop+1)),
               slice(max(0,x.start-1),min(body.shape[1],x.stop+1)))
        gap=labels[outer]==component;rim=ndimage.binary_dilation(gap,structure=cross)&~gap
        local_coverage=coverage[outer];local_ids=ids[outer]
        adjacent=np.unique(local_ids[rim&(local_coverage==1)])
        row=dict(gap_component=component,pixels=int(gap.sum()),status='unassigned')
        if np.any(rim&(local_coverage>1)):row['reason']='adjacent_owner_overlap'
        elif len(adjacent)!=1:row['reason']='adjacent_owner_unavailable' if not len(adjacent) else 'adjacent_owner_ambiguous'
        else:
            index=int(adjacent[0]);context=contexts[index-1]
            if context.get('reject_reason') is not None:row['reason']='adjacent_owner_invalid'
            elif not np.any(rim&permission[outer]&(local_coverage==1)&(local_ids==index)):
                row['reason']='no_adjacent_owned_permission'
            else:
                if index not in additions:additions[index]=np.zeros(body.shape,bool)
                additions[index][outer]|=gap
                row.update(status='linked',candidate_id=context['candidate_id'],reason=None)
                report['restored_pixels']+=row['pixels'];report['restored_pieces']+=1
        report['pieces'].append(row)
    result=[]
    for index,context in enumerate(contexts,1):
        addition=additions.get(index)
        if addition is None:result.append(context);continue
        # Additions were unassigned BODY/permission pixels, never another owner.
        if np.any(addition&((coverage!=0)|~body|~permission)):
            raise RuntimeError('owner_boundary_repair_partition_failure')
        result.append(context|dict(body=context['body']|addition,native_owner_policy=VERSION,
            native_body_edge_pixels_restored=int(context.get('native_body_edge_pixels_restored',0))+int(addition.sum()),
            boundary_repair_pixels=int(addition.sum()),anatomical_owner_verified=False))
    report['unassigned_after']-=report['restored_pixels']
    return result,report
