import numpy as np

from visible_pad_scope_v2 import propose_visible_pad as propose_v2

def propose_visible_pad(image,seed_roi):
    scope,mask,meta=propose_v2(image,seed_roi)
    meta=meta|dict(method='visible_pad_scope_v3')
    if scope is None:return scope,mask,meta
    candidates=meta['crease'].get('candidates',[])
    if not candidates:return scope,mask,meta
    first=min(candidates,key=lambda p:p['y']);selected=meta['crease']['selected']
    if first['y']==selected['y']:
        meta['crease']=meta['crease']|dict(selection='first absolute-threshold distal crease; no strongest-relative cutoff')
        return scope,mask,meta
    bottom=meta['bottom_y']-(selected['y']-first['y']);a,b,c,d=scope
    yy,xx=np.where(mask);keep=yy+b<bottom;yy=yy[keep];xx=xx[keep]
    if not len(xx):return None,None,meta|dict(status='scope_empty_after_distal_crease')
    xmin=a+int(xx.min());xmax=a+int(xx.max())+1;tip=meta['tip_y'];width=meta['width']
    side=2*int(np.ceil((max(xmax-xmin,bottom-tip)+.2*width)/2));cx=(xmin+xmax)//2;cy=(tip+bottom)//2
    new=[cx-side//2,cy-side//2,cx+side//2,cy+side//2];out=np.zeros((side,side),bool)
    out[yy+b-new[1],xx+a-new[0]]=True
    meta.update(bottom_y=bottom,roi_xyxy=new,pad_pixels=int(out.sum()),native_side=side)
    meta['crease']=meta['crease']|dict(selected=first,selection='first absolute-threshold distal crease; no strongest-relative cutoff',proximal_stronger_crease_ignored=True)
    return new,out,meta
