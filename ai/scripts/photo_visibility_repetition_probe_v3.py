"""V3 raw repetition experiment with subpixel ACF; not a visibility classifier.

A frequency peak proposes a direction. Two profiles from unenhanced pixels must
then show recurrence at both one and two periods. Broad shading need not lose an
energy competition against the ridges. This still cannot distinguish every
periodic skin crease or textile from a fingerprint. No output binds a renderer.
"""
from dataclasses import asdict, dataclass

import cv2
import numpy as np
from scipy import ndimage, signal

from photo_visibility_gate_audit_v1 import validate


@dataclass(frozen=True)
class RepetitionConfig:
    windows: tuple = (32, 64)
    stride: int = 16
    min_frequency: float = .065
    max_frequency: float = .30
    min_ring_axial_concentration: float = .70
    min_peak_to_noise: float = 4.
    min_recurrence: float = .60
    min_second_recurrence: float = .50
    min_cycles: float = 3.
    max_period_disagreement: float = .20
    min_connected_windows: int = 4


CONFIG = RepetitionConfig()


from photo_visibility_fractional_recurrence_v3 import profile_recurrence as _profile_recurrence


def _geometry(n):
    y, x = np.indices((n,n), dtype=np.float64)
    x -= (n-1)/2; y -= (n-1)/2
    fy, fx = np.meshgrid(np.fft.fftfreq(n), np.fft.fftfreq(n), indexing='ij')
    radius = np.hypot(fx,fy)
    band = (radius >= CONFIG.min_frequency) & (radius <= CONFIG.max_frequency)
    return x, y, np.outer(np.hanning(n), np.hanning(n)), fx, fy, radius, band


def _patch(patch, geometry):
    n = patch.shape[0]
    x, y, hann, fx, fy, radius, band = geometry
    denominator = (x*x).sum()
    residual = patch-patch.mean()-(patch*x).sum()/denominator*x-(patch*y).sum()/denominator*y
    if np.mean(residual**2) <= 2./12.:
        return None, 'quantization_floor'
    power = np.abs(np.fft.fft2(residual*hann))**2
    peak = np.unravel_index(np.argmax(np.where(band,power,-1)), power.shape)
    f = float(radius[peak]); theta = float(np.arctan2(fy[peak],fx[peak]))
    floor = max(float(np.median(power[band])), np.finfo(float).eps*max(float(power.sum()),1.))
    peak_to_noise = float(power[peak]/floor)
    ring = band & (np.abs(radius-f) < 1./n)
    angles = np.arctan2(fy[ring],fx[ring]); weights = power[ring]
    axial = float(abs(np.sum(weights*np.exp(2j*angles)))/max(float(weights.sum()),1e-12))
    if peak_to_noise < CONFIG.min_peak_to_noise or axial < CONFIG.min_ring_axial_concentration:
        return None, 'spectral_direction'
    # Every coordinate fits inside this fully supported patch at any angle.
    length = n-8
    u = np.arange(length,dtype=np.float32)-(length-1)/2
    profiles = []
    for offset in (-2., 2.):
        v = np.array([offset-1,offset,offset+1],dtype=np.float32)[:,None]
        mx = (n-1)/2+u[None,:]*np.cos(theta)-v*np.sin(theta)
        my = (n-1)/2+u[None,:]*np.sin(theta)+v*np.cos(theta)
        values = cv2.remap(patch.astype(np.float32),mx.astype(np.float32),my.astype(np.float32),
                           interpolation=cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
        result = _profile_recurrence(values.mean(axis=0),1./f)
        if result is None:
            return None, 'raw_profile_recurrence'
        profiles.append(result)
    periods = [r['period_pixels'] for r in profiles]
    if abs(periods[0]-periods[1])/max(periods) > CONFIG.max_period_disagreement:
        return None, 'profile_disagreement'
    return dict(working_period_pixels=float(np.mean(periods)),
                normal_angle_radians=theta, ring_axial_concentration=axial,
                peak_to_noise=peak_to_noise, profiles=profiles), 'accepted'


def probe_level(gray, support, max_side):
    validate(gray,support)
    if type(max_side) is not int or max_side <= 0:
        raise ValueError('positive_integer_max_side_required')
    h,w = gray.shape; scale = min(1.,max_side/max(h,w))
    size = (max(1,round(w*scale)),max(1,round(h*scale)))
    small = cv2.resize(gray.astype(np.float64),size,interpolation=cv2.INTER_AREA)
    # An AREA-resized pixel may mix both sides of a NEAREST mask boundary.
    # Only footprints entirely inside support may supply raw profile evidence.
    allowed = cv2.resize(support.astype(np.float64),size,interpolation=cv2.INTER_AREA) >= 1.-1e-12
    scales = []
    for n in CONFIG.windows:
        ys = list(range(0,size[1]-n+1,CONFIG.stride)); xs = list(range(0,size[0]-n+1,CONFIG.stride))
        accepted = np.zeros((len(ys),len(xs)),bool); counts = {}; samples = []
        geometry = _geometry(n)
        for iy,y in enumerate(ys):
            for ix,x in enumerate(xs):
                sl = np.s_[y:y+n,x:x+n]
                if not allowed[sl].all():
                    continue
                result,reason = _patch(small[sl],geometry)
                counts[reason] = counts.get(reason,0)+1
                if result is not None:
                    accepted[iy,ix] = True
                    samples.append(dict(working_xy=[x,y],window=n,**result))
        labels,count = ndimage.label(accepted,structure=np.ones((3,3),np.uint8))
        sizes = np.bincount(labels.ravel(),minlength=count+1); sizes[0] = 0
        scales.append(dict(window=n,eligible_windows=sum(counts.values()),reasons=counts,
                           credible_windows=int(accepted.sum()),largest_connected_windows=int(sizes.max()),samples=samples))
    return dict(version='photo_visibility_repetition_probe_v3',config=asdict(CONFIG),
                working_shape=[size[1],size[0]],actual_resize_yx=[size[1]/h,size[0]/w],scales=scales,
                candidate_signal_observed=any(r['largest_connected_windows']>=CONFIG.min_connected_windows for r in scales),
                automatic_visibility='uncertain',calibrated_visibility_probability=None,
                used_by_protection=False,renderer_binding_allowed=False,
                support_is_visibility_GT=False,absence_inferred_from_failure=False)
