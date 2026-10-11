import cv2, numpy as np

from scipy.signal import find_peaks

from highres_ridge_quality import orientation_field, RidgeQualityConfig

def estimate_ridge_pitch(gray,roi):
    if gray.dtype!=np.uint8 or gray.shape!=(512,512) or roi.shape!=gray.shape:raise ValueError('512 gray and matching ROI required')
    tangent,coherence=orientation_field(gray,RidgeQualityConfig(tensor_sigma=5))
    normal=tangent-np.pi/2;uu,vv=np.meshgrid(np.arange(-32,32,dtype=np.float32),np.arange(-12,12,dtype=np.float32));measurements=[]
    for cy in range(48,465,48):
        for cx in range(48,465,48):
            region=np.s_[cy-24:cy+24,cx-24:cx+24]
            if float(roi[region].mean())<.95 or float(coherence[region].mean())<.65:continue
            theta=.5*np.arctan2(float(np.mean(np.sin(2*normal[region]))),float(np.mean(np.cos(2*normal[region]))))
            mx=(cx+uu*np.cos(theta)-vv*np.sin(theta)).astype(np.float32);my=(cy+uu*np.sin(theta)+vv*np.cos(theta)).astype(np.float32)
            profile=cv2.remap(gray.astype(np.float32),mx,my,cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT_101).mean(axis=0)
            axis=np.arange(64);profile-=np.polyval(np.polyfit(axis,profile,1),axis);contrast=float(profile.std())
            if contrast<2:continue
            acf=np.array([np.dot(profile[:-lag],profile[lag:])/max(float(np.linalg.norm(profile[:-lag])*np.linalg.norm(profile[lag:])),1e-6) for lag in range(1,29)])
            peaks,_=find_peaks(acf,prominence=.15);peaks=[int(p) for p in peaks if 4<=p+1<=24 and acf[p]>=.25]
            if not peaks:continue
            # First credible periodic peak; independent of any matcher score.
            peak=peaks[0];lag=float(peak+1)
            if 0<peak<len(acf)-1:
                den=float(acf[peak-1]-2*acf[peak]+acf[peak+1])
                if abs(den)>1e-5:lag+=float(np.clip(.5*(acf[peak-1]-acf[peak+1])/den,-.5,.5))
            measurements.append(dict(x=cx,y=cy,pitch=lag,correlation=float(acf[peak]),coherence=float(coherence[region].mean()),profile_contrast=contrast))
    if len(measurements)<6:return dict(status='insufficient_periodic_patches',pitch=None,count=len(measurements),measurements=measurements,physical_dpi_known=False)
    pitches=np.array([m['pitch'] for m in measurements]);median=float(np.median(pitches));mad=float(np.median(np.abs(pitches-median)));inliers=pitches[np.abs(pitches-median)<=max(2,3*mad)]
    return dict(status='estimated',pitch=float(np.median(inliers)),count=len(measurements),inlier_count=len(inliers),pitch_mad=mad,measurements=measurements,physical_dpi_known=False,identity_matcher_selection_used=False)
