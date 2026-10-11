import cv2

import numpy as np

from protect_rgb_fingerprint import validate_roi

from contactless_finger_width import estimate_finger_width

def crease_boundary(rgb,component,tip_local,width,seed_y):
    gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY).astype(np.float32)
    smooth=cv2.GaussianBlur(gray,(0,0),max(1.,.012*width))
    dark=cv2.GaussianBlur(smooth,(1,0),sigmaX=0,sigmaY=max(2.,.06*width))-smooth
    start=max(round(tip_local+1.25*width),round(seed_y+.20*width))
    end=min(len(gray)-1,round(tip_local+1.95*width))
    scores=np.zeros(len(gray),np.float32);coverages=np.zeros(len(gray),np.float32)
    for y in range(start,end):
        xs=np.flatnonzero(component[y])
        if len(xs)<width*.55:continue
        left=round(xs[0]+.2*(xs[-1]-xs[0]));right=round(xs[-1]-.2*(xs[-1]-xs[0]))
        v=dark[y,left:right+1];coverages[y]=float(np.mean(v>2.))
        scores[y]=max(0.,float(np.median(v)))*coverages[y]
    peaks=[]
    radius=max(2,round(.07*width))
    for y in range(start,end):
        if scores[y]>=1.5 and coverages[y]>=.65 and scores[y]==np.max(scores[max(start,y-radius):min(end,y+radius+1)]):
            peaks.append(dict(y=int(y),score=float(scores[y]),coverage=float(coverages[y])))
    if not peaks:return None,dict(status='no_observed_crease',candidates=[],search_rows=[start,end])
    # Distal of spatially separate strong crease candidates, never score-tuned.
    best=max(p['score'] for p in peaks)
    credible=[p for p in peaks if p['score']>=max(1.5,best*.65)]
    selected=min(credible,key=lambda p:p['y'])
    return selected['y'],dict(status='observed_crease_proposal',selected=selected,candidates=peaks,
        search_rows=[start,end],selection='distal credible horizontal dark valley',expert_verified=False)

def propose_visible_pad(image,seed_roi):
    rgb,box=validate_roi(image,seed_roi);a,b,c,d=box;cx=(a+c)//2;cy=(b+d)//2
    measurement=estimate_finger_width(rgb,box)
    meta=dict(method='visible_pad_scope_v2',seed_roi=list(box),width_measurement=measurement,
        proposal_only=True,expert_segmentation_validated=False,matcher_score_used=False,upright_finger_assumption=True)
    def fail(status):return None,None,meta|dict(status=status)
    if measurement['status']!='estimated':return fail('scope_width_unavailable')
    width=measurement['width'];rx=round(width*1.4);ry=round(width*2.8)
    x0=max(0,cx-rx);x1=min(rgb.shape[1],cx+rx+1);y0=max(0,cy-ry);y1=min(rgb.shape[0],cy+ry+1)
    crop=rgb[y0:y1,x0:x1];hsv=cv2.cvtColor(crop,cv2.COLOR_RGB2HSV)
    skin=(hsv[:,:,1]>=measurement['saturation_threshold'])&(crop[:,:,0].astype(int)-crop[:,:,1].astype(int)>=2)&(hsv[:,:,2]>30)
    skin=cv2.morphologyEx(skin.astype(np.uint8),cv2.MORPH_CLOSE,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(9,9)))
    skin=cv2.morphologyEx(skin,cv2.MORPH_OPEN,np.ones((3,3),np.uint8))
    _,labels,_,_=cv2.connectedComponentsWithStats(skin,8);label=labels[cy-y0,cx-x0]
    if not label:return fail('scope_seed_not_skin')
    component=labels==label;yy,xx=np.where(component);tip=y0+int(yy.min())
    if component[0].any():return fail('scope_tip_clipped')
    observed,crease=crease_boundary(crop,component,tip-y0,width,cy-y0)
    bottom=round(tip+1.6*width) if observed is None else y0+observed
    meta.update(crease=crease,tip_y=tip,geometric_bottom_y=round(tip+1.6*width),bottom_y=bottom,
        lower_boundary_geometric=observed is None,boundary_confidence='heuristic_observed' if observed is not None else 'geometric_fallback')
    if not tip<cy<bottom or bottom>=y1:return fail('scope_seed_or_bottom_outside')
    pad=component.copy();pad[np.arange(len(pad))+y0>=bottom]=False
    # Only pad-local sides matter; a lower hand may legitimately join window edges.
    if pad[:,0].any() or pad[:,-1].any():return fail('scope_pad_sides_clipped')
    yy,xx=np.where(pad)
    if len(xx)<.4*width**2:return fail('scope_pad_too_small')
    row_widths=[];centers=[]
    for y in range(round(tip-y0+.3*width),bottom-y0,max(1,round(width/20))):
        xs=np.flatnonzero(pad[y])
        if len(xs):row_widths.append(int(xs[-1]-xs[0]+1));centers.append(float((xs[-1]+xs[0])/2))
    if not row_widths or max(row_widths)>1.5*width:return fail('scope_merged_or_wide_silhouette')
    if max(centers)-min(centers)>.5*width:return fail('scope_not_upright')
    xmin=x0+int(xx.min());xmax=x0+int(xx.max())+1;centerx=(xmin+xmax)//2;centery=(tip+bottom)//2
    side=2*int(np.ceil((max(xmax-xmin,bottom-tip)+.2*width)/2))
    scope=[centerx-side//2,centery-side//2,centerx+side//2,centery+side//2]
    if scope[0]<0 or scope[1]<0 or scope[2]>rgb.shape[1] or scope[3]>rgb.shape[0]:return fail('scope_square_out_of_image')
    sx,sy,_,_=scope;mask=np.zeros((side,side),bool);mask[yy+y0-sy,xx+x0-sx]=True
    return scope,mask,meta|dict(status='scope_proposal',roi_xyxy=scope,pad_pixels=int(mask.sum()),native_side=side,width=width)
