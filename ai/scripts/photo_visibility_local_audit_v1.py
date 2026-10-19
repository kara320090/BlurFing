"""Native-pixel failure measurements; human boxes are diagnostic-only inputs.

Gate failures are reproducible facts. Contrast, clipping and angular dispersion
are measurements, not automatic labels for blur, glare or anatomical curvature.
"""
from collections import Counter
import cv2
import numpy as np
from photo_visibility_gate_audit_v1 import validate


def local_audit(gray,support,evidence_box=None):
    validate(gray,support)
    h,w=gray.shape
    if evidence_box is not None:
        if not isinstance(evidence_box,(list,tuple)) or len(evidence_box)!=4 or any(type(v) is not int for v in evidence_box):
            raise ValueError('integer_local_evidence_box_required')
        x0,y0,x1,y1=evidence_box
        if not 0<=x0<x1<=w or not 0<=y0<y1<=h or not support[y0:y1,x0:x1].all():
            raise ValueError('evidence_box_must_be_inside_support')
    g=gray.astype(np.float32)
    gx=cv2.Sobel(g,cv2.CV_32F,1,0);gy=cv2.Sobel(g,cv2.CV_32F,0,1)
    xx=cv2.GaussianBlur(gx*gx,(0,0),3);yy=cv2.GaussianBlur(gy*gy,(0,0),3);xy=cv2.GaussianBlur(gx*gy,(0,0),3)
    coherence=np.hypot(xx-yy,2*xy)/(xx+yy+1e-6)
    py,px=np.indices((32,32),dtype=np.float64);px-=15.5;py-=15.5
    denominator=(px*px).sum();hann=np.outer(np.hanning(32),np.hanning(32))
    fy,fx=np.meshgrid(np.fft.fftfreq(32),np.fft.fftfreq(32),indexing='ij');radius=np.hypot(fx,fy)
    band=(radius>=.065)&(radius<=.30);wide=(radius>=.04)&(radius<=.46)
    windows=[]
    for y in range(0,h-31,16):
        for x in range(0,w-31,16):
            sl=np.s_[y:y+32,x:x+32]
            if support[sl].mean()<.8:continue
            patch=g[sl];residual=patch-patch.mean()-(patch*px).sum()/denominator*px-(patch*py).sum()/denominator*py
            power=np.abs(np.fft.fft2(residual*hann))**2;total=float(power.sum())
            peak=np.unravel_index(np.argmax(power*band),power.shape);f=float(radius[peak])
            radial=float(power[(np.abs(radius-f)<.025)&band].sum()/max(total,1e-6))
            wide_peak=np.unravel_index(np.argmax(np.where(wide,power,-1)),power.shape)
            wf=float(radius[wide_peak]);contrast=float(patch.std());co=float(np.median(coherence[sl]))
            failures=[key for key,valid in [('contrast',contrast>=8),('coherence',co>=.45),('radial_concentration',radial>=.4),('nonzero_energy',total>0)] if not valid]
            angles=.5*np.arctan2(2*xy[sl],xx[sl]-yy[sl]);weights=coherence[sl]
            angular_dispersion=float(1-abs((weights*np.exp(2j*angles)).sum())/max(float(weights.sum()),1e-6))
            inside=evidence_box is not None and x>=x0 and y>=y0 and x+32<=x1 and y+32<=y1
            windows.append(dict(xy=[x,y],inside_human_evidence=inside,contrast=contrast,coherence=co,
                plane_radial_concentration=radial,orientation_dispersion=angular_dispersion,
                dominant_residual_frequency=wf,dominant_outside_legacy_band=not .065<=wf<=.30,
                clipped_fraction=float(((patch<=2)|(patch>=253)).mean()),failures=failures))
    def summarize(items):
        return dict(windows=len(items),accepted=sum(not r['failures'] for r in items),
            failures=dict(Counter('+'.join(r['failures']) or 'accepted' for r in items)),
            one_gate_removed={key:sum(not any(k!=key for k in r['failures']) for r in items) for key in ['contrast','coherence','radial_concentration']},
            dominant_outside_legacy_band=sum(r['dominant_outside_legacy_band'] for r in items),
            quantiles_p10_p50_p90={key:np.percentile([r[key] for r in items],[10,50,90]).tolist() for key in ['contrast','coherence','plane_radial_concentration','orientation_dispersion','clipped_fraction']} if items else {})
    return dict(version='photo_visibility_local_audit_v1',native_shape=[h,w],all=summarize(windows),
        human_evidence=summarize([r for r in windows if r['inside_human_evidence']]),windows=windows,
        box_used_for_diagnostics_only=True,used_by_protection=False,measurements_are_not_causal_labels=True)
