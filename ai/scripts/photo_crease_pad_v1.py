"""Opt-in image-observed joint cut and semantic fingertip silhouette.

The old cap supplies an owner and an approximate distal axis only. The final
distal contour follows the observed finger BODY, not a fitted semicircle.
Transverse dark-line evidence locates the nearby joint; it is not human GT.
"""
import hashlib
import cv2
import numpy as np
from scipy import ndimage
from photo_rounded_pad_v1 import rounded_pads, _mask, _point
from photo_rounded_native_pipeline_v1 import protection_contexts

VERSION='observed_crease_distal_silhouette_v1_experimental'
CONFIG=dict(samples_per_width=192,search_proximal_widths=.65,search_distal_widths=.25,
    central_half_width=.38,max_slope=.8,slope_steps=33,max_curvature=1.2,curvature_steps=9,narrow_sigma_widths=.012,
    broad_sigma_widths=.075,minimum_dark_contrast=1.,minimum_prominence_mad=3.,
    minimum_positive_support=.65,crease_inclusion_widths=.02)


def _geometry(geometry):
    joint=_point(geometry['joint_xy']);axis=_point(geometry['axis_xy'])
    length=float(np.linalg.norm(axis));width=float(geometry['reference_width'])
    extent=float(geometry['distal_extent'])
    if not np.isfinite([length,width,extent]).all() or length<=0 or width<2 or extent<=0 or extent/width>8:
        raise ValueError('crease_geometry_contract')
    return joint,axis/length,width,extent


def observe_crease(rgb,owner,geometry):
    _mask(owner)
    if not isinstance(rgb,np.ndarray) or rgb.dtype!=np.uint8 or rgb.shape!=(*owner.shape,3):
        raise ValueError('crease_RGB_shape_contract')
    joint,axis,width,extent=_geometry(geometry)
    normal=np.array([-axis[1],axis[0]]);step=width/CONFIG['samples_per_width']
    u=np.arange(-.8*width,.8*width+step/2,step)
    t=np.arange(-1.5*width,extent+.2*width,step)
    xy=joint+u[None,:,None]*normal+t[:,None,None]*axis
    maps=xy.astype(np.float32)
    gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY).astype(np.float32)
    strip=cv2.remap(gray,maps[:,:,0],maps[:,:,1],cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT_101)
    support=cv2.remap(owner.astype(np.uint8),maps[:,:,0],maps[:,:,1],cv2.INTER_NEAREST,borderMode=cv2.BORDER_CONSTANT)>0
    narrow=cv2.GaussianBlur(strip,(0,0),CONFIG['narrow_sigma_widths']*width/step)
    broad=cv2.GaussianBlur(strip,(0,0),CONFIG['broad_sigma_widths']*width/step)
    dark=broad-narrow
    central=np.flatnonzero(np.abs(u)<=CONFIG['central_half_width']*width)
    cuts=np.arange(-CONFIG['search_proximal_widths']*width,CONFIG['search_distal_widths']*width+step/2,step)
    scores=[];candidates=[]
    for slope,curvature in [(s,c) for s in np.linspace(-CONFIG['max_slope'],CONFIG['max_slope'],CONFIG['slope_steps'])
                           for c in np.linspace(-CONFIG['max_curvature'],CONFIG['max_curvature'],CONFIG['curvature_steps'])]:
        lateral=u[central][None,:]
        positions=(cuts[:,None]+slope*lateral+curvature*lateral**2/width-t[0])/step
        indices=np.rint(positions).astype(int)
        valid=(indices>=0)&(indices<len(t));indices=np.clip(indices,0,len(t)-1)
        valid &= support[indices,central]
        values=np.where(valid,dark[indices,central],0.)
        median=np.median(values,axis=1)
        coverage=valid.mean(1);positive=np.sum((values>0)&valid,axis=1)/np.maximum(1,valid.sum(1))
        for k,cut in enumerate(cuts):
            if coverage[k]>=.9 and np.isfinite(median[k]):
                candidates.append((float(median[k]),float(cut),float(slope),float(positive[k]),float(curvature)))
                scores.append(float(median[k]))
    if not candidates:return dict(status='unobserved',reason='crease_cross_section_unavailable')
    score,cut,slope,positive,curvature=max(candidates,key=lambda x:(x[0],-abs(x[1]),-abs(x[2]),-abs(x[4])))
    center=float(np.median(scores));mad=float(np.median(np.abs(np.array(scores)-center)))*1.4826
    observed=score>=CONFIG['minimum_dark_contrast'] and score-center>=CONFIG['minimum_prominence_mad']*mad and positive>=CONFIG['minimum_positive_support']
    return dict(status='observed' if observed else 'unobserved',reason=None if observed else 'crease_evidence_insufficient',
        offset_native_pixels=cut,slope=slope,curvature=curvature,median_dark_contrast=score,background_score=center,
        background_mad=mad,positive_support=positive,search_interval_native=[float(cuts[0]),float(cuts[-1])],
        crease_inclusion_native_pixels=CONFIG['crease_inclusion_widths']*width,
        coordinate_system='native owner axis; positive toward fingertip',anatomical_boundary_verified=False)


def silhouette(owner,geometry,observation):
    _mask(owner)
    if observation.get('status')!='observed':raise ValueError('observed_crease_required')
    joint,axis,width,_=_geometry(geometry)
    normal=np.array([-axis[1],axis[0]])
    cut=float(observation['offset_native_pixels'])-float(observation['crease_inclusion_native_pixels'])
    slope=float(observation['slope'])
    curvature=float(observation.get('curvature',0))
    if not np.isfinite([cut,slope,curvature]).all():raise ValueError('crease_cut_contract')
    result=np.zeros_like(owner)
    for y0 in range(0,owner.shape[0],128):
        yy,xx=np.nonzero(owner[y0:y0+128]);yy+=y0
        delta=np.stack([xx-joint[0],yy-joint[1]],axis=1)
        lateral=delta@normal
        # Quadratic evidence is observed centrally. Outside that interval,
        # continue its tangent rather than allowing an unbounded parabola.
        edge=CONFIG['central_half_width']*width
        clipped=np.clip(lateral,-edge,edge)
        boundary=cut+slope*clipped+curvature*clipped**2/width
        boundary+=(lateral-clipped)*(slope+2*curvature*clipped/width)
        keep=delta@axis>=boundary
        result[yy[keep],xx[keep]]=True
    point=_point(geometry['tip_xy']);x,y=np.floor(point+.5).astype(int)
    if not (0<=x<owner.shape[1] and 0<=y<owner.shape[0] and result[y,x]):
        raise ValueError('crease_cut_excludes_tip')
    labels,count=ndimage.label(result);result=labels==labels[y,x]
    return result,dict(joint_xy=(joint+cut*axis).tolist(),axis_xy=axis.tolist(),
        cut_slope=slope,cut_curvature=curvature,distal_shape='observed_owner_silhouette',detached_components_removed=int(count-1))


def crease_pads(rgb,base,coarse,body,tip,*,pose_geometry=None):
    baseline,rounding=rounded_pads(base,coarse,body,tip,pose_geometry=pose_geometry)
    contexts=protection_contexts(body,tip,rounding,pose_geometry,complete_native_edges=True)
    output=np.zeros_like(body);rows=[]
    for previous,context in zip(rounding['candidates'],contexts):
        row=dict(previous);owner=context['body']
        if previous['status']!='rounded_cap_applied':
            row.update(status='base_retained',reason='crease_anchor_unavailable',after_pixels=0,
                unanchored_candidate_excluded=True,review_required=True)
            rows.append(row);continue
        observation=observe_crease(rgb,owner,previous['geometry'])
        row['crease_observation']=observation
        if observation['status']=='observed':
            cap,detail=silhouette(owner,previous['geometry'],observation)
            row.update(geometry=previous['geometry']|detail,after_pixels=int(cap.sum()),
                status='rounded_cap_applied',reason=None,base_preserved=False)
        else:
            cap=baseline&owner
            row.update(after_pixels=int(cap.sum()),boundary_fallback='previous_rounded_permission',review_required=True)
        output|=cap;rows.append(row)
    if np.any(output&~body):raise RuntimeError('crease_permission_outside_body')
    assigned=np.zeros_like(body)
    for context in contexts:assigned|=context['body']
    return output,dict(rounding,version=VERSION,base_geometry_version=rounding['version'],configuration=dict(CONFIG),candidates=rows,
        native_owner_edge_policy='unique_native_quantization_band_v1',
        excluded_unassigned_baseline_pixels=int((baseline&~assigned).sum()),
        excluded_unanchored_baseline_pixels=sum(r['before_pixels'] for r in rows if r.get('unanchored_candidate_excluded')),
        added_pixels=int((output&~baseline).sum()),removed_pixels=int((baseline&~output).sum()),
        observed_creases=sum(r.get('crease_observation',{}).get('status')=='observed' for r in rows),
        unobserved_creases=sum(r.get('crease_observation',{}).get('status')=='unobserved' for r in rows),
        input_RGB_sha256=hashlib.sha256(rgb.tobytes()).hexdigest(),
        anatomical_boundary_verified=False,whole_photo_protection_verified=False,review_required=True)
