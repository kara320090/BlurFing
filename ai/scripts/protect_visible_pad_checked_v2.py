import cv2

from fingerprint_poc_core import prepare_fingerprint

from protect_contactless_delta import normalize_contactless

from contactless_ridge_pitch import estimate_ridge_pitch

from single_ridge_naturalizer_v2 import select_observed_pitch

from diagnose_ridge_measurement_noise import two_scale_measurement

def observed_seed_pitch(original,box):
    a,b,c,d=box;gray=cv2.cvtColor(original[b:d,a:c],cv2.COLOR_RGB2GRAY)
    raw=cv2.resize(gray,(512,512),interpolation=cv2.INTER_CUBIC if len(gray)<512 else cv2.INTER_AREA)
    try:mask=prepare_fingerprint(normalize_contactless(raw))[0]['roi']
    except ValueError as exc:
        if not any(s in str(exc) for s in ['No fingerprint ROI found','No ridge skeleton found','No refined ridge skeleton found']):raise
        return None,dict(status='no_ridges',reason=str(exc)),raw
    attempts=[]
    for label,frame in [('Raw',raw),('Bilateral5_8_3',cv2.bilateralFilter(raw,5,8,3))]:
        measurement=estimate_ridge_pitch(frame,mask);selected=select_observed_pitch(measurement)
        attempts.append(dict(preprocessing=label,measurement=measurement,selection=selected))
        if selected['pitch'] is not None:return selected['pitch']*(c-a)/512,dict(attempts=attempts,selected=label,pitch512=selected['pitch']),raw
    measurement=two_scale_measurement(raw,mask);attempts.append(dict(preprocessing='TwoScaleGaussian1.2_1.8',measurement=measurement))
    pitch=measurement['pitch']
    return None if pitch is None else pitch*(c-a)/512,dict(attempts=attempts,selected=None if pitch is None else 'TwoScaleGaussian1.2_1.8',pitch512=pitch),raw
