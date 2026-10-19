"""Diagnostic peak-train observation for nonuniform, low-contrast ridge texture.

Human boxes/labels are not inputs. Slow shading is removed for analysis only.
Several spectral hypotheses must be confirmed by extrema in two disjoint raw
image strips. Periodic non-fingerprint textures can still pass: not a classifier.
"""
from dataclasses import asdict,dataclass
from collections import Counter
import cv2
import numpy as np
from scipy import ndimage,signal
from photo_visibility_gate_audit_v1 import validate


@dataclass(frozen=True)
class PeakConfig:
    windows: tuple = (32,64)
    stride: int = 16
    min_frequency: float = .065
    max_frequency: float = .30
    min_ring_axial: float = .70
    min_peak_to_noise: float = 4.
    max_hypotheses: int = 3
    min_peaks: int = 4
    max_spacing_cv: float = .35
    max_period_disagreement: float = .20
    min_strip_agreement: float = .60
    prominence_std_fraction: float = .60
    min_connected_windows: int = 4


CONFIG=PeakConfig()


def peak_train(profile,proposed_period):
    """Track several raw crests/troughs without requiring a constant phase lag."""
    raw=profile.astype(np.float64)
    # Gaussian smoothing has no oscillating impulse response. Verify several
    # cycles, so a lone edge/crease plus its broad halo is not enough.
    residual=raw-ndimage.gaussian_filter1d(raw,proposed_period*1.5,mode='reflect')
    residual=ndimage.gaussian_filter1d(residual,.5,mode='reflect')
    std=float(residual.std())
    if std*std<=2./12.:return None
    prominence=max(2*np.sqrt(1./12.),CONFIG.prominence_std_fraction*std)
    distance=max(2,int(np.floor(proposed_period*.5)))
    peaks,_=signal.find_peaks(residual,prominence=prominence,distance=distance)
    troughs,_=signal.find_peaks(-residual,prominence=prominence,distance=distance)
    if len(peaks)<CONFIG.min_peaks:return None
    gaps=np.diff(peaks);period=float(np.median(gaps));cv=float(gaps.std()/gaps.mean())
    if abs(period-proposed_period)/proposed_period>CONFIG.max_period_disagreement or cv>CONFIG.max_spacing_cv:return None
    if any(not np.any((troughs>a)&(troughs<b)) for a,b in zip(peaks[:-1],peaks[1:])):return None
    return dict(period_pixels=period,peak_count=len(peaks),spacing_cv=cv,residual=residual)


def _geometry(n):
    fy,fx=np.meshgrid(np.fft.fftfreq(n),np.fft.fftfreq(n),indexing='ij')
    radius=np.hypot(fx,fy);band=(radius>=CONFIG.min_frequency)&(radius<=CONFIG.max_frequency)
    return np.outer(np.hanning(n),np.hanning(n)),fx,fy,radius,band


def inspect_patch(patch,geometry):
    n=patch.shape[0];hann,fx,fy,radius,band=geometry
    residual=patch-cv2.GaussianBlur(patch,(0,0),n/8,borderType=cv2.BORDER_REFLECT_101)
    if float(np.mean(residual**2))<=2./12.:return None,'quantization_floor'
    power=np.abs(np.fft.fft2(residual*hann))**2
    floor=max(float(np.median(power[band])),np.finfo(float).eps*max(float(power.sum()),1.))
    candidates=[]
    for index in np.argsort(np.where(band,power,-1).ravel())[::-1]:
        pos=np.unravel_index(index,power.shape)
        if not band[pos] or power[pos]/floor<CONFIG.min_peak_to_noise:break
        vector=np.array([fx[pos],fy[pos]])
        if any(min(np.linalg.norm(vector-v),np.linalg.norm(vector+v))<=1./n for _,v in candidates):continue
        candidates.append((pos,vector))
        if len(candidates)==CONFIG.max_hypotheses:break
    direction_pass=0
    for pos,vector in candidates:
        f=float(radius[pos]);theta=float(np.arctan2(vector[1],vector[0]));ring=band&(np.abs(radius-f)<1./n)
        angles=np.arctan2(fy[ring],fx[ring]);weights=power[ring]
        axial=float(abs(np.sum(weights*np.exp(2j*angles)))/max(float(weights.sum()),1e-12))
        if axial<CONFIG.min_ring_axial:continue
        direction_pass+=1;profiles=[]
        length=n-8;u=np.arange(length,dtype=np.float32)-(length-1)/2
        for offset in (-2.,2.):
            v=np.array([offset-1,offset,offset+1],dtype=np.float32)[:,None]
            mx=(n-1)/2+u[None,:]*np.cos(theta)-v*np.sin(theta)
            my=(n-1)/2+u[None,:]*np.sin(theta)+v*np.cos(theta)
            values=cv2.remap(patch.astype(np.float32),mx.astype(np.float32),my.astype(np.float32),interpolation=cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
            result=peak_train(values.mean(axis=0),1./f)
            if result is None:break
            profiles.append(result)
        if len(profiles)!=2:continue
        periods=[r['period_pixels'] for r in profiles]
        if abs(periods[0]-periods[1])/max(periods)>CONFIG.max_period_disagreement:continue
        a,b=[r['residual'] for r in profiles];a=a-a.mean();b=b-b.mean()
        agreement=float(np.clip(a@b/max(np.linalg.norm(a)*np.linalg.norm(b),1e-12),-1.,1.))
        if agreement<CONFIG.min_strip_agreement:continue
        return dict(working_period_pixels=float(np.mean(periods)),normal_angle_radians=theta,
                    ring_axial=axial,strip_agreement=agreement,
                    profiles=[{k:v for k,v in r.items() if k!='residual'} for r in profiles]),'accepted'
    return None,'raw_peak_train' if direction_pass else 'spectral_direction'


def probe_level(gray,support,max_side):
    validate(gray,support)
    if type(max_side) is not int or max_side<=0:raise ValueError('positive_integer_max_side_required')
    h,w=gray.shape;scale=min(1.,max_side/max(h,w));size=(max(1,round(w*scale)),max(1,round(h*scale)))
    small=cv2.resize(gray.astype(np.float64),size,interpolation=cv2.INTER_AREA)
    allowed=cv2.resize(support.astype(np.float64),size,interpolation=cv2.INTER_AREA)>=1.-1e-12
    scales=[]
    for n in CONFIG.windows:
        xs=list(range(0,size[0]-n+1,CONFIG.stride));ys=list(range(0,size[1]-n+1,CONFIG.stride))
        accepted=np.zeros((len(ys),len(xs)),bool);counts=Counter();samples=[];geometry=_geometry(n)
        for iy,y in enumerate(ys):
            for ix,x in enumerate(xs):
                sl=np.s_[y:y+n,x:x+n]
                if not allowed[sl].all():continue
                value,reason=inspect_patch(small[sl],geometry);counts[reason]+=1
                if value is not None:
                    accepted[iy,ix]=True;samples.append(dict(working_xy=[x,y],window=n,**value))
        labels,count=ndimage.label(accepted,structure=np.ones((3,3),np.uint8));sizes=np.bincount(labels.ravel(),minlength=count+1);sizes[0]=0
        scales.append(dict(window=n,eligible_windows=sum(counts.values()),credible_windows=int(accepted.sum()),
                           largest_connected_windows=int(sizes.max()),reasons=dict(counts),samples=samples))
    return dict(version='photo_visibility_peak_train_probe_v4',config=asdict(CONFIG),working_shape=[size[1],size[0]],
                actual_resize_yx=[size[1]/h,size[0]/w],scales=scales,
                candidate_signal_observed=any(s['largest_connected_windows']>=CONFIG.min_connected_windows for s in scales),
                automatic_visibility='uncertain',calibrated_visibility_probability=None,used_by_protection=False,
                renderer_binding_allowed=False,absence_inferred_from_failure=False,support_is_visibility_GT=False)
