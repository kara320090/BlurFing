"""Versioned memory-safe semantic/coarse to native CanonicalFingerprintROI adapter.

No GT, refinement, parameter search or production approval is used.
"""
import hashlib,json
from pathlib import Path
import cv2
import numpy as np
from PIL import Image,ImageOps
from scipy import ndimage
from finger_body_distal_estimator import estimate
from evaluate_finger_body_distal import read_binary
from canonical_fingerprint_roi import canonical_roi
from protect_visible_pad_checked_v2 import observed_seed_pitch
from ridge_evidence_frontend import ridge_evidence
from photo_resize_safety_v1 import validate_resize,ResizeSafetyError


def orient(array,orientation,inverse=False):
    forward={2:Image.Transpose.FLIP_LEFT_RIGHT,3:Image.Transpose.ROTATE_180,4:Image.Transpose.FLIP_TOP_BOTTOM,5:Image.Transpose.TRANSPOSE,6:Image.Transpose.ROTATE_270,7:Image.Transpose.TRANSVERSE,8:Image.Transpose.ROTATE_90}
    backward=forward|{6:Image.Transpose.ROTATE_90,8:Image.Transpose.ROTATE_270}
    im=Image.fromarray(array);method=(backward if inverse else forward).get(orientation)
    return np.asarray(im.transpose(method) if method else im).copy()


def seed_square(mask):
    distance=cv2.distanceTransform(np.pad(mask.astype(np.uint8),1),cv2.DIST_L2,5)[1:-1,1:-1];y,x=np.unravel_index(np.argmax(distance),distance.shape);half=int(distance[y,x]/np.sqrt(2)*.9)
    if half<4:raise ValueError('coarse_pad_too_small_for_seed')
    box=[int(x-half),int(y-half),int(x+half),int(y+half)]
    if not mask[box[1]:box[3],box[0]:box[2]].all():raise ValueError('seed_not_inside_pad')
    return box


def square_scope(mask):
    y,x=np.where(mask);h,w=mask.shape;side=max(int(x.max()-x.min()+1),int(y.max()-y.min()+1));a=max(0,min(int((x.min()+x.max()+1-side)//2),max(0,w-side)));b=max(0,min(int((y.min()+y.max()+1-side)//2),max(0,h-side)))
    return [a,b,a+side,b+side],dict(right=max(0,a+side-w),bottom=max(0,b+side-h))


def validate_semantic_policy(identity):
    """Accept only the encoded-pixel policy produced by the body worker."""
    if not isinstance(identity,dict):raise ValueError('invalid_semantics_identity')
    classes=identity.get('body_classes')
    if identity.get('coordinate_system')!='encoded_original_pixels':raise ValueError('semantic_coordinate_contract_mismatch')
    if not isinstance(classes,list) or any(type(v) is not int for v in classes) or classes!=[1,2]:raise ValueError('semantic_class_contract_mismatch')
    if type(identity.get('tip_class')) is not int or identity['tip_class']!=2:raise ValueError('semantic_class_contract_mismatch')
    if type(identity.get('minimum_votes')) is not int or identity['minimum_votes']!=2:raise ValueError('semantic_consensus_contract_mismatch')


def adapt(source,semantics):
    source=Path(source);sha=hashlib.sha256(source.read_bytes()).hexdigest();identity=json.loads((Path(semantics)/'semantics.json').read_text())
    validate_semantic_policy(identity)
    with Image.open(source) as im:rgb=np.asarray(im.convert('RGB')).copy();orientation=im.getexif().get(274,1)
    if identity['source_sha256']!=sha or (identity['image_height'],identity['image_width'])!=rgb.shape[:2]:raise ValueError('source_semantics_contract_mismatch')
    body=read_binary(Path(semantics)/'body.png',rgb.shape[:2],identity['body_sha256']);tip=read_binary(Path(semantics)/'tip.png',rgb.shape[:2],identity['tip_sha256']);result=estimate(body,tip);labels,n=ndimage.label(result['mask']);upright=orient(rgb,orientation);accepted=[];rejected=[]
    # Match the existing structure check's 400px width normalization using only mask geometry.
    diameters=[2*float(cv2.distanceTransform((labels==i).astype(np.uint8),cv2.DIST_L2,5).max()) for i in range(1,n+1)]
    scale=400/float(np.median(diameters)) if diameters else 1.0
    try:
        working_shape,resize_audit=validate_resize(upright.shape[0],upright.shape[1],scale)
    except ResizeSafetyError as error:
        rejected=[dict(component=i,reject_reason=error.reason) for i in range(1,n+1)]
        return rgb,dict(source_sha256=sha,exif_orientation=orientation,working_shape=None,working_scale=scale,regions=[],rejected=rejected,detected_pad_count=n,body=body,coarse_mask=result['mask'],adapter_version='photo_coarse_adapter_v2',resize_audit=error.audit,PHOTO_DETECTOR_APPROVED=False,PHOTO_PROTECTION_PRODUCTION_READY=False)
    upright=cv2.resize(upright,(working_shape[1],working_shape[0]),interpolation=cv2.INTER_AREA if scale<1 else cv2.INTER_CUBIC)
    for i in range(1,n+1):
        mask=labels==i;working_mask=cv2.resize(orient(mask.astype(np.uint8),orientation),(working_shape[1],working_shape[0]),interpolation=cv2.INTER_NEAREST)>0
        try:seed=seed_square(working_mask);pitch,measurement,_=observed_seed_pitch(upright,seed)
        except ValueError as e:rejected.append(dict(component=i,reject_reason=str(e)));continue
        if pitch is None:rejected.append(dict(component=i,reject_reason='pitch_unobserved',pitch_measurement=measurement));continue
        if not 2<=pitch<=50:rejected.append(dict(component=i,reject_reason='renderer_pitch_out_of_range',observed_pitch=pitch));continue
        y,x=np.where(mask);a,b,c,d=int(x.min()),int(y.min()),int(x.max())+1,int(y.max())+1;gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY);_,quality=ridge_evidence(gray[b:d,a:c],mask[b:d,a:c]);quality|=dict(pitch_native=float(pitch/scale),pitch_source='frozen_observed_seed_pitch',confidence_semantics='ridge credible-window fraction; geometric candidate not production-approved')
        roi=canonical_roi(gray,mask,sha,'PHOTO',quality,'COLFISPOOF_finger_body_distal_experimental');roi.validate(rgb,sha)
        if (mask&~body).any():raise ValueError('pad_outside_body')
        scope,padding=square_scope(working_mask);accepted.append(dict(roi=roi,working_seed=seed,working_scope=scope,padding=padding,pitch_measurement=measurement,component=i))
    # Bound the shared square-padding allocation too; no crop/scale substitution.
    try:
        _,padding_audit=validate_resize(working_shape[0]+max([e['padding']['bottom'] for e in accepted]+[0]),working_shape[1]+max([e['padding']['right'] for e in accepted]+[0]),1)
        resize_audit['square_padding_allocation']=padding_audit
    except ResizeSafetyError as error:
        rejected += [dict(component=e['component'],reject_reason=error.reason) for e in accepted]
        return rgb,dict(source_sha256=sha,exif_orientation=orientation,working_shape=None,working_scale=scale,regions=[],rejected=rejected,detected_pad_count=n,body=body,coarse_mask=result['mask'],adapter_version='photo_coarse_adapter_v2',resize_audit=error.audit,PHOTO_DETECTOR_APPROVED=False,PHOTO_PROTECTION_PRODUCTION_READY=False)
    assert hashlib.sha256(source.read_bytes()).hexdigest()==sha
    return rgb,dict(source_sha256=sha,exif_orientation=orientation,working_shape=working_shape,working_scale=scale,adapter_version='photo_coarse_adapter_v2',resize_audit=resize_audit,source_rgb_sha256=hashlib.sha256(rgb.tobytes()).hexdigest(),regions=accepted,rejected=rejected,detected_pad_count=n,body=body,coarse_mask=result['mask'],PHOTO_DETECTOR_APPROVED=False,PHOTO_PROTECTION_PRODUCTION_READY=False)
