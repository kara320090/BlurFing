"""Opt-in body-owner-local allocation; frozen math and gates remain unchanged.

The virtual crop has its own identity and encoded coordinates. Full native RGB
is reconstructed only within the hash-bound learned component. Translation
does not change an observed native axis. Crop edges/rounded resize can change
numeric observations; equivalence to whole-photo resizing is not claimed.
"""
import hashlib,json,math
import numpy as np
import photo_learned_pad_pipeline_v1 as base
from photo_candidate_context_v1 import plan_candidate_scale
from photo_region_pipeline_v3 import render_candidate_region

VERSION='photo_learned_pad_pipeline_v2_body_local_experimental'
CONTEXT_HALO_NATIVE=2 # Four-tap cubic interpolation needs actual source neighbors.
CONTEXT_HALO_WORKING=2 # Preserve exterior body samples after downscaling.


def body_crop(rgb,native,owner,orientation,source_sha,working_scale=1.):
    if (not isinstance(rgb,np.ndarray) or rgb.dtype!=np.uint8 or rgb.ndim!=3 or rgb.shape[2]!=3 or
            native.shape!=rgb.shape[:2] or owner.shape!=native.shape or
            native.dtype!=np.bool_ or owner.dtype!=np.bool_ or not native.any() or
            np.any(native & ~owner)):
        raise ValueError('body_local_crop_contract')
    if type(orientation) is not int or orientation not in range(1,9):raise ValueError('body_local_exif_contract')
    if not np.isfinite(working_scale) or working_scale<=0:raise ValueError('body_local_scale_contract')
    halo=max(CONTEXT_HALO_NATIVE,math.ceil(CONTEXT_HALO_WORKING/working_scale))
    y,x=np.where(owner);height,width=owner.shape
    bbox=[max(0,int(x.min())-halo),max(0,int(y.min())-halo),
          min(width,int(x.max())+1+halo),min(height,int(y.max())+1+halo)];a,b,c,d=bbox
    crop_rgb=rgb[b:d,a:c].copy();crop_mask=native[b:d,a:c].copy();crop_body=owner[b:d,a:c].copy()
    if int(crop_body.sum())!=int(owner.sum()) or int(crop_mask.sum())!=int(native.sum()):raise ValueError('body_local_crop_loses_pixels')
    identity=dict(version=VERSION,parent_source_sha256=source_sha,parent_shape=list(native.shape),
        bbox_encoded_original=bbox,virtual_shape=list(crop_mask.shape),exif_orientation=orientation,
        virtual_RGB_sha256=base.pixel_hash(crop_rgb),virtual_body_sha256=base.pixel_hash(crop_body),
        virtual_mask_sha256=base.pixel_hash(crop_mask),coordinate_system='encoded_virtual_crop_pixels',
        context_halo_native=halo,context_halo_policy='max(2 native, ceil(2 working / normalization scale))',
        source_frame_clipped=bool(a==0 or b==0 or c==width or d==height),
        native_mapping='x_parent=x_crop+x0; y_parent=y_crop+y0',complete_owner_body_retained=True)
    virtual_sha=hashlib.sha256(json.dumps(identity,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return crop_rgb,crop_mask,crop_body,identity|dict(virtual_source_sha256=virtual_sha)


def prepare_scoped_region(rgb,gray,native,owner,orientation,source_sha,full_plan,association):
    local,mask,body,identity=body_crop(rgb,native,owner,orientation,source_sha,full_plan['working_scale'])
    plan=plan_candidate_scale(mask,full_plan['component']);plan['allocation_scope']='complete_observed_body_owner_bbox'
    geometry=dict(scope=identity,axis_native_yx=association['axis_native_yx'],reject_reason=plan['reject_reason'])
    if plan['status']!='planned':return None,geometry,plan,None
    # Integer translation preserves native directions. shared.prepare_region
    # applies EXIF and the ACTUAL rounded per-axis virtual-crop resize ratios.
    a,b,c,d=identity['bbox_encoded_original']
    artifact,details=base.shared.prepare_region(local,gray[b:d,a:c],mask,body,orientation,
        identity['virtual_source_sha256'],plan,association)
    geometry.update(details)
    if artifact is None:return None,geometry,plan,None
    roi=artifact['regions'][0]['roi'];roi.detector_name=VERSION;roi.detector_version=VERSION
    roi.validate(local,identity['virtual_source_sha256'])
    r0,r1,r2,r3=roi.bbox
    geometry['virtual_ROI_metadata']=roi.metadata()|dict(coordinate_system='encoded_virtual_crop_pixels',
        parent_source_sha256=source_sha,bbox_parent_encoded_original=[r0+a,r1+b,r2+a,r3+b],origin_parent_xy=[a,b])
    def render(axis):
        before_rgb=base.pixel_hash(local);before_mask=base.pixel_hash(mask);before_body=base.pixel_hash(body)
        candidate,report=render_candidate_region(local,artifact,axis)
        if (not isinstance(candidate,np.ndarray) or candidate.shape!=local.shape or candidate.dtype!=np.uint8 or
                not np.array_equal(candidate[~mask],local[~mask]) or base.pixel_hash(local)!=before_rgb or
                base.pixel_hash(mask)!=before_mask or base.pixel_hash(body)!=before_body):
            raise ValueError('body_local_renderer_output_contract')
        full=rgb.copy();area=full[b:d,a:c];area[mask]=candidate[mask]
        report['virtual_crop_provenance']=identity
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
