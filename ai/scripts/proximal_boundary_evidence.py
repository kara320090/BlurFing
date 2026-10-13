"""RGB-only axial proximal-boundary evidence; no GT, filenames or runtime APIs.

Confidence is cue agreement, not a calibrated probability. Width and distance
transform are correlated and must not on their own authorize a boundary.
"""
import cv2
import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks


def observe_proximal_boundary(gray,mask,widths,start,end,width,crease,coverage,chroma_margin=None):
    rows=len(widths);dt=cv2.distanceTransform(mask.astype(np.uint8),cv2.DIST_L2,5)
    gx=cv2.Sobel(gray,cv2.CV_32F,1,0);gy=cv2.Sobel(gray,cv2.CV_32F,0,1)
    high=gray-cv2.GaussianBlur(gray,(0,0),max(1.,.015*width))
    signals={k:np.zeros(rows,float) for k in ['distance_width','gray_gradient','texture_energy','orientation_coherence','frequency_cycles_per_analysis_px','mask_confidence','skin_background_chroma_margin']}
    for row in range(start,end+1):
        xx=np.flatnonzero(mask[row])
        if len(xx)<8:continue
        a,b=np.percentile(xx,[20,80]).astype(int);sl=slice(a,b+1)
        signals['distance_width'][row]=2*float(dt[row].max())
        signals['gray_gradient'][row]=float(np.median(np.abs(gy[row,sl])))
        signals['texture_energy'][row]=float(np.median(np.abs(high[row,sl])))
        signals['mask_confidence'][row]=float(mask[row,sl].mean())
        if chroma_margin is not None:signals['skin_background_chroma_margin'][row]=float(np.median(chroma_margin[row,sl])) # support occupancy, not model probability
        jxx=float(np.mean(gx[row,sl]**2));jyy=float(np.mean(gy[row,sl]**2));jxy=float(np.mean(gx[row,sl]*gy[row,sl]))
        signals['orientation_coherence'][row]=float(np.hypot(jxx-jyy,2*jxy)/(jxx+jyy+1e-6))
        patch=high[max(start,row-8):min(end+1,row+9),sl]
        if min(patch.shape)>=8:
            spectrum=np.abs(np.fft.rfft2(patch-patch.mean()))**2
            fy=np.fft.fftfreq(patch.shape[0])[:,None];fx=np.fft.rfftfreq(patch.shape[1])[None,:];radius=np.hypot(fx,fy)
            allowed=(radius>=.04)&(radius<=.4)
            if allowed.any() and spectrum.max()>0:
                index=np.unravel_index(np.argmax(spectrum*allowed),spectrum.shape);signals['frequency_cycles_per_analysis_px'][row]=float(radius[index])
    smooth_width=gaussian_filter1d(widths.astype(float),max(1,.04*width));derivative=np.gradient(smooth_width)
    for k in signals:signals[k]=gaussian_filter1d(signals[k],max(1,.025*width))
    lo=max(start,round(start+1.1*width));hi=min(end,round(start+2.4*width));window=max(3,round(.15*width));candidates=[]
    valley_candidates=[]
    # Small tilted transects retain evidence from a slightly oblique crease.
    smooth=cv2.GaussianBlur(gray,(0,0),max(1.,.025*width))
    residual=cv2.GaussianBlur(smooth,(1,0),sigmaX=0,sigmaY=max(2.,.18*width))-smooth
    for slope in [-.2,-.1,0.,.1,.2]:
        trace=np.zeros(rows);support=np.zeros(rows)
        if slope==0:trace=crease.copy();support=coverage.copy()
        else:
            for row in range(max(start,lo),min(end,hi)+1):
                xx=np.flatnonzero(mask[row])
                if len(xx)<8:continue
                a,b=np.percentile(xx,[20,80]).astype(int);x=np.arange(a,b+1);y=np.rint(row+slope*(x-(a+b)/2)).astype(int)
                inside=(y>=start)&(y<=end);x=x[inside];y=y[inside]
                if not len(x) or mask[y,x].mean()<.9:continue
                v=residual[y,x];trace[row]=float(np.median(v));support[row]=float(np.mean(v>2))
        peaks,_=find_peaks(trace,prominence=1.5,distance=max(2,round(.25*width)))
        valley_candidates.extend((int(row),float(slope),float(trace[row]),float(support[row])) for row in peaks if lo<=row<=hi)
    # Crease plus an independent appearance transition, optionally geometry.
    for row,slope,valley_strength,valley_coverage in valley_candidates:
        if not lo<=row<=hi or row-window<start or row+window>end:continue
        before=slice(row-window,row);after=slice(row,row+window)
        def change(v):
            x=float(np.median(v[before]));y=float(np.median(v[after]));return (y-x)/max(abs(x),1e-6)
        energy_change=change(signals['texture_energy']);coherence_change=change(signals['orientation_coherence']);width_change=change(smooth_width);dt_change=change(signals['distance_width'])
        cues=dict(crease=bool(valley_strength>=1.5 and valley_coverage>=.5),ridge_energy_drop=bool(energy_change<=-.35 and np.median(signals['texture_energy'][before])>=2),coherence_drop=bool(coherence_change<=-.25),width_change=bool(abs(width_change)>=.1),distance_width_change=bool(abs(dt_change)>=.1))
        appearance=cues['ridge_energy_drop'] or cues['coherence_drop'];geometry=cues['width_change'] or cues['distance_width_change']
        accepted=cues['crease'] and appearance
        confidence=(float(cues['crease'])+float(appearance)+float(geometry))/3
        candidates.append(dict(row=int(row),slope=slope,valley_strength=valley_strength,valley_coverage=valley_coverage,confidence=confidence,accepted=bool(accepted),cues=cues,energy_relative_change=energy_change,coherence_relative_change=coherence_change,width_relative_change=width_change,distance_width_relative_change=dt_change))
    diagnostic_peaks={}
    for name,values in [('width_derivative',np.abs(derivative)),('distance_width_derivative',np.abs(np.gradient(signals['distance_width']))),('gray_gradient',signals['gray_gradient']),('dark_valley',crease),('texture_energy_derivative',np.abs(np.gradient(signals['texture_energy']))),('coherence_derivative',np.abs(np.gradient(signals['orientation_coherence']))),('frequency_derivative',np.abs(np.gradient(signals['frequency_cycles_per_analysis_px'])))]:
        peaks,_=find_peaks(values,distance=max(2,round(.1*width)))
        possible=[int(p) for p in peaks if lo<=p<=hi]
        diagnostic_peaks[name]=sorted(possible,key=lambda p:(-values[p],p))[:3]
    accepted=[q for q in candidates if q['accepted']];chosen=max(accepted,key=lambda q:(q['confidence'],-q['row'])) if accepted else None
    return dict(observed=chosen is not None,selected_row=None if chosen is None else chosen['row'],confidence=0. if chosen is None else chosen['confidence'],source='OBSERVED_PROXIMAL_BOUNDARY' if chosen else 'unobserved',reject_reason=None if chosen else 'proximal_boundary_unobserved',candidates=candidates,diagnostic_peak_rows=diagnostic_peaks,signals=dict(width=widths.tolist(),width_derivative=derivative.tolist(),crease_response=crease.tolist(),crease_coverage=coverage.tolist(),**{k:v.tolist() for k,v in signals.items()}),search_rows=[lo,hi],tip_axial_row=int(start),confidence_semantics='cue agreement, not probability; mask_confidence is support occupancy; chroma margin is an uncalibrated RGB proxy',signal_units='analysis_pixels; frequency cycles/analysis_pixel; derivatives per axial row')
