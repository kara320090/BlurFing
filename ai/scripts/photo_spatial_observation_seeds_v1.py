"""Geometry-only extra observation positions within the same permission.

Keep the complete V8 seed prefix. Add nearest eligible centers to a fixed 3x3
box grid, farthest targets first, under the existing eight-seed resource budget.
No RGB, target annotations, pitch or renderer results select positions.
"""
import cv2
import numpy as np
from photo_body_observation_seed_v1 import seeds as original_seeds,MAX_SEEDS

VERSION='same_permission_spatial_observation_v1_experimental'


def proposals(mask,body,*unused):
    selected=original_seeds(mask,body)
    if len(selected)>=MAX_SEEDS:return selected
    distances=cv2.distanceTransform(np.pad(body.astype(np.uint8),1),cv2.DIST_L2,5)[1:-1,1:-1]
    # This is the original half>=4 eligibility formula, not a quality gate.
    eligible=mask & (distances*(.9/np.sqrt(2))>=4)
    if not eligible.any():return selected
    yy,xx=np.where(mask);lo_y,hi_y=int(yy.min()),int(yy.max());lo_x,hi_x=int(xx.min()),int(xx.max());del yy,xx
    center=selected[0]['center_yx'] if selected else [(lo_y+hi_y)/2,(lo_x+hi_x)/2]
    targets=[(lo_y+(hi_y-lo_y)*fy,lo_x+(hi_x-lo_x)*fx) for fy in [.25,.5,.75] for fx in [.25,.5,.75]]
    targets.sort(key=lambda p:(-((p[0]-center[0])**2+(p[1]-center[1])**2),p[0],p[1]))
    rows=np.arange(mask.shape[0],dtype=np.float32)[:,None];cols=np.arange(mask.shape[1],dtype=np.float32)[None,:]
    seen={tuple(row['box']) for row in selected}
    for y0,x0 in targets:
        squared=(rows-y0)**2+(cols-x0)**2;squared[~eligible]=np.inf
        y,x=np.unravel_index(np.argmin(squared),squared.shape);half=int(distances[y,x]/np.sqrt(2)*.9)
        if half<4:continue
        box=[int(x-half),int(y-half),int(x+half),int(y+half)];a,b,c,d=box
        if tuple(box) in seen or not (0<=a<c<=mask.shape[1] and 0<=b<d<=mask.shape[0]) or not body[b:d,a:c].all():continue
        selected.append(dict(box=box,center_yx=[int(y),int(x)],side=c-a,fragment='same_permission',
            fully_inside_observed_body=True,proposal_policy=VERSION,spatial_target_yx=[y0,x0]))
        seen.add(tuple(box))
        if len(selected)>=MAX_SEEDS:break
    return selected
