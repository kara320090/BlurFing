"""Fill the existing seed budget with spatial coverage within prediction pixels.

Keep V4 proposals first, then exclude their squares from the center-selection
domain and choose deterministic maximum-body-support centers in the remainder.
Observation squares can overlap; they are not independent evidence. Permission
pixels are unchanged. No source/matcher scores or human targets enter planning.
"""
import cv2,numpy as np
from photo_body_observation_seed_v1 import seeds,MAX_SEEDS


def observation_seeds(mask,body):
    result=seeds(mask,body)
    if len(result)>=MAX_SEEDS:return result
    available=mask.copy()
    def exclude(box):
        a,b,c,d=box;available[b:d,a:c]=False
    for row in result:exclude(row['box'])
    distance=cv2.distanceTransform(np.pad(body.astype(np.uint8),1),cv2.DIST_L2,5)[1:-1,1:-1]
    # Bound both successful proposals and invalid-geometry attempts.
    for attempt in range(MAX_SEEDS-len(result)):
        if not available.any():break
        values=np.where(available,distance,-1.);y,x=np.unravel_index(np.argmax(values),values.shape)
        half=int(distance[y,x]/np.sqrt(2)*.9)
        if half<16:break # Existing renderer requires a >=32px square ROI.
        a,b,c,d=int(x-half),int(y-half),int(x+half),int(y+half)
        if not (0<=a<c<=mask.shape[1] and 0<=b<d<=mask.shape[0]):break
        exclude([a,b,c,d])
        if not body[b:d,a:c].all():continue
        result.append(dict(box=[a,b,c,d],center_yx=[int(y),int(x)],side=c-a,
            fully_inside_observed_body=True,proposal_policy='spatial_coverage_within_predicted_pixels_v1',
            observation_squares_may_overlap=True,permission_mask_expanded=False))
    return result
