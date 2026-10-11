from __future__ import annotations

import hashlib

import cv2

import numpy as np

from scipy.ndimage import gaussian_filter1d

from scipy.signal import find_peaks

def _ridge_seed(rgb, cx, tip_y, width):
    """Choose a bounded distal texture patch using the input image alone.

    Gradient coherence and band energy are observations, not proof of ridges.
    Matcher scores, identity labels and manual reference boxes are absent.
    """
    h,w=rgb.shape[:2];side=max(64,2*round(.65*width/2));trials=[]
    for fraction in (.55,.70,.85,1.,1.15):
        cy=round(tip_y+fraction*width);box=[round(cx)-side//2,cy-side//2,round(cx)+side//2,cy+side//2]
        a,b,c,d=box
        if a<0 or b<0 or c>w or d>h:continue
        gray=cv2.cvtColor(rgb[b:d,a:c],cv2.COLOR_RGB2GRAY).astype(np.float32)
        band=cv2.GaussianBlur(gray,(0,0),max(.8,.003*width))-cv2.GaussianBlur(gray,(0,0),max(2.,.018*width))
        gx=cv2.Sobel(band,cv2.CV_32F,1,0,ksize=3);gy=cv2.Sobel(band,cv2.CV_32F,0,1,ksize=3)
        sigma=max(2.,width*.025)
        xx=cv2.GaussianBlur(gx*gx,(0,0),sigma);yy=cv2.GaussianBlur(gy*gy,(0,0),sigma);xy=cv2.GaussianBlur(gx*gy,(0,0),sigma)
        coherence=np.sqrt((xx-yy)**2+4*xy**2)/(xx+yy+1e-6)
        rms=np.sqrt(np.maximum(0,cv2.GaussianBlur(band*band,(0,0),sigma)))
        reliable=(coherence>=.35)&(rms>=1.5)
        score=float(np.mean(np.minimum(rms,12.)*reliable))
        trials.append(dict(seed_roi=box,center_width_fraction=fraction,texture_score=round(score,6),reliable_texture_fraction=round(float(reliable.mean()),4)))
    if not trials:return None,[]
    best=max(trials,key=lambda t:(t['texture_score'],-abs(t['center_width_fraction']-.85)))
    return best['seed_roi'],trials

def detect_fingertips(image):
    rgb = np.asarray(image)
    if rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3 or min(rgb.shape[:2]) < 64:
        raise ValueError('Expected HxWx3 uint8 RGB with sides >=64')
    h, w = rgb.shape[:2]
    ratio = min(1., 1024/max(h,w))
    small = cv2.resize(rgb, (round(w*ratio), round(h*ratio)), interpolation=cv2.INTER_AREA)
    sh, sw = small.shape[:2]
    hsv = cv2.cvtColor(small, cv2.COLOR_RGB2HSV)
    ycrcb=cv2.cvtColor(small,cv2.COLOR_RGB2YCrCb)
    red = small[:,:,0].astype(np.int16); green=small[:,:,1].astype(np.int16)
    skin = ((hsv[:,:,1]>=25)&(hsv[:,:,2]>30)&(red-green>=np.maximum(5,.04*red))&(ycrcb[:,:,1]>=135)&(ycrcb[:,:,2]<=135)).astype(np.uint8)
    skin = cv2.morphologyEx(skin,cv2.MORPH_CLOSE,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(7,7)))
    skin = cv2.morphologyEx(skin,cv2.MORPH_OPEN,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(5,5)))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(skin, 8)
    candidates=[]; rejected=[]
    for label in range(1,count):
        sx,sy,bw,bh,area=map(int,stats[label])
        if area < sh*sw*.012 or bh < sh*.12: continue
        comp=labels==label
        top=np.full(sw,float(sh))
        for x in range(sx,sx+bw):
            ys=np.flatnonzero(comp[:,x])
            if len(ys):top[x]=ys[0]
        profile=gaussian_filter1d(top,3.)
        peaks, props=find_peaks(-profile,prominence=max(15.,sh*.018),distance=max(16,round(sw*.04)))
        for pi,x in enumerate(peaks):
            if not sx <= x < sx+bw:continue
            ys=np.flatnonzero(comp[:,x]);tip=int(ys[0])
            if tip <= 4:rejected.append(dict(reason='tip_clipped',x=int(x)));continue
            def row_run(y,expected_x):
                if not 0<=y<sh:return None
                xs=np.flatnonzero(comp[y]);near=xs[np.abs(xs-expected_x)<sw*.035]
                if not len(near):return None
                center=int(near[np.argmin(np.abs(near-expected_x))]);left=center;right=center+1
                while left>0 and comp[y,left-1]:left-=1
                while right<sw and comp[y,right]:right+=1
                return left,right
            initial=[row_run(tip+round(sh*f),int(x)) for f in (.025,.035,.045)]
            initial=[v for v in initial if v]
            if len(initial)<2:continue
            width=float(np.median([b-a for a,b in initial]))
            if not 20<=width<=sw*.28:continue
            rows=[row_run(tip+round(width*f),int(x)) for f in (.4,.6,.8,1.)]
            rows=[v for v in rows if v]
            if len(rows)<3:continue
            widths=np.array([b-a for a,b in rows],float);width=float(np.median(widths))
            centers=np.array([(a+b)/2 for a,b in rows]);prom=float(props['prominences'][pi])
            reason=None
            cap=row_run(tip+max(1,round(.08*width)),int(x))
            if width<20 or width/ratio<160:reason='too_small_for_existing_pad_pipeline'
            elif cap is None or (cap[1]-cap[0])/width>.9:reason='flat_top_not_a_rounded_fingertip'
            elif min(a for a,b in rows)<=3 or max(b for a,b in rows)>=sw-3:reason='side_clipped'
            elif width>sw*.28 or np.ptp(widths)/width>.45:reason='unstable_or_merged_width'
            elif np.ptp(centers)/width>.25:reason='tilted_finger_requires_review'
            elif prom < .65*width:reason='short_protrusion_requires_review'
            if reason:rejected.append(dict(reason=reason,x=int(x),tip_y=tip));continue
            cx=float(np.median(centers));cy=tip+.70*width
            native_width=width/ratio
            nx=round(cx/ratio);ny=round(cy/ratio)
            box,trials=_ridge_seed(rgb,nx,tip/ratio,native_width)
            if box is None:
                rejected.append(dict(reason='seed_outside_image',x=int(x)));continue
            if any(abs(nx-c['tip_xy'][0])<.55*min(native_width,c['width_native']) for c in candidates):continue
            candidates.append(dict(seed_roi=box,tip_xy=[round(x/ratio),round(tip/ratio)],
                width_native=round(native_width,2),prominence_width_ratio=round(prom/width,3),
                seed_selection='highest bounded distal band energy/coherence; no matcher',seed_trials=trials,
                status='fingertip_proposal_requires_confirmation',finger_identity=None,
                ridge_visibility_verified=False,hand_side=None))
    candidates.sort(key=lambda c:(c['tip_xy'][0],c['tip_xy'][1]))
    digest=hashlib.sha256(rgb.tobytes()).hexdigest()[:12]
    for i,c in enumerate(candidates):c['candidate_id']=f'v2:{digest}:{i}'
    return dict(method='upright_skin_silhouette_v2',input_sha256=digest,candidates=candidates,
        rejected=rejected,manual_roi_used=False,matcher_scores_used=False,
        status='proposals_require_confirmation' if candidates else 'no_usable_fingertip_proposal',
        trained_detector=False,skin_tone_generalization_validated=False,
        automatic_detection_accuracy_validated=False,orientation_policy='near-upright only; rotate input explicitly')
