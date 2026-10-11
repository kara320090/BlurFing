import cv2

import numpy as np

from protect_rgb_fingerprint import validate_roi

def estimate_finger_width(rgb,box):
    rgb,box=validate_roi(rgb,box);x0,y0,x1,y1=box;cx=(x0+x1)//2;cy=(y0+y1)//2
    radius=600;left=max(0,cx-radius);right=min(rgb.shape[1],cx+radius)
    seed=rgb[max(0,cy-20):min(rgb.shape[0],cy+21),max(0,cx-20):min(rgb.shape[1],cx+21)]
    hsv=cv2.cvtColor(seed,cv2.COLOR_RGB2HSV)
    sat=float(np.median(hsv[:,:,1]));sat_threshold=max(12.,sat*.5);samples=[]
    for y in range(max(0,cy-90),min(rgb.shape[0],cy+91),30):
        row=rgb[y,left:right];hs=cv2.cvtColor(row[None],cv2.COLOR_RGB2HSV)[0]
        skin=(hs[:,1]>=sat_threshold)&(row[:,0].astype(int)-row[:,1].astype(int)>=2)&(hs[:,2]>30)
        skin=cv2.morphologyEx(skin.astype(np.uint8)[None],cv2.MORPH_CLOSE,np.ones((1,9),np.uint8))[0]>0
        center=cx-left
        if not skin[center]:
            nearby=np.flatnonzero(skin[max(0,center-20):min(len(skin),center+21)])
            if not len(nearby):continue
            nearby=nearby+max(0,center-20);center=int(nearby[np.argmin(abs(nearby-center))])
        a=center;b=center+1
        while a>0 and skin[a-1]:a-=1
        while b<len(skin)and skin[b]:b+=1
        if a==0 or b==len(skin)or not 160<=b-a<=900:continue
        samples.append(dict(y=int(y),left=int(left+a),right=int(left+b),width=int(b-a)))
    info=dict(samples=samples,seed_saturation=sat,saturation_threshold=sat_threshold,physical_dpi_known=False,
        method='RGB skin-saturation connected row intervals around manual pad center',matcher_score_used=False)
    if len(samples)<5:return info|dict(status='insufficient_boundary_rows',width=None)
    widths=np.array([s['width']for s in samples]);median=float(np.median(widths));iqr=float(np.percentile(widths,75)-np.percentile(widths,25))
    return info|dict(status='estimated'if iqr/median<=.25 else'unstable_boundary_width',width=median,width_iqr=iqr,relative_iqr=iqr/median)
