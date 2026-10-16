"""Read-only spectral cross-check; never a replacement pitch or protection gate.

The FFT and ACF examine the same profile. Agreement is not independent
biometric evidence, and a dominant spectral peak need not be the fundamental
of a non-sinusoidal fingerprint. Bin differences expose ambiguity only.
"""
import numpy as np

VERSION='pitch_profile_spectrum_diagnostic_v1_experimental'


def diagnose_profile(profile,candidate_period=None):
    value=np.asarray(profile)
    if (value.ndim!=1 or not 8<=len(value)<=4096 or value.dtype.kind not in 'uif' or not np.isfinite(value).all()):
        raise ValueError('finite_real_profile_vector_required')
    if candidate_period is not None and (isinstance(candidate_period,(bool,np.bool_)) or
            not isinstance(candidate_period,(int,float,np.integer,np.floating)) or
            not np.isfinite(candidate_period) or candidate_period<=0):
        raise ValueError('positive_candidate_period_required')
    value=value.astype(np.float64);n=len(value);x=np.arange(n,dtype=np.float64)-(n-1)/2
    if not np.isfinite(value).all():raise ValueError('finite_float64_profile_required')
    if candidate_period is not None:
        candidate_period=float(candidate_period)
        if not np.isfinite(candidate_period) or not np.isfinite(n/candidate_period):
            raise ValueError('representable_candidate_frequency_required')
    # Normalize before subtraction, detrending and squaring to prevent finite
    # high/low amplitude input from overflowing or underflowing the FFT power.
    amplitude=float(np.abs(value).max())
    if amplitude>0:value=value/amplitude
    centered=value-value.mean();centered-=np.dot(centered,x)/np.dot(x,x)*x
    report=dict(version=VERSION,samples=n,status='diagnostic_only',candidate_period=candidate_period,
        dominant_spectral_period=None,dominant_bin=None,physical_DPI_known=False,
        fundamental_confirmed=False,independent_biometric_evidence=False,
        default_pitch_generated=False,protection_gate_modified=False)
    bound=np.finfo(np.float64).eps*32*n*max(1.,float(np.abs(value).max()))
    if float(np.abs(centered).max())<=bound:return report|dict(status='unavailable',reason='no_periodic_energy')
    power=np.abs(np.fft.rfft(centered*np.hanning(n)))**2;power[0]=0
    peak=int(np.argmax(power));total=float(power.sum())
    if peak==0 or total==0:return report|dict(status='unavailable',reason='no_periodic_energy')
    frequency=peak/n;period=1/frequency
    report.update(dominant_bin=peak,dominant_frequency=frequency,dominant_spectral_period=period,
        peak_power_fraction=float(power[peak]/total),frequency_bin_width=1/n,
        period_is_discrete_spectral_peak=True)
    if candidate_period is not None:
        ratio=float(candidate_period/period);harmonic=round(ratio)
        report.update(candidate_frequency_bin=float(n/candidate_period),
            candidate_nearest_bin=int(round(n/candidate_period)),
            candidate_bin_offset=int(round(n/candidate_period))-peak,
            candidate_to_spectral_period_ratio=ratio,
            longer_integer_harmonic_hypothesis=harmonic if harmonic>=2 else None,
            harmonic_hypothesis_relative_error=(float(abs(ratio-harmonic)/harmonic) if harmonic>=2 else None))
    return report
