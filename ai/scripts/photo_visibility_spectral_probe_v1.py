"""Experimental low-contrast ridge-like signal probe, never a protection gate.

Linear illumination is removed from raw patches. Spectral concentration and
noise-relative evidence replace absolute brightness amplitude in this separate
experiment. No labels, evidence boxes, image names, or learned weights are inputs.
Passing is not a fingerprint identity, visibility probability, or privacy proof.
"""
from dataclasses import asdict, dataclass

import cv2
import numpy as np
from scipy import ndimage

from photo_visibility_gate_audit_v1 import validate


@dataclass(frozen=True)
class ProbeConfig:
    # Frequency range matches the earlier engineering probe. Concentration .70
    # comes from the existing highres quality defaults, not this label set.
    window: int = 32
    stride: int = 16
    min_frequency: float = .065
    max_frequency: float = .30
    min_band_energy: float = .70
    min_axial_concentration: float = .70
    min_radial_concentration: float = .70
    min_peak_to_noise: float = 4.0  # 6 dB relative to median in-band power.
    min_connected_windows: int = 4


CONFIG = ProbeConfig()


def probe_level(gray, support, max_side):
    validate(gray, support)
    if type(max_side) is not int or max_side <= 0:
        raise ValueError('positive_integer_max_side_required')
    c = CONFIG; h, w = gray.shape; scale = min(1., max_side/max(h,w))
    shape = (max(1, round(w*scale)), max(1, round(h*scale)))
    small = cv2.resize(gray, shape, interpolation=cv2.INTER_AREA).astype(np.float64)
    allowed = cv2.resize(support.astype(np.uint8), shape, interpolation=cv2.INTER_NEAREST)>0
    n = c.window
    yy, xx = np.indices((n,n), dtype=np.float64); xx -= (n-1)/2; yy -= (n-1)/2
    denom = float((xx*xx).sum()); hann = np.outer(np.hanning(n),np.hanning(n))
    fy, fx = np.meshgrid(np.fft.fftfreq(n), np.fft.fftfreq(n), indexing='ij')
    radius = np.hypot(fx,fy); angle = np.arctan2(fy,fx)
    band = (radius>=c.min_frequency)&(radius<=c.max_frequency)
    active = radius > 0
    xs=list(range(0,shape[0]-n+1,c.stride)); ys=list(range(0,shape[1]-n+1,c.stride))
    accepted = np.zeros((len(ys),len(xs)),bool); samples=[]; eligible=0
    for iy,y in enumerate(ys):
        for ix,x in enumerate(xs):
            sl=np.s_[y:y+n,x:x+n]
            if not allowed[sl].all(): continue  # No background entering a window.
            eligible += 1
            patch=small[sl]
            residual=patch-patch.mean()-(patch*xx).sum()/denom*xx-(patch*yy).sum()/denom*yy
            # Two quantization-noise variances; this is not a learned contrast gate.
            if float(np.mean(residual**2)) <= 2./12.: continue
            power=np.abs(np.fft.fft2(residual*hann))**2
            total=float(power[active].sum()); band_power=float(power[band].sum())
            if total<=0 or band_power<=0: continue
            energy=band_power/total
            axial=float(np.hypot((power[band]*np.cos(2*angle[band])).sum(),
                                 (power[band]*np.sin(2*angle[band])).sum())/band_power)
            peak=np.unravel_index(np.argmax(np.where(band,power,-1)),power.shape)
            peak_frequency=float(radius[peak])
            ring=band & (np.abs(radius-peak_frequency)<1./n)
            radial=float(power[ring].sum()/band_power)
            floor=float(np.median(power[band]))
            peak_to_noise=float(power[peak]/max(floor,np.finfo(np.float64).eps*max(total,1.)))
            valid=energy>=c.min_band_energy and axial>=c.min_axial_concentration and radial>=c.min_radial_concentration and peak_to_noise>=c.min_peak_to_noise
            if valid:
                accepted[iy,ix]=True
                samples.append(dict(grid_xy=[ix,iy],working_xy=[x,y],band_energy=energy,axial_concentration=axial,
                    radial_concentration=radial,peak_to_noise=peak_to_noise,working_period_pixels=1./peak_frequency))
    clusters,count=ndimage.label(accepted,structure=np.ones((3,3),np.uint8))
    sizes=np.bincount(clusters.ravel(),minlength=count+1); sizes[0]=0
    largest=int(sizes.max())
    signal=largest>=c.min_connected_windows
    return dict(version='photo_visibility_spectral_probe_v1',config=asdict(c),
        working_shape=[shape[1],shape[0]],actual_resize_yx=[shape[1]/h,shape[0]/w],
        eligible_windows=eligible,credible_windows=int(accepted.sum()),largest_connected_windows=largest,
        candidate_signal_observed=signal,samples=samples,
        automatic_visibility='uncertain',calibrated_visibility_probability=None,
        used_by_protection=False,renderer_binding_allowed=False,
        support_is_visibility_GT=False,absence_inferred_from_failure=False)
