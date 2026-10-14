"""OS-independent native encoded coordinate contract. Arrays are private."""
from dataclasses import dataclass
import hashlib
import re
import cv2
import numpy as np

@dataclass
class CanonicalFingerprintROI:
    source_sha256:str
    source_type:str
    bbox:list
    binary_mask:np.ndarray
    normalized_roi:np.ndarray
    ridge_quality:dict
    orientation:float|None
    pitch:float|None
    confidence:float
    reject_reason:str|None
    detector_name:str
    detector_version:str='frontend_v1_experimental'
    def validate(self,rgb,source_sha):
        if not re.fullmatch('[0-9a-f]{64}',self.source_sha256) or not np.isfinite(self.confidence) or not 0<=self.confidence<=1:raise ValueError('invalid_source_hash_or_confidence')
        if self.source_sha256!=source_sha or self.source_type not in ['PHOTO','FINGERPRINT_IMAGE']:raise ValueError('source_contract_mismatch')
        if self.binary_mask.shape!=rgb.shape[:2] or self.binary_mask.dtype!=np.uint8 or not np.isin(self.binary_mask,[0,255]).all():raise ValueError('mask_contract_mismatch')
        h,w=rgb.shape[:2];a,b,c,d=self.bbox
        if not(0<=a<c<=w and 0<=b<d<=h) or not self.binary_mask.any():raise ValueError('empty_or_outside_ROI')
        expected=np.zeros((h,w),bool);expected[b:d,a:c]=True
        if (self.binary_mask[~expected]!=0).any():raise ValueError('mask_outside_bbox')
        if self.normalized_roi.shape!=(512,512) or self.normalized_roi.dtype!=np.uint8:raise ValueError('normalized_ROI_contract')
        if self.pitch is None or not np.isfinite(self.pitch) or self.pitch<=0:raise ValueError('invalid_pitch')
    def metadata(self):
        a,b,c,d=self.bbox;scale=512/max(c-a,d-b);rw=max(1,round((c-a)*scale));rh=max(1,round((d-b)*scale))
        return {k:v for k,v in self.__dict__.items() if k not in ['binary_mask','normalized_roi']}|dict(coordinate_system='encoded_original_pixels',normalization=dict(scale=scale,canvas_size=512,padding_xy=[(512-rw)//2,(512-rh)//2],resized_shape=[rh,rw]),mask_pixel_sha256=hashlib.sha256(self.binary_mask.tobytes()).hexdigest())


def canonical_roi(gray,mask,sha,kind,quality,name):
    ys,xs=np.where(mask);box=[int(xs.min()),int(ys.min()),int(xs.max())+1,int(ys.max())+1];a,b,c,d=box;crop=gray[b:d,a:c];ratio=512/max(c-a,d-b);small=cv2.resize(crop,(max(1,round((c-a)*ratio)),max(1,round((d-b)*ratio))),interpolation=cv2.INTER_AREA if ratio<1 else cv2.INTER_CUBIC);normalized=np.full((512,512),255,np.uint8);y=(512-small.shape[0])//2;x=(512-small.shape[1])//2;normalized[y:y+small.shape[0],x:x+small.shape[1]]=small
    return CanonicalFingerprintROI(sha,kind,box,mask.astype(np.uint8)*255,normalized,quality,quality.get('orientation'),quality.get('pitch_native'),quality['credible_fraction'],None,name)
