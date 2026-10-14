"""Opt-in shared native observation anchor and actual-return RGB validation.

Width normalization and seed observation use the SAME predicted native pixel.
The final native RGB is reprojected into the original working geometry and
must satisfy the existing structure gate again. No baseline threshold/math
changes, seed search using matcher outcomes, or permission-mask expansion.
"""
from photo_returned_rgb_structure_v1 import returned_structure_check
from pathlib import Path
import cv2
import numpy as np
import photo_learned_pad_pipeline_v1 as base
import photo_region_pipeline_v1 as shared
from photo_learned_pad_pipeline_v3 import prepare_scoped_region as prepare_body_scale
from photo_owner_partition_v1 import partition
from photo_body_observation_seed_v1 import seeds,prepare_region as prepare_observed_region
from photo_native_body_scale_v1 import observe_width
from contactless_finger_width_body_v1 import estimate_finger_width_body
from photo_native_owner_context_v1 import restore_contexts

VERSION='photo_learned_pad_pipeline_v5_shared_anchor_returned_RGB_experimental'


def orient_point(point_yx,shape,orientation):
    y,x=point_yx;h,w=shape
    return {1:(y,x),2:(y,w-1-x),3:(h-1-y,w-1-x),4:(h-1-y,x),
            5:(x,y),6:(x,h-1-y),7:(w-1-x,h-1-y),8:(w-1-x,y)}[orientation]


def pinned_proposal(mask,body,native_shape,orientation,working_shape,association):
    source=association['normalization_anchor_local_yx']
    point=np.array(orient_point(source,native_shape,orientation),np.float64)
    upright_shape=native_shape if orientation<5 else native_shape[::-1]
    center=np.rint((point+.5)*np.array(working_shape)/upright_shape-.5).astype(int)
    y,x=center
    if not (0<=y<mask.shape[0] and 0<=x<mask.shape[1] and mask[y,x] and body[y,x]):return []
    # Same source measurement site after exact EXIF and actual rounded resize.
    distances=cv2.distanceTransform(np.pad(body.astype(np.uint8),1),cv2.DIST_L2,5)[1:-1,1:-1]
    half=int(distances[y,x]/np.sqrt(2)*.9)
    a,b,c,d=int(x-half),int(y-half),int(x+half),int(y+half)
    if half<16 or not (0<=a<c<=mask.shape[1] and 0<=b<d<=mask.shape[0]) or not body[b:d,a:c].all():return []
    return [dict(box=[a,b,c,d],center_yx=[int(y),int(x)],side=c-a,fully_inside_observed_body=True,
                 native_anchor_local_yx=source,anchor_policy='same native predicted pixel for width, pitch and feature ROI')]


def prepare_scoped_region(rgb,gray,native,owner,orientation,source_sha,full_plan,association):
    proposals=seeds(native,owner)
    if not proposals:
        return None,dict(reject_reason='body_supported_seed_unavailable'),full_plan|dict(status='rejected',reject_reason='body_supported_seed_unavailable'),None
    attempts=[];last=None
    # The same fixed observation budget as V4, but EVERY site gets its own
    # width normalization. Select using pre-render RGB/geometry only. Never
    # try another site after seeing generated features or matcher results.
    for proposal in proposals:
        anchor=proposal['center_yx']
        def observer(mask,body,axis):return observe_width(mask,body,axis,anchor_yx=anchor)
        def preparer(*args):return prepare_observed_region(*args,_proposals=pinned_proposal,_width_preflight=True)
        last=prepare_body_scale(rgb,gray,native,owner,orientation,source_sha,full_plan,association,
            _preparer=preparer,_version=VERSION,_observer=observer,_postprocess=returned_structure_check)
        artifact,geometry,plan,render=last
        attempts.append(dict(native_seed=proposal,geometry=geometry,scale_plan=plan))
        if artifact is not None:
            return artifact,geometry|dict(native_observation_attempts=attempts,seed_selection_uses_rendered_features=False),plan,render
    artifact,geometry,plan,render=last
    return artifact,geometry|dict(native_observation_attempts=attempts,seed_selection_uses_rendered_features=False),plan,render


def evaluate_learned_mask(source,mask,expected_pixel_sha256,*,detect_only=False):
    return base.evaluate_learned_mask(source,mask,expected_pixel_sha256,detect_only=detect_only,
        _scope_adapter=prepare_scoped_region,_version=VERSION,_candidate_builder=partition,_context_adapter=restore_contexts)


def protect_bundle(folder,root,output,detect_only=False):
    return base.protect_bundle(folder,root,output,detect_only,_mask_evaluator=evaluate_learned_mask,_version=VERSION)


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--model',type=Path,required=True)
    p.add_argument('--inputs',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--detect-only',action='store_true');a=p.parse_args()
    protect_bundle(a.model,a.inputs,a.output,a.detect_only)
