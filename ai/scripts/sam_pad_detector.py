"""Linux development: native encoded RGB + individual SAM masks -> pad candidates.

GT is never an input. All candidates remain review-gated until independent
quantitative approval. Geometry fallback is explicitly not an observed crease.
"""
import hashlib
import json
from pathlib import Path
import time
import cv2
import numpy as np

VERSION='sam_pad_axis_v2_foreground_review'


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def bbox(mask):
    y,x=np.where(mask)
    return [int(x.min()),int(y.min()),int(x.max())+1,int(y.max())+1] if len(x) else None


def clean_mask(mask):
    if mask.ndim!=2 or mask.dtype!=np.bool_:raise ValueError('Expected Boolean finger mask')
    n,labels,stats,_=cv2.connectedComponentsWithStats(mask.astype(np.uint8),connectivity=4)
    if n<=1:return None,dict(reject_reason='empty_finger_mask')
    chosen=1+int(np.argmax(stats[1:,cv2.CC_STAT_AREA]));clean=labels==chosen
    fraction=float(clean.sum()/max(1,mask.sum()))
    if fraction<.9:return None,dict(reject_reason='multiple_fingers_in_one_mask',largest_component_fraction=fraction)
    return clean,dict(largest_component_fraction=fraction,discarded_pixels=int(mask.sum()-clean.sum()))


def refine_edge_connected_foreground(rgb, mask):
    """RGB-only conservative refinement of near-full-frame SAM leakage.

    Three image edges plus large occupancy indicate insufficient background
    separation, not a sample identity. Otsu selects the chroma partition from
    the image, without GT or a tuned per-image cutoff. Never expands SAM support.
    """
    margin=max(1,round(.01*min(mask.shape)))
    edges=sum(bool(v.any()) for v in (mask[:margin],mask[-margin:],mask[:,:margin],mask[:,-margin:]))
    meta=dict(method='edge_connected_RGB_chroma_otsu',applied=False,edge_contacts=edges)
    if edges<3 or mask.mean()<.75:return mask,meta
    small_rgb=cv2.resize(rgb,(max(1,rgb.shape[1]//4),max(1,rgb.shape[0]//4)),interpolation=cv2.INTER_AREA)
    chroma=np.clip(small_rgb[:,:,0].astype(np.int16)-small_rgb[:,:,1].astype(np.int16),0,255).astype(np.uint8)
    threshold,_=cv2.threshold(chroma,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)
    support=chroma>threshold
    support=cv2.morphologyEx(support.astype(np.uint8),cv2.MORPH_CLOSE,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(5,5)))
    support=cv2.resize(support,(mask.shape[1],mask.shape[0]),interpolation=cv2.INTER_NEAREST)>0
    refined,q=clean_mask(mask&support)
    if refined is None or refined.sum()<.35*mask.sum():return mask,meta|dict(reason='uncertain_chroma_partition')
    return refined,meta|dict(applied=True,otsu_threshold=float(threshold),removed_pixels=int(mask.sum()-refined.sum()))


def extract_one(rgb,finger,prepared_quality=None,tip_hint=None):
    from scipy.ndimage import gaussian_filter1d
    from scipy.signal import find_peaks
    h,w=finger.shape
    if prepared_quality is None:clean,quality=clean_mask(finger)
    else:clean,quality=finger,prepared_quality
    if quality.get("reject_reason"):clean=None
    if clean is None:return dict(mask=np.zeros_like(finger),status='rejected',quality=quality)
    clean,foreground=refine_edge_connected_foreground(rgb,clean);quality=quality|dict(foreground_refinement=foreground)
    bb=bbox(clean);a,b,c,d=bb;scale=min(1.,720/max(d-b,c-a));small=cv2.resize(clean[b:d,a:c].astype(np.uint8),(max(1,round((c-a)*scale)),max(1,round((d-b)*scale))),interpolation=cv2.INTER_NEAREST)>0
    image=cv2.resize(rgb[b:d,a:c],(small.shape[1],small.shape[0]),interpolation=cv2.INTER_AREA)
    y,x=np.where(small)
    if len(x)<100:return dict(mask=np.zeros_like(finger),status='rejected',quality=quality|dict(reject_reason='too_small'))
    coords=np.column_stack([x,y]).astype(float);center=coords.mean(axis=0);values,vectors=np.linalg.eigh(np.cov(coords.T));axis=vectors[:,-1]
    if values[-1]/max(1.,values[0])<1.6:return dict(mask=np.zeros_like(finger),status='rejected',quality=quality|dict(reject_reason='axis_unstable'))
    def normalize(direction):
        normal=np.array([direction[1],-direction[0]]);t=(coords-center)@direction;v=(coords-center)@normal
        lo=np.array([v.min()-2,t.min()-2]);matrix=np.array([[normal[0],normal[1],-center@normal-lo[0]],[direction[0],direction[1],-center@direction-lo[1]]])
        size=(int(np.ceil(v.max()-lo[0]))+3,int(np.ceil(t.max()-lo[1]))+3)
        mask=cv2.warpAffine(small.astype(np.uint8),matrix,size,flags=cv2.INTER_NEAREST)>0
        gray=cv2.cvtColor(cv2.warpAffine(image,matrix,size,flags=cv2.INTER_LINEAR),cv2.COLOR_RGB2GRAY).astype(np.float32)
        widths=np.array([np.ptp(np.where(row)[0])+1 if row.any() else 0 for row in mask],float)
        valid=np.flatnonzero(widths);start=int(valid.min());end=int(valid.max());span=end-start+1
        cap=float(np.median(widths[start+max(1,round(span*.02)):start+max(2,round(span*.15))]));base=float(np.median(widths[end-max(2,round(span*.15)):end-max(1,round(span*.02))]))
        return matrix,mask,gray,widths,start,end,cap,base
    matrix,mask,gray,widths,start,end,cap,base=normalize(axis)
    # Optional RGB-only cap proposal resolves the major-axis sign; it never
    # supplies the lower pad boundary or expands the SAM foreground.
    hint_used=False
    if tip_hint is not None:
        hint=np.asarray(tip_hint,float)
        if hint.shape!=(2,) or not np.isfinite(hint).all() or not (0<=hint[0]<w and 0<=hint[1]<h):raise ValueError('invalid_RGB_tip_hint')
        working=(hint-np.array([a,b]))*scale;canonical=matrix@np.r_[working,1.];fraction=(canonical[1]-start)/max(1,end-start)
        outside=cv2.distanceTransform((~small).astype(np.uint8),cv2.DIST_L2,cv2.DIST_MASK_PRECISE);hx=int(np.clip(round(working[0]),0,small.shape[1]-1));hy=int(np.clip(round(working[1]),0,small.shape[0]-1))
        body_width=float(np.median(widths[widths>0]))
        if outside[hy,hx]<=.25*body_width and (fraction<=.25 or fraction>=.75):
            hint_used=True
            if fraction>=.75:axis=-axis;matrix,mask,gray,widths,start,end,cap,base=normalize(axis)
    if not hint_used and cap>base:axis=-axis;matrix,mask,gray,widths,start,end,cap,base=normalize(axis)
    ambiguity=abs(base-cap)/max(1.,max(base,cap))
    tip_canonical=start;length=end-start+1
    reference=widths[start+round(.15*length):start+round(.55*length)];reference=reference[reference>0];width=float(np.median(reference))
    if width<12:return dict(mask=np.zeros_like(finger),status='rejected',quality=quality|dict(reject_reason='too_small'))
    smooth=cv2.GaussianBlur(gray,(0,0),max(1.,.025*width));response=cv2.GaussianBlur(smooth,(1,0),sigmaX=0,sigmaY=max(2.,.18*width))-smooth
    row_signal=np.zeros(len(widths));coverage=np.zeros(len(widths))
    for yy in range(start,end+1):
        xx=np.flatnonzero(mask[yy])
        if not len(xx):continue
        left,right=np.percentile(xx,[20,80]).astype(int);v=response[yy,left:right+1];row_signal[yy]=float(np.median(v));coverage[yy]=float(np.mean(v>2))
    lo=min(end,max(start,round(start+1.1*width)));hi=min(end,round(start+2.4*width));signal=gaussian_filter1d(row_signal,max(1.,.015*width))
    peaks,_=find_peaks(signal,prominence=1.5,distance=max(2,round(.25*width)))
    possible=[int(p) for p in peaks if lo<=p<=hi and signal[p]>=1.5 and coverage[p]>=.65]
    observed=bool(possible);bottom=possible[0] if observed else min(end,round(start+1.8*width))
    # Trace the crease locally; clip to input finger geometry on inverse mapping.
    curve=np.full(mask.shape[1],float(bottom));radius=max(1,round(.10*width))
    if observed:
        for xx in range(mask.shape[1]):
            ys=np.arange(max(lo,bottom-radius),min(hi,bottom+radius)+1)
            if len(ys):curve[xx]=float(ys[np.argmax(response[ys,xx])])
        curve=gaussian_filter1d(curve,max(1.,.06*width))
    yy=np.arange(mask.shape[0])[:,None];pad=mask&(yy<=curve[None,:])
    inverse=cv2.invertAffineTransform(matrix);local=cv2.warpAffine(pad.astype(np.uint8),inverse,(small.shape[1],small.shape[0]),flags=cv2.INTER_NEAREST)>0
    native=cv2.resize(local.astype(np.uint8),(c-a,d-b),interpolation=cv2.INTER_NEAREST)>0;full=np.zeros_like(finger);full[b:d,a:c]=native;full&=clean
    n,labels,stats,_=cv2.connectedComponentsWithStats(full.astype(np.uint8),connectivity=4)
    if n<=1:return dict(mask=full,status='rejected',quality=quality|dict(reject_reason='empty_pad'))
    full=labels==(1+int(np.argmax(stats[1:,cv2.CC_STAT_AREA])))
    assert not (full&~finger).any()
    tip_xy=inverse@np.array([mask.shape[1]/2,start,1.]);tip_xy=tip_xy/scale+np.array([a,b])
    if hint_used:tip_xy=np.asarray(tip_hint,float)
    # Metadata must use a real native foreground pixel, not an extrapolated axis.
    projected_outside=not (0<=tip_xy[0]<w and 0<=tip_xy[1]<h)
    px=int(np.clip(round(tip_xy[0]),0,w-1));py=int(np.clip(round(tip_xy[1]),0,h-1));radius=max(2,int(np.ceil(2/scale)),round(.25*width/scale) if hint_used else 0)
    l=max(0,px-radius);r=min(w,px+radius+1);top=max(0,py-radius);bottom_search=min(h,py+radius+1);ny,nx=np.where(clean[top:bottom_search,l:r])
    endpoint_on_mask=bool(len(nx))
    if endpoint_on_mask:
        index=int(np.argmin((nx+l-tip_xy[0])**2+(ny+top-tip_xy[1])**2));tip_xy=np.array([nx[index]+l,ny[index]+top])
    else:tip_xy=np.array([px,py])
    reasons=[]
    if projected_outside or not endpoint_on_mask:reasons.append('geometric_tip_endpoint_unreliable')
    if min(tip_xy[0],tip_xy[1],w-1-tip_xy[0],h-1-tip_xy[1])<=1:reasons.append('tip_truncated_by_image_border')
    if not hint_used and ambiguity<.1:reasons.append('tip_direction_ambiguous')
    if not observed:reasons.append('crease_not_observed_geometry_fallback')
    if full.sum()<100:reasons.append('too_small')
    return dict(mask=full,status='proposal_requires_review',bbox=bbox(full),axis_xy=axis.tolist(),tip_xy=tip_xy.tolist(),quality=quality|dict(reject_reasons=reasons,crease_observed=observed,axis_endpoint_ambiguity=ambiguity,RGB_tip_hint_used=hint_used,finger_mask_exterior_pixels=0),width_profile=dict(median_native=width/scale,length_native=length/scale,relative_iqr=float(np.subtract(*np.percentile(reference,[75,25]))/width),samples_native=(widths[::max(1,len(widths)//20)]/scale).tolist()),bottom_native_distance=(bottom-start)/scale,analysis_scale=scale,crease_candidates_native=[(p-start)/scale for p in possible])


def extract_pad_candidates(rgb,finger_masks,prepared_qualities=None,tip_hints=None):
    if rgb.dtype!=np.uint8 or rgb.ndim!=3 or rgb.shape[2]!=3:raise ValueError('Expected native uint8 RGB')
    start=time.perf_counter();rows=[];union=np.zeros(rgb.shape[:2],bool)
    if prepared_qualities is not None and len(prepared_qualities)!=len(finger_masks):raise ValueError('prepared_quality_count_mismatch')
    if tip_hints is not None and len(tip_hints)!=len(finger_masks):raise ValueError('tip_hint_count_mismatch')
    for i,finger in enumerate(finger_masks):
        if finger.shape!=rgb.shape[:2]:raise ValueError('finger_mask_shape_mismatch')
        r=extract_one(rgb,finger,None if prepared_qualities is None else prepared_qualities[i],None if tip_hints is None else tip_hints[i]);r['finger_id']=i
        if (union&r['mask']).any():r.update(mask=np.zeros_like(union),status='rejected',quality=r['quality']|dict(reject_reason='overlapping_pad_candidates'))
        r.setdefault('bbox',bbox(r['mask']));r.setdefault('axis_xy',None);r.setdefault('tip_xy',None);r.setdefault('width_profile',{})
        union|=r['mask'];rows.append(r)
    return dict(detector_version=VERSION,coordinate_system='encoded_original_pixels',mask=union,regions=rows,axis_pad_seconds=time.perf_counter()-start,approved_for_use=False)


def load_finger_masks(source,manifest):
    from PIL import Image
    start=time.perf_counter();data=json.loads(Path(manifest).read_text());expected=digest(source)
    with Image.open(source) as im:rgb=np.asarray(im.convert('RGB')).copy()
    if data.get('schema_version')!='sam-finger-input-v1':raise ValueError('SAM_schema_mismatch')
    if data.get('source_sha256')!=expected or data.get('coordinate_system')!='encoded_original_pixels' or (data.get('image_width'),data.get('image_height'))!=(rgb.shape[1],rgb.shape[0]):raise ValueError('SAM_source_geometry_or_hash_mismatch')
    masks=[]
    for row in data['masks']:
        name=row['mask_path']
        if Path(name).name!=name:raise ValueError('mask_path_not_relative')
        path=Path(manifest).parent/name
        if path.is_symlink() or digest(path)!=row['mask_sha256']:raise ValueError('SAM_mask_hash_mismatch')
        with Image.open(path) as im:
            if im.format!='PNG' or im.mode!='L' or im.size!=(rgb.shape[1],rgb.shape[0]):raise ValueError('SAM_mask_shape_mismatch')
            values=np.asarray(im).copy()
        if not np.isin(values,[0,255]).all():raise ValueError('SAM_mask_not_binary')
        masks.append(values==255)
    if digest(source)!=expected:raise ValueError('source_changed')
    return rgb,masks,dict(loading_seconds=time.perf_counter()-start,input_manifest=data)


def postprocess_fingers(masks):
    clean=[];qualities=[]
    for mask in masks:
        part,q=clean_mask(mask);clean.append(np.zeros_like(mask) if part is None else part);qualities.append(q)
    return clean,qualities


if __name__=='__main__':
    import argparse
    from PIL import Image
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--finger-manifest',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    rgb,masks,load=load_finger_masks(a.input,a.finger_manifest);result=extract_pad_candidates(rgb,masks,tip_hints=[r.get('tip_hint_native') for r in load['input_manifest']['masks']]);a.output.mkdir(parents=True,exist_ok=False);regions=[]
    for i,r in enumerate(result['regions']):
        name=f'pad_{i:03d}.png';Image.fromarray(r['mask'].astype(np.uint8)*255).save(a.output/name);regions.append({k:v for k,v in r.items() if k!='mask'}|dict(mask_path=name,mask_sha256=digest(a.output/name)))
    Image.fromarray(result['mask'].astype(np.uint8)*255).save(a.output/'pad_union.png')
    (a.output/'pad_candidates.json').write_text(json.dumps(dict(schema_version='sam-pad-candidates-v1',detector_version=VERSION,source_sha256=digest(a.input),image_width=rgb.shape[1],image_height=rgb.shape[0],coordinate_system='encoded_original_pixels',mask_path='pad_union.png',mask_sha256=digest(a.output/'pad_union.png'),status='review_required_not_protection_artifact',approved_for_use=False,regions=regions),indent=2))
