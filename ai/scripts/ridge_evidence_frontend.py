"""Shared ridge evidence: image-only engineering gate, not matcher/privacy proof."""
import cv2
import numpy as np


def ridge_evidence(gray,support=None,max_side=512):
    if gray.ndim!=2 or gray.dtype!=np.uint8:raise ValueError('uint8 grayscale required')
    h,w=gray.shape;ratio=min(1.,max_side/max(h,w));small=cv2.resize(gray,(max(1,round(w*ratio)),max(1,round(h*ratio))),interpolation=cv2.INTER_AREA);allowed=np.ones(small.shape,bool) if support is None else cv2.resize(support.astype(np.uint8),(small.shape[1],small.shape[0]),interpolation=cv2.INTER_NEAREST)>0
    g=small.astype(np.float32);gx=cv2.Sobel(g,cv2.CV_32F,1,0);gy=cv2.Sobel(g,cv2.CV_32F,0,1);xx=cv2.GaussianBlur(gx*gx,(0,0),3);yy=cv2.GaussianBlur(gy*gy,(0,0),3);xy=cv2.GaussianBlur(gx*gy,(0,0),3);coherence=np.hypot(xx-yy,2*xy)/(xx+yy+1e-6);angle=.5*np.arctan2(2*xy,xx-yy)
    mask=np.zeros(small.shape,bool);measurements=[];eligible=0;window=np.outer(np.hanning(32),np.hanning(32));f=np.fft.fftfreq(32);radius=np.hypot(f[:,None],f[None,:]);band=(radius>=.065)&(radius<=.30)
    for y in range(0,small.shape[0]-31,16):
        for x in range(0,small.shape[1]-31,16):
            sl=np.s_[y:y+32,x:x+32]
            if allowed[sl].mean()<.8:continue
            eligible+=1;patch=g[sl];contrast=float(patch.std());co=float(np.median(coherence[sl]))
            power=np.abs(np.fft.fft2((patch-patch.mean())*window))**2;total=float(power.sum());idx=np.unravel_index(np.argmax(power*band),power.shape);frequency=float(radius[idx]);radial=float(power[(np.abs(radius-frequency)<.025)&band].sum()/max(total,1e-6))
            valid=contrast>=8 and co>=.45 and radial>=.40 and total>0
            if valid:mask[sl]=True;measurements.append(dict(x=x,y=y,pitch=1/frequency/ratio,coherence=co,radial_concentration=radial,orientation=float(np.median(angle[sl]))))
    mask&=allowed
    native=cv2.resize(mask.astype(np.uint8),(w,h),interpolation=cv2.INTER_NEAREST)>0
    if support is not None:native&=support
    fraction=len(measurements)/max(1,eligible)
    quality=dict(credible_windows=len(measurements),eligible_windows=eligible,credible_fraction=fraction,pitch_native=float(np.median([r['pitch'] for r in measurements])) if measurements else None,orientation=float(np.median([r['orientation'] for r in measurements])) if measurements else None,working_ratio=ratio,status='ridge_observed' if len(measurements)>=4 else 'ridge_evidence_insufficient',confidence_semantics='credible-window fraction, not probability',physical_DPI_known=False)
    return native,quality


def scanner_ridge_evidence(gray):
    attempts=[];best=None
    for side in [512,1024,2048]:
        mask,q=ridge_evidence(gray,max_side=side);attempts.append(q.copy())
        if best is None or q['credible_fraction']>best[1]['credible_fraction']:best=(mask,q)
        if q['credible_windows']>=8 and q['credible_fraction']>=.10:break
    best[1]['resolution_attempts']=attempts
    return best
