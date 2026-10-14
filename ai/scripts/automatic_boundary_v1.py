"""Experimental multiview detector and local graph-cut pad proposals.

No filenames, person labels, matcher scores, learned models or original ridge
structure are used for localization. Review remains necessary: skin/geometry
and ridge statistics are not a trained palmar-vs-nail classifier.
"""
import hashlib
import threading
import time
import cv2
import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks
from automatic_fingertip_proposals import _ridge_seed, detect_fingertips
from visible_pad_scope_quality import propose_visible_pad as legacy_pad
from protect_visible_pad_checked_v2 import observed_seed_pitch
from automatic_ridge_consensus import observe_fallback

_LOCK = threading.RLock()


def _skin(rgb):
    hsv=cv2.cvtColor(rgb,cv2.COLOR_RGB2HSV);y=cv2.cvtColor(rgb,cv2.COLOR_RGB2YCrCb)
    red=rgb[:,:,0].astype(np.int16);green=rgb[:,:,1].astype(np.int16)
    mask=((hsv[:,:,1]>=25)&(hsv[:,:,2]>30)&(red-green>=np.maximum(5,.04*red))&(y[:,:,1]>=135)&(y[:,:,2]<=135)).astype(np.uint8)
    return cv2.morphologyEx(mask,cv2.MORPH_CLOSE,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(7,7)))


def _rotation(k,h,w):
    # np.rot90 coordinate mapping original -> rotated, with inverse exact.
    return [np.array([[1,0,0],[0,1,0]],float),np.array([[0,1,0],[-1,0,w-1]],float),
            np.array([[-1,0,w-1],[0,-1,h-1]],float),np.array([[0,-1,h-1],[1,0,0]],float)][k]


def _square(mask):
    yy,xx=np.where(mask)
    if not len(xx):return None
    side=max(int(xx.max()-xx.min()+1),int(yy.max()-yy.min()+1));side+=side%2
    if side>min(mask.shape):return None
    cx=(int(xx.max())+int(xx.min()))//2;cy=(int(yy.max())+int(yy.min()))//2
    a=min(max(0,cx-side//2),mask.shape[1]-side);b=min(max(0,cy-side//2),mask.shape[0]-side)
    return [a,b,a+side,b+side]



def square_tile_plan(mask):
    """Cover an elongated proposal without clipping; never authorizes rendering.

    Frozen multi-region transforms reject overlapping application masks. A
    disjoint partition adds an internal compositor boundary and independent
    renderer phases. Therefore these scopes are a geometry-only review plan.
    """
    yy,xx=np.where(mask)
    if not len(xx):return dict(status='empty',scopes=[])
    h,w=mask.shape;side=min(h,w);x0=min(max(0,int((xx.min()+xx.max()+1-side)//2)),w-side)
    if xx.min()<x0 or xx.max()>=x0+side:return dict(status='incompatible',scopes=[])
    starts=[max(0,min(int(yy.min()),h-side)),max(0,min(int(yy.max())+1-side,h-side))]
    starts=sorted(set(starts));cover=np.zeros_like(mask)
    scopes=[]
    for y in starts:
        cover[y:y+side,x0:x0+side]=True;scopes.append([x0,y,x0+side,y+side])
    return dict(status='geometry_only_not_transform_approved',scopes=scopes,mask_pixels=int(mask.sum()),uncovered_pixels=int((mask&~cover).sum()),overlapping_application_masks_forbidden=True,internal_seam_validation_required=True)

def _view_candidates(rgb,scale_limit,red_chroma_only=False):
    h,w=rgb.shape[:2];ratio=min(1.,scale_limit/max(h,w));small=cv2.resize(rgb,(round(w*ratio),round(h*ratio)),interpolation=cv2.INTER_AREA)
    sh,sw=small.shape[:2];skin=_skin(small)
    if red_chroma_only:
        hue=cv2.cvtColor(small,cv2.COLOR_RGB2HSV)[:,:,0]
        skin=skin & ((hue<=12)|(hue>=170)).astype(np.uint8)
    n,labels,stats,_=cv2.connectedComponentsWithStats(skin,8);rows=[]
    for label in range(1,n):
        sx,sy,bw,bh,area=stats[label]
        if area<sh*sw*.012 or bh<sh*.12:continue
        comp=labels==label;top=np.full(sw,float(sh))
        for x in range(int(sx),int(sx+bw)):
            yy=np.flatnonzero(comp[:,x])
            if len(yy):top[x]=yy[0]
        peaks,_=find_peaks(-gaussian_filter1d(top,3.),prominence=max(15.,sh*.018),distance=max(16,round(sw*.04)))
        for x in peaks:
            ys=np.flatnonzero(comp[:,x]);tip=int(ys[0])
            if tip<=4:continue
            def run(y):
                if not 0<=y<sh or not comp[y,x]:return None
                a=x;b=x+1
                while a>0 and comp[y,a-1]:a-=1
                while b<sw and comp[y,b]:b+=1
                return int(a),int(b)
            initial=[run(tip+round(sh*f)) for f in (.025,.035,.045)];initial=[v for v in initial if v]
            if len(initial)<2:continue
            width=float(np.median([b-a for a,b in initial]))
            samples=[run(tip+round(width*f)) for f in (.4,.6,.8,1.)];samples=[v for v in samples if v]
            if len(samples)<3:continue
            widths=np.array([b-a for a,b in samples]);width=float(np.median(widths));centers=np.array([(a+b)/2 for a,b in samples]);cap=run(tip+max(1,round(.08*width)))
            # The broad proposal range permits close-up fingers; it is never an acceptance gate.
            if width/ratio<160 or width>sw*.9 or cap is None or (cap[1]-cap[0])/width>.9 or np.ptp(widths)/width>.45:continue
            if min(a for a,b in samples)<=3 or max(b for a,b in samples)>=sw-3:continue
            cx=float(np.median(centers))/ratio;box,trials=_ridge_seed(rgb,cx,tip/ratio,width/ratio)
            if box is not None:rows.append(dict(seed_roi=box,tip_xy=[round(x/ratio),round(tip/ratio)],width_native=width/ratio,seed_trials=trials,proposal_only=True))
    return rows



def isolate_seed_scanlines(fg,sx,sy,tip,ww):
    sh,sw=fg.shape
    # Track only the contiguous scanline run attached to this seed axis.
    # Other fingers can share the palm component but not the distal run.
    isolated=np.zeros_like(fg);center=float(sx);width_runs=[]
    for y in range(max(0,round(tip+.25*ww)),min(sh,round(tip+1.05*ww))):
        xs=np.flatnonzero(fg[y])
        if not len(xs):continue
        near=int(xs[np.argmin(abs(xs-center))])
        if abs(near-center)>.2*ww:continue
        left=near;right=near+1
        while left>0 and fg[y,left-1]:left-=1
        while right<sw and fg[y,right]:right+=1
        if .45*ww<=right-left<=1.4*ww:width_runs.append(right-left)
    if len(width_runs)<5:return None,dict(reject_reason='finger_width_unstable')
    reference=float(np.median(width_runs))
    for y in range(sh):
        xs=np.flatnonzero(fg[y])
        if not len(xs):continue
        near=int(xs[np.argmin(abs(xs-center))])
        if abs(near-center)>.35*reference:continue
        left=near;right=near+1
        while left>0 and fg[y,left-1]:left-=1
        while right<sw and fg[y,right]:right+=1
        if right-left>1.45*reference:continue
        isolated[y,left:right]=True
        center=.9*center+.1*(left+right)/2
    if not isolated[sy,sx]:return None,dict(reject_reason='neighbor_finger_connected')
    return isolated,dict(reference_width=reference)

def _local_pad_pass(rgb,candidate,isolate=False):
    """Graph-cut separates local foreground before robust row geometry and crease path."""
    h,w=rgb.shape[:2];cx=(candidate['seed_roi'][0]+candidate['seed_roi'][2])//2;tip=candidate['tip_xy'][1];width=candidate['width_native'];cy=(candidate['seed_roi'][1]+candidate['seed_roi'][3])//2
    a=max(0,round(cx-1.4*width));c=min(w,round(cx+1.4*width));b=max(0,round(tip-.2*width));d=min(h,round(tip+2.5*width));crop=rgb[b:d,a:c]
    if min(crop.shape[:2])<64:return None,dict(reject_reason='too_small')
    ratio=min(1.,800/max(crop.shape[:2]));small=cv2.resize(crop,(round((c-a)*ratio),round((d-b)*ratio)),interpolation=cv2.INTER_AREA)
    sh,sw=small.shape[:2];sx=round((cx-a)*ratio);sy=round((cy-b)*ratio);ww=width*ratio
    if not 0<=sx<sw or not 0<=sy<sh:return None,dict(reject_reason='boundary_quality_low')
    labels=np.where(_skin(small)>0,cv2.GC_PR_FGD,cv2.GC_PR_BGD).astype(np.uint8)
    labels[[0,-1],:]=cv2.GC_BGD;labels[:,[0,-1]]=cv2.GC_BGD
    yy,xx=np.indices(labels.shape);sure=((xx-sx)**2+(yy-sy)**2)<(.13*ww)**2;labels[sure]=cv2.GC_FGD
    with _LOCK:
        cv2.setRNGSeed(int(hashlib.sha256(crop.tobytes()).hexdigest()[:7],16))
        cv2.grabCut(small,labels,None,np.zeros((1,65),np.float64),np.zeros((1,65),np.float64),3,cv2.GC_INIT_WITH_MASK)
    fg=np.isin(labels,[cv2.GC_FGD,cv2.GC_PR_FGD]).astype(np.uint8);_,components,_,_=cv2.connectedComponentsWithStats(fg,8);chosen=components[sy,sx]
    if not chosen:return None,dict(reject_reason='background_connected')
    fg=components==chosen;rows=[]
    if isolate:
        fg,isolation_quality=isolate_seed_scanlines(fg,sx,sy,(tip-b)*ratio,ww)
        if fg is None:return None,isolation_quality
    for y in range(max(0,round((tip-b)*ratio+.3*ww)),min(sh,round((tip-b)*ratio+1.3*ww)),max(1,round(ww/20))):
        xs=np.flatnonzero(fg[y])
        if len(xs):rows.append((y,int(xs[0]),int(xs[-1])+1))
    if len(rows)<5:return None,dict(reject_reason='finger_width_unstable')
    widths=np.array([r-l for _,l,r in rows]);median=float(np.median(widths));spread=float((np.percentile(widths,75)-np.percentile(widths,25))/median)
    if spread>.25 or max(widths)>1.5*median:return None,dict(reject_reason='neighbor_finger_connected',width_relative_iqr=spread)
    # Preserve the existing absolute crease-response and coverage requirements.
    gray=cv2.cvtColor(small,cv2.COLOR_RGB2GRAY).astype(np.float32);sm=cv2.GaussianBlur(gray,(0,0),max(1.,.012*median));dark=cv2.GaussianBlur(sm,(1,0),sigmaX=0,sigmaY=max(2.,.06*median))-sm
    local_tip=int(np.where(fg)[0].min());start=max(round(local_tip+1.25*median),round(sy+.20*median));end=min(sh-1,round(local_tip+1.95*median));crease=[]
    for y in range(start,end):
        xs=np.flatnonzero(fg[y])
        if len(xs)<.55*median:continue
        lo=round(xs[0]+.2*(xs[-1]-xs[0]));hi=round(xs[-1]-.2*(xs[-1]-xs[0]));v=dark[y,lo:hi+1];coverage=float(np.mean(v>2.));score=max(0.,float(np.median(v)))*coverage
        if score>=1.5 and coverage>=.65:crease.append((y,score))
    if not crease and isolate and end-start>=3:
        # Dynamic-programming dark-valley trace permits an oblique crease while
        # retaining the original absolute response/coverage and prior checks.
        xlo=max(0,round(sx-.30*median));xhi=min(sw,round(sx+.30*median))
        response=dark[start:end,xlo:xhi].astype(np.float64)
        if response.shape[1]>=5:
            cost=response[:,0].copy();parents=[]
            for x in range(1,response.shape[1]):
                choices=np.stack([np.roll(cost,k)-abs(k)*.75 for k in [-1,0,1]])
                choices[0,-1]=-np.inf;choices[2,0]=-np.inf
                move=np.argmax(choices,axis=0);parents.append(move)
                cost=choices[move,np.arange(len(cost))]+response[:,x]
            ys=np.empty(response.shape[1],int);ys[-1]=int(np.argmax(cost))
            for x in range(response.shape[1]-1,0,-1):ys[x-1]=ys[x]-[-1,0,1][parents[x-1][ys[x]]]
            values=response[ys,np.arange(len(ys))];coverage=float(np.mean(values>2.));score=max(0.,float(np.median(values)))*coverage
            if score>=1.5 and coverage>=.65 and np.max(abs(np.diff(ys)))<=1:
                crease=[(round(float(np.median(ys)))+start,score)]
    if not crease:return None,dict(reject_reason='crease_not_observed',finger_width_native=median/ratio)
    bottom=min(y for y,score in crease);prior=local_tip+1.6*median
    if abs(bottom-prior)/median>.2:return None,dict(reject_reason='boundary_quality_low',crease_prior_disagreement=abs(bottom-prior)/median)
    # Trace the local dark valley in a narrow neighborhood, not a horizontal cut.
    xs=np.arange(sw);curve=np.full(sw,float(bottom));radius=max(2,round(.07*median))
    for x in range(sw):
        ys=np.arange(max(start,bottom-radius),min(end,bottom+radius+1))
        values=dark[ys,x];curve[x]=ys[np.argmax(values)] if len(ys) else bottom
    curve=gaussian_filter1d(curve,max(1.,median*.025))
    pad=fg & (yy<curve[None,:])
    # Inspect before erosion; the graph-cut hard border must not hide search-window contact.
    if pad[:,1].any() or pad[:,-2].any():return None,dict(reject_reason='background_connected')
    pad=cv2.erode(pad.astype(np.uint8),np.ones((3,3),np.uint8))>0
    # A finger proposal may not retain detached foreground specks after erosion.
    # This is source-geometry cleanup, not GT-driven cropping.
    _,parts,_,_=cv2.connectedComponentsWithStats(pad.astype(np.uint8),connectivity=4)
    seed_component=parts[sy,sx]
    if not seed_component:return None,dict(reject_reason='boundary_quality_low')
    pad=parts==seed_component
    if pad[:,0].any() or pad[:,-1].any():return None,dict(reject_reason='background_connected')
    if not pad[sy,sx] or pad.sum()<.4*median**2:return None,dict(reject_reason='boundary_quality_low')
    native=cv2.resize(pad.astype(np.uint8),(c-a,d-b),interpolation=cv2.INTER_NEAREST)>0;full=np.zeros((h,w),bool);full[b:d,a:c]=native
    # Match the consumer's four-neighbor component contract in native pixels.
    _,parts,_,_=cv2.connectedComponentsWithStats(full.astype(np.uint8),connectivity=4)
    component=parts[cy,cx]
    if not component:return None,dict(reject_reason='boundary_quality_low')
    full=parts==component
    return full,dict(status='proposal_requires_review',reject_reason=None,finger_width_native=median/ratio,width_relative_iqr=spread,crease_observed=True,crease_curve_range_native=float(np.ptp(curve)/ratio),expert_segmentation_validated=False)



def _local_pad(rgb,candidate):
    mask,quality=_local_pad_pass(rgb,candidate)
    if mask is not None:return mask,quality
    if quality.get('reject_reason') in {'neighbor_finger_connected','crease_not_observed','background_connected'}:
        isolated,isolated_quality=_local_pad_pass(rgb,candidate,isolate=True)
        if isolated is not None:
            return isolated,isolated_quality|dict(per_finger_scanline_isolation=True,previous_reject_reason=quality['reject_reason'])
        return None,isolated_quality|dict(primary_reject_reason=quality['reject_reason'])
    return mask,quality


def detect_boundaries(image):
    rgb=np.asarray(image)
    if rgb.dtype!=np.uint8 or rgb.ndim!=3 or rgb.shape[2]!=3 or min(rgb.shape[:2])<64:raise ValueError('Expected uint8 RGB')
    t=time.perf_counter();candidate_seconds=0.;proposals=[];rejected=[];seen=[];h,w=rgb.shape[:2]
    # Keep legacy accepted masks byte-identical as a protected baseline path.
    candidate_start=time.perf_counter();legacy=detect_fingertips(rgb);candidate_seconds+=time.perf_counter()-candidate_start
    for c in legacy['candidates']:
        scope,mask,quality=legacy_pad(rgb,c['seed_roi'])
        if scope is not None:
            full=np.zeros((h,w),bool);a,b,cx,d=scope;full[b:d,a:cx]=mask
            proposals.append(dict(candidate=c,mask=full,scope=scope,quality=quality,method='legacy_accepted'))
    for k in range(4):
        view=np.rot90(rgb,k).copy();vh,vw=view.shape[:2];inv=cv2.invertAffineTransform(_rotation(k,h,w))
        candidates=[]
        candidate_start=time.perf_counter()
        for limit in [1024,1600]:
            candidates.extend(_view_candidates(view,limit))
            candidates.extend(_view_candidates(view,limit,red_chroma_only=True))
        candidate_seconds+=time.perf_counter()-candidate_start
        for c in candidates:
            center=np.array([[(c['seed_roi'][0]+c['seed_roi'][2])/2,(c['seed_roi'][1]+c['seed_roi'][3])/2,1.]])@inv.T;center=center[0]
            if any(np.hypot(center[0]-x,center[1]-y)<.55*min(c['width_native'],width) for x,y,width in seen):continue
            seen.append((float(center[0]),float(center[1]),c['width_native']))
            try:mask,quality=_local_pad(view,c)
            except cv2.error as e:mask=None;quality=dict(reject_reason='boundary_quality_low',error_type=type(e).__name__)
            if mask is None:rejected.append(quality);continue
            original_mask=np.rot90(mask,-k).copy();scope=_square(original_mask)
            if scope is None:rejected.append(dict(reject_reason='frozen_square_scope_incompatible',observed_mask_pixels=int(original_mask.sum()),mask_bbox_extent=[int(np.ptp(np.where(original_mask)[1]))+1,int(np.ptp(np.where(original_mask)[0]))+1],square_tile_plan=square_tile_plan(original_mask)));continue
            side=c['seed_roi'][2]-c['seed_roi'][0];sx=round(center[0]-side/2);sy=round(center[1]-side/2);seed=[sx,sy,sx+side,sy+side]
            if sx<0 or sy<0 or sx+side>w or sy+side>h:rejected.append(dict(reject_reason='boundary_quality_low'));continue
            proposals.append(dict(candidate=dict(seed_roi=seed,candidate_id='multi:'+str(len(proposals))),mask=original_mask,scope=scope,quality=quality|dict(rotation_quadrants=k),method='local_graphcut'))
    regions=[]
    for i,p in enumerate(proposals):
        pitch,measurement,_=observed_seed_pitch(rgb,p['candidate']['seed_roi'])
        if pitch is None and p['method']=='legacy_accepted':
            selected,consensus=observe_fallback(rgb,p['candidate'],dict(pitch_native=pitch,scope_quality=p['quality']))
            p['quality']=p['quality']|dict(pitch_consensus=consensus)
            if selected is not None:
                scope,local,quality=legacy_pad(rgb,selected['seed_roi'])
                if scope is not None:
                    full=np.zeros((h,w),bool);a,b,c,d=scope;full[b:d,a:c]=local
                    p.update(candidate=selected,scope=scope,mask=full,quality=quality|dict(pitch_consensus=consensus))
                    pitch,measurement,_=observed_seed_pitch(rgb,selected['seed_roi'])
        reason=None if pitch is not None and 2<=pitch<=50 else 'pitch_invalid'
        # New graph-cut masks deliberately remain unapproved pending leakage review.
        if p['method']!='legacy_accepted' and reason is None:reason='boundary_review_required'
        regions.append(dict(candidate=p['candidate'],scope=p['scope'],mask=p['mask'],quality=p['quality'],pitch_native=pitch,pitch_measurement=measurement,status='accepted' if reason is None else 'rejected',reject_reason=reason,method=p['method']))
    return dict(detector_version='automatic_boundary_v2_separation_review',proposal_count=len(seen),legacy_boundary_count=sum(p['method']=='legacy_accepted' for p in proposals),regions=regions,rejected=rejected,detection_seconds=time.perf_counter()-t,candidate_generation_seconds=candidate_seconds,boundary_and_pitch_seconds=time.perf_counter()-t-candidate_seconds,ground_truth_validated=False)
