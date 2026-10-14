"""Synthetic isolated-API support probe, not whole-pipeline protection evidence."""
import json
import numpy as np
from contactless_ridge_pitch import estimate_ridge_pitch
from photo_local_periodicity_v1 import observe


def fixture(centers,period):
    y,x=np.indices((512,512));mask=np.zeros((512,512),bool)
    for cy,cx in centers:mask[cy-24:cy+24,cx-24:cx+24]=True
    gray=np.rint(128+90*np.cos(2*np.pi*x/period)).astype(np.uint8)
    gray[mask]=128 # no periodicity in the actual target
    return gray,mask


def probe():
    rows=[]
    for period in [6,8]:
        gray,mask=fixture([(y,x) for y in [96,240] for x in [96,240,384]],period)
        original=estimate_ridge_pitch(gray,mask)
        local_gray,local_mask=fixture([(y,x) for y in [100,228] for x in [100,228,356]],period)
        local=observe(local_gray,local_mask)
        rows.append(dict(periodic_background_pixels=period,target_periodicity=None,
            original_isolated_API=dict(status=original['status'],pitch=original['pitch'],count=original['count']),
            local_isolated_API=dict(status=local['status'],spacing=local['periodic_spacing_native_pixels'],
                stage_counts=local['stage_counts']),
            fixture_centers_aligned_to_each_observers_own_grid=True))
    return dict(schema_version='ridge-profile-support-probe-v1',rows=rows,synthetic_only=True,
        validation_scope='isolated function contracts, not whole frozen pipeline',
        frozen_source_changed=False,protection_success_or_failure_proven=False,
        local_support_policy='existing 95% remapped profile coverage; not complete exclusion of background influence')


if __name__=='__main__':print(json.dumps(probe(),indent=2,allow_nan=False))
