from itertools import combinations

from protect_visible_pad_checked_v2 import observed_seed_pitch

from visible_pad_scope_quality import propose_visible_pad

def agreeing_trials(trials):
    supported=set()
    for i,j in combinations(range(len(trials)),2):
        a,b=trials[i],trials[j]
        if not a['accepted'] or not b['accepted']:continue
        # Spatially distinct patches, with agreement in native pixel units.
        if abs(a['center_width_fraction']-b['center_width_fraction'])<.15-1e-8:continue
        median=(a['pitch_native']+b['pitch_native'])/2
        if abs(a['pitch_native']-b['pitch_native'])/median<=.15:supported.update([i,j])
    return sorted(supported)

def observe_fallback(image,candidate,primary):
    quality=primary['scope_quality'];meta=dict(candidate_id=candidate['candidate_id'],trials=[],
        matcher_scores_used=False,manual_reference_used=False,thresholds_relaxed=False,human_verified=False)
    if primary['pitch_native'] is not None or not quality.get('automatic_boundary_accepted',False):
        return None,meta|dict(status='fallback_not_eligible')
    width=quality['width'];tip=quality['tip_y'];bottom=quality['bottom_y']
    for trial in candidate['seed_trials']:
        box=trial['seed_roi'];pitch,measurement,_=observed_seed_pitch(image,box)
        scope,_,observed=propose_visible_pad(image,box)
        drift=None if scope is None else max(abs(observed['tip_y']-tip),abs(observed['bottom_y']-bottom))/width
        accepted=pitch is not None and scope is not None and drift<=.15
        meta['trials'].append(dict(**trial,pitch_native=pitch,pitch_measurement=measurement,
            scope_quality=observed,scope_drift_width_fraction=drift,accepted=accepted))
    support=agreeing_trials(meta['trials']);meta['consensus_trial_indices']=support
    if not support:return None,meta|dict(status='no_spatial_periodicity_consensus')
    selected=max((meta['trials'][i] for i in support),key=lambda t:t['texture_score'])
    return candidate|dict(seed_roi=selected['seed_roi'],seed_selection='two distinct distal patches with native pitch agreement <=15%; stable boundary'),meta|dict(status='observed_spatial_consensus',selected_roi=selected['seed_roi'])
