"""Append larger same-body windows without changing earlier observations.

The V9 positions and complete prefix remain intact. At each existing position,
append the largest even axis-aligned square entirely inside the same observed
body/raster, then a geometric midpoint size. RGB, GT and observed pitch do not
select windows. At most 24 sequential observations are possible.
"""
import math
from photo_spatial_observation_seeds_v1 import proposals as spatial_proposals

VERSION='same_permission_multiscale_observation_v1_experimental'
MAX_SEEDS=24


def proposals(mask,body,*unused):
    prefix=spatial_proposals(mask,body)
    selected=list(prefix);seen={tuple(row['box']) for row in prefix};extensions=[]
    for row in prefix:
        y,x=row['center_yx'];base=row['side']//2
        low=base;high=min(x,y,body.shape[1]-x,body.shape[0]-y)
        # Containment is monotone for concentric squares; search uses only
        # views of the already bounded body, with no larger image allocation.
        while low<high:
            half=(low+high+1)//2
            if body[y-half:y+half,x-half:x+half].all():low=half
            else:high=half-1
        extensions.append((row,low,math.isqrt(base*low)))
    for index in [1,2]:
        for row,*sizes in extensions:
            half=sizes[index-1];y,x=row['center_yx'];box=[x-half,y-half,x+half,y+half]
            if half<=row['side']//2 or tuple(box) in seen:continue
            selected.append(dict(box=box,center_yx=[y,x],side=2*half,
                fragment='same_permission',fully_inside_observed_body=True,
                proposal_policy=VERSION,scale_parent_box=row['box'],
                scale_rule='largest_contained_square' if index==1 else 'geometric_midpoint'))
            seen.add(tuple(box))
    if len(selected)>MAX_SEEDS:raise ValueError('multiscale_observation_budget_exceeded')
    return selected
