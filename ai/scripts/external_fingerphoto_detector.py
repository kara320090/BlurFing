"""Landmark-prompted SAM primary path; no automatic mask generator or GT.

COLFISPOOF is blocked until upstream code and licensing can be verified. No
third-party code is vendored. Landmark and SAM runtimes are optional injections.
"""
import cv2
import numpy as np
from PIL import Image
from ridge_evidence_frontend import ridge_evidence
from canonical_fingerprint_roi import canonical_roi

class PhotoRuntimeUnavailable(RuntimeError):pass


def hand_prompts(landmarks,shape):
    h,w=shape;points=np.asarray(landmarks,float)
    if points.shape!=(21,2) or not np.isfinite(points).all() or np.any(points<0) or np.any(points>1):raise ValueError('invalid_hand_landmarks')
    xy=points*np.array([w-1,h-1]);result=[]
    for tip_id,dip_id,pip_id in [(4,3,2),(8,7,6),(12,11,10),(16,15,14),(20,19,18)]:
        tip,dip,pip=xy[[tip_id,dip_id,pip_id]];length=float(np.linalg.norm(tip-dip))
        if length<6:continue
        axis=(tip-dip)/length;normal=np.array([-axis[1],axis[0]]);width=length*.9
        corners=np.array([tip+axis*.3*length+normal*width,tip+axis*.3*length-normal*width,pip-axis*.2*length+normal*width,pip-axis*.2*length-normal*width]);a,b=corners.min(axis=0);c,d=corners.max(axis=0);box=np.array([max(0,a),max(0,b),min(w-1,c),min(h-1,d)])
        positive=.7*tip+.3*dip;negative=[xy[0]]+[xy[j] for j in [3,7,11,15,19] if j!=dip_id];prompt_points=np.array([positive]+negative);labels=np.array([1]+[0]*len(negative))
        result.append(dict(finger_id=tip_id,tip=tip.tolist(),DIP=dip.tolist(),PIP=pip.tolist(),axis=axis.tolist(),box=box.tolist(),points=prompt_points,labels=labels))
    return result

class MediaPipeSAMRuntime:
    def __init__(self,hand_model,sam_checkpoint):
        from pathlib import Path
        if not Path(hand_model).is_file() or not Path(sam_checkpoint).is_file():raise PhotoRuntimeUnavailable('hand_or_SAM_model_missing')
        try:
            import mediapipe as mp
            import torch
            from segment_anything import sam_model_registry,SamPredictor
        except ImportError as e:raise PhotoRuntimeUnavailable('mediapipe_or_SAM_dependency_missing') from e
        self.mp=mp;options=mp.tasks.vision.HandLandmarkerOptions(base_options=mp.tasks.BaseOptions(model_asset_path=str(hand_model)),running_mode=mp.tasks.vision.RunningMode.IMAGE,num_hands=2)
        self.hand=mp.tasks.vision.HandLandmarker.create_from_options(options)
        try:self.sam=SamPredictor(sam_model_registry['vit_b'](checkpoint=str(sam_checkpoint)).eval().to('cuda' if torch.cuda.is_available() else 'cpu'))
        except Exception:self.hand.close();raise
    def landmarks(self,rgb):return [[(v.x,v.y) for v in hand] for hand in self.hand.detect(self.mp.Image(image_format=self.mp.ImageFormat.SRGB,data=rgb)).hand_landmarks]
    def set_image(self,rgb):self.sam.set_image(rgb)
    def predict(self,prompt):
        masks,scores,_=self.sam.predict(point_coords=prompt['points'],point_labels=prompt['labels'],box=np.array(prompt['box']),multimask_output=True)
        return masks[int(np.argmax(scores))]
    def close(self):self.hand.close()


def detect_photo(rgb,sha,orientation=1,runtime=None):
    if runtime is None:return [],dict(status='blocked',reject_reason='photo_primary_runtime_unavailable',COLFISPOOF='code_license_not_verified',legacy_available=True)
    to_upright={2:Image.Transpose.FLIP_LEFT_RIGHT,3:Image.Transpose.ROTATE_180,4:Image.Transpose.FLIP_TOP_BOTTOM,5:Image.Transpose.TRANSPOSE,6:Image.Transpose.ROTATE_270,7:Image.Transpose.TRANSVERSE,8:Image.Transpose.ROTATE_90};inverse={**to_upright,6:Image.Transpose.ROTATE_90,8:Image.Transpose.ROTATE_270};im=Image.fromarray(rgb)
    if orientation in to_upright:im=im.transpose(to_upright[orientation])
    upright=np.array(im);hands=runtime.landmarks(upright);prompts=[r for h in hands for r in hand_prompts(h,upright.shape[:2])]
    if not prompts:return [],dict(status='rejected',reject_reason='no_hand_landmarks',legacy_available=True)
    runtime.set_image(upright);regions=[];rejected=[];gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
    for prompt in prompts:
        finger=np.asarray(runtime.predict(prompt),bool)
        if finger.shape!=upright.shape[:2]:raise ValueError('SAM_shape_mismatch')
        # Anatomy restricts the search; image-observed ridge tiles authorize it.
        a,b,c,d=np.rint(prompt['box']).astype(int);local=np.zeros_like(finger);local[b:d+1,a:c+1]=True;finger&=local
        # The learned DIP/IP anchors distal anatomy; ridge evidence still gates it.
        yy,xx=np.ogrid[b:d+1,a:c+1];dip=np.asarray(prompt['DIP']);axis=np.asarray(prompt['axis']);finger[b:d+1,a:c+1]&=((xx-dip[0])*axis[0]+(yy-dip[1])*axis[1]>=0)
        gim=Image.fromarray(finger.astype(np.uint8)*255)
        if orientation in inverse:gim=gim.transpose(inverse[orientation])
        native=np.asarray(gim)>0;ys,xs=np.where(native)
        if not len(xs):rejected.append('SAM_empty_finger');continue
        x0,x1,y0,y1=int(xs.min()),int(xs.max())+1,int(ys.min()),int(ys.max())+1
        local_ridges,q=ridge_evidence(gray[y0:y1,x0:x1],native[y0:y1,x0:x1]);ridge=np.zeros(native.shape,bool);ridge[y0:y1,x0:x1]=local_ridges
        if q['status']!='ridge_observed':rejected.append('ridge_evidence_insufficient');continue
        n,labels,stats,centers=cv2.connectedComponentsWithStats(ridge.astype(np.uint8),connectivity=4)
        if n<=1:rejected.append('ridge_foreground_empty');continue
        # Positive anatomical point must overlap or be adjacent to ridge support.
        marker=np.zeros(upright.shape[:2],np.uint8);px,py=prompt['points'][0];marker[int(round(py)),int(round(px))]=255;mi=Image.fromarray(marker)
        if orientation in inverse:mi=mi.transpose(inverse[orientation])
        yy,xx=np.where(np.asarray(mi)>0);point=np.array([xx[0],yy[0]]);nearest=1+int(np.argmin(np.linalg.norm(centers[1:]-point,axis=1)));mask=labels==nearest;distance=cv2.distanceTransform((~mask).astype(np.uint8),cv2.DIST_L2,5)
        if distance[point[1],point[0]]>2*q['pitch_native']:rejected.append('ridges_not_associated_with_distal_landmark');continue
        if any((mask&(r.binary_mask>0)).any() for r in regions):rejected.append('duplicate_finger_region');continue
        roi=canonical_roi(gray,mask,sha,'PHOTO',q,'MediaPipe_landmark_prompted_SAM_ridges');roi.validate(rgb,sha);regions.append(roi)
    return regions,dict(status='review_candidates_only',reject_reason=None if regions else 'no_valid_distal_ridge_region',hands=len(hands),anatomical_prompts=len(prompts),rejected=rejected,approved_for_use=False)
