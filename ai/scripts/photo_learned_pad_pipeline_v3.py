"""Opt-in native body-width normalization and unchanged frozen quality gates."""
import hashlib,json
import numpy as np
from photo_resize_safety_v1 import validate_resize,ResizeSafetyError
from photo_native_body_scale_v1 import observe_width
import photo_learned_pad_pipeline_v1 as base
from photo_learned_pad_pipeline_v2 import body_crop
from photo_region_pipeline_v3 import render_candidate_region
from photo_region_scale_plan_v1 import NORMALIZED_WIDTH

VERSION='photo_learned_pad_pipeline_v3_native_body_scale_experimental'


def prepare_scoped_region(rgb,gray,native,owner,orientation,source_sha,full_plan,association,*,_preparer=None,_version=VERSION,_observer=None,_postprocess=None):
    observation=(_observer or observe_width)(native,owner,association['axis_native_yx'])
    scale=NORMALIZED_WIDTH/observation['observed_native_body_width']
    plan=dict(component=full_plan['component'],working_scale=scale,normalization=observation,
              mask_pixels=int(native.sum()),scale_policy='observed_native_body_width',target_working_body_width=NORMALIZED_WIDTH,
              component_filtering=False,allocation_scope='complete_observed_body_owner_bbox')
    geometry=dict(normalization=observation,axis_native_yx=association['axis_native_yx'])
    if observation['boundary_unobserved']:
        reason='native_body_width_boundary_unobserved'
        return None,geometry|dict(reject_reason=reason),plan|dict(status='rejected',reject_reason=reason),None
    local,mask,body,identity=body_crop(rgb,native,owner,orientation,source_sha,scale)
    identity.update(version=_version,normalization=observation)
    identity.pop('virtual_source_sha256');identity['virtual_source_sha256']=hashlib.sha256(json.dumps(identity,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    geometry['scope']=identity
    try:
        shape,audit=validate_resize(*mask.shape,scale)
        plan.update(status='planned',reject_reason=None,working_shape=list(shape),resize_audit=audit)
    except ResizeSafetyError as error:
        reason=error.reason;plan.update(status='rejected',reject_reason=reason,working_shape=None,resize_audit=error.audit)
        return None,geometry|dict(reject_reason=reason),plan,None
    a,b,c,d=identity['bbox_encoded_original']
    local_association=association|dict(normalization_anchor_local_yx=[observation['anchor_native_yx'][0]-b,observation['anchor_native_yx'][1]-a])
    artifact,details=(_preparer or base.shared.prepare_region)(local,gray[b:d,a:c],mask,body,orientation,
        identity['virtual_source_sha256'],plan,local_association)
    geometry.update(details)
    if artifact is None:return None,geometry,plan,None
    roi=artifact['regions'][0]['roi'];roi.detector_name=_version;roi.detector_version=_version;roi.validate(local,identity['virtual_source_sha256'])
    r0,r1,r2,r3=roi.bbox
    geometry['virtual_ROI_metadata']=roi.metadata()|dict(coordinate_system='encoded_virtual_crop_pixels',
        parent_source_sha256=source_sha,bbox_parent_encoded_original=[r0+a,r1+b,r2+a,r3+b],origin_parent_xy=[a,b])
    def render(axis):
        before_rgb=base.pixel_hash(local);before_mask=base.pixel_hash(mask);before_body=base.pixel_hash(body)
        candidate,report=render_candidate_region(local,artifact,axis)
        if (not isinstance(candidate,np.ndarray) or candidate.shape!=local.shape or candidate.dtype!=np.uint8 or
                not np.array_equal(candidate[~mask],local[~mask])):
            raise ValueError('body_local_renderer_output_contract')
        if _postprocess is not None:candidate,report=_postprocess(local,candidate,artifact,axis,report)
        if (not isinstance(candidate,np.ndarray) or candidate.shape!=local.shape or candidate.dtype!=np.uint8 or
                not np.array_equal(candidate[~mask],local[~mask]) or base.pixel_hash(local)!=before_rgb or
                base.pixel_hash(mask)!=before_mask or base.pixel_hash(body)!=before_body):
            raise ValueError('body_local_renderer_output_contract')
        full=rgb.copy();area=full[b:d,a:c];area[mask]=candidate[mask];report['virtual_crop_provenance']=identity
        return full,report
    return artifact,geometry,plan,render


def evaluate_learned_mask(source,mask,expected_pixel_sha256,*,detect_only=False):
    return base.evaluate_learned_mask(source,mask,expected_pixel_sha256,detect_only=detect_only,
                                     _scope_adapter=prepare_scoped_region,_version=VERSION)


def protect_bundle(folder,root,output,detect_only=False):
    return base.protect_bundle(folder,root,output,detect_only,_mask_evaluator=evaluate_learned_mask,_version=VERSION)


if __name__=='__main__':
    import argparse
    from pathlib import Path
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--model',type=Path,required=True)
    p.add_argument('--inputs',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--detect-only',action='store_true');a=p.parse_args()
    protect_bundle(a.model,a.inputs,a.output,a.detect_only)
