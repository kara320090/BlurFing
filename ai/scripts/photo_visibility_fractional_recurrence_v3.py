"""Subpixel recurrence from raw profiles, an uncalibrated diagnostic primitive.

Parabolic interpolation estimates the location/value of observed correlation
peaks. It never generates ridge pixels or supplies a renderer pitch fallback.
"""
import numpy as np
from scipy import signal
from photo_visibility_repetition_probe_v2 import CONFIG


def _refined_peak(values, k):
    a,b,c = map(float,values[k-1:k+2])
    curvature = a-2*b+c
    delta = .5*(a-c)/curvature if curvature < -1e-12 else 0.
    delta = float(np.clip(delta,-.5,.5))
    height = b-.25*(a-c)*delta
    return float(k+delta),float(np.clip(height,-1.,1.))


def profile_recurrence(profile, proposed_period):
    d = np.diff(profile.astype(np.float64)); d -= d.mean()
    if np.mean(d*d) <= 2./12.:
        return None
    # Keep enough overlapping original samples for every tested displacement.
    max_lag = min(len(d)-4, int(np.ceil(2/CONFIG.min_frequency))+2)
    ac = np.zeros(max_lag+1)
    for lag in range(1,max_lag+1):
        a,b = d[:-lag],d[lag:]; a,b = a-a.mean(),b-b.mean()
        denominator = np.linalg.norm(a)*np.linalg.norm(b)
        ac[lag] = float(np.clip(a@b/denominator,-1.,1.)) if denominator>1e-12 else 0.
    peaks,_ = signal.find_peaks(ac)
    refined = [_refined_peak(ac,int(k)) for k in peaks if 1<k<max_lag]
    for period,first in sorted(refined,key=lambda p:abs(p[0]-proposed_period)):
        if first < CONFIG.min_recurrence or abs(period-proposed_period)/proposed_period > CONFIG.max_period_disagreement:
            continue
        if len(profile)/period < CONFIG.min_cycles:
            continue
        for second_lag,second in sorted(refined,key=lambda p:abs(p[0]-2*period)):
            if second < CONFIG.min_second_recurrence or len(d)-second_lag < period:
                continue
            # The two recurrences must describe the same period, not two
            # unrelated maxima that happen to have high correlation.
            if abs(second_lag-2*period)/(2*period) <= CONFIG.max_period_disagreement:
                return dict(period_pixels=period,recurrence=first,second_recurrence=second,
                            second_lag_pixels=second_lag,subpixel_method='parabolic_ACF_peak')
    return None
