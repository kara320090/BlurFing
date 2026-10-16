"""Bounded RGB edge refinement of already anchored distal finger silhouettes.

No new finger is discovered. Only the uncertain band around the original BODY
can change, in each anchored distal window. Original semantics are retained as
provenance; this result must not be described as raw COLFISPOOF class output.
"""
import hashlib
import cv2
import numpy as np
from photo_rounded_pad_v1 import _mask
from photo_crease_pad_v1 import _geometry

VERSION='bounded_RGB_body_edges_v1_experimental'
CONFIG=dict(inside_band_widths=.035,outside_band_widths=.12,
            proximal_extent_widths=.8,lateral_extent_widths=.85,
            distal_margin_widths=.2,iterations=3,rng_seed=0,max_window_pixels=4_000_000)


def refine_body(rgb,body,rounding):
    _mask(body)
    if not isinstance(rgb,np.ndarray) or rgb.dtype!=np.uint8 or rgb.shape!=(*body.shape,3):
        raise ValueError('RGB_body_refinement_shape_contract')
    result=body.copy();rows=[]
    for candidate in rounding['candidates']:
        if candidate['status']!='rounded_cap_applied':continue
        joint,axis,width,extent=_geometry(candidate['geometry'])
        normal=np.array([-axis[1],axis[0]])
        corners=np.array([joint+u*normal+t*axis for u in [-.85*width,.85*width]
                          for t in [-.8*width,extent+.2*width]])
        x0,y0=np.maximum(0,np.floor(corners.min(0)).astype(int)-2)
        x1,y1=np.minimum([body.shape[1],body.shape[0]],np.ceil(corners.max(0)).astype(int)+3)
        if (x1-x0)*(y1-y0)>CONFIG['max_window_pixels']:
            rows.append(dict(candidate_id=candidate['candidate_id'],status='unchanged_window_resource_limit'));continue
        local=body[y0:y1,x0:x1].astype(np.uint8)
        inside=max(2,round(CONFIG['inside_band_widths']*width))
        outside=max(2,round(CONFIG['outside_band_widths']*width))
        eroded=cv2.erode(local,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(2*inside+1,2*inside+1)))>0
        dilated=cv2.dilate(local,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(2*outside+1,2*outside+1)))>0
        if not eroded.any() or dilated.all():
            rows.append(dict(candidate_id=candidate['candidate_id'],status='unchanged_seed_unavailable'));continue
        seeds=np.where(local,cv2.GC_PR_FGD,cv2.GC_PR_BGD).astype(np.uint8)
        seeds[eroded]=cv2.GC_FGD;seeds[~dilated]=cv2.GC_BGD
        bg=np.zeros((1,65),np.float64);fg=np.zeros((1,65),np.float64)
        # Explicit seed makes OpenCV's initial GMM k-means reproducible within
        # this runtime. No cross-platform equivalence is asserted.
        cv2.setRNGSeed(CONFIG['rng_seed'])
        cv2.grabCut(np.ascontiguousarray(rgb[y0:y1,x0:x1]),seeds,None,bg,fg,CONFIG['iterations'],cv2.GC_INIT_WITH_MASK)
        inferred=np.isin(seeds,[cv2.GC_FGD,cv2.GC_PR_FGD])
        yy,xx=np.mgrid[y0:y1,x0:x1];dx=xx-joint[0];dy=yy-joint[1]
        t=dx*axis[0]+dy*axis[1];u=dx*normal[0]+dy*normal[1]
        eligible=(t>=-.8*width)&(t<=extent+.2*width)&(np.abs(u)<=.85*width)
        band=eligible&dilated&~eroded
        result[y0:y1,x0:x1][band]=inferred[band]
        rows.append(dict(candidate_id=candidate['candidate_id'],status='RGB_boundary_refined',
            bbox=[int(x0),int(y0),int(x1),int(y1)],inside_band_pixels=inside,outside_band_pixels=outside,
            changed_pixels=int(np.count_nonzero((inferred!=local.astype(bool))&band))))
    return result,dict(version=VERSION,configuration=dict(CONFIG),candidates=rows,
        input_RGB_sha256=hashlib.sha256(rgb.tobytes()).hexdigest(),
        original_body_pixel_sha256=hashlib.sha256(body.tobytes()).hexdigest(),
        refined_body_pixel_sha256=hashlib.sha256(result.tobytes()).hexdigest(),
        added_pixels=int((result&~body).sum()),removed_pixels=int((body&~result).sum()),
        anatomical_boundary_verified=False,review_required=True)
