"""Experimental crease-optional estimator. No GT or filename inputs.

Engineering cue agreement is NOT calibrated safety confidence. All output
remains review-only, including high-confidence proposals.
"""
import numpy as np
from sam_pad_detector import extract_pad_candidates,refine_edge_connected_foreground,clean_mask,bbox

POLICY=dict(confidence_min=.75,texture_relative_drop=.20,geometry_relative_change=.08,minimum_texture_energy=2.,window_width_fraction=.10)


def select_distal_extent(region):
    p=region.get('proximal_boundary');q=region['quality']
    if q.get('reject_reason'):return dict(source='rejected',confidence=0.,contributing_cues=[],reject_reason=q['reject_reason'],row=None)
    if p is None:return dict(source='rejected',confidence=0.,contributing_cues=[],reject_reason=q.get('reject_reason','axis_unstable'),row=None)
    sig={k:np.asarray(v,float) for k,v in p['signals'].items()};width=region['width_profile']['median_native']/p['analysis_to_native_scale'];window=max(3,round(POLICY['window_width_fraction']*width));lo,hi=p['search_rows'];origin=p['tip_axial_row']
    stable_tip=bool(q.get('RGB_tip_hint_used') or q.get('axis_endpoint_ambiguity',0)>=.1) and not any('tip_' in r for r in q.get('reject_reasons',[]))
    if q.get('crease_observed') and stable_tip:
        return dict(source='observed_crease_axis_width',confidence=.75,contributing_cues=['RGB_tip_or_cap','major_axis','width_distance_profile','observed_crease'],reject_reason=None,row=None,retain_existing_mask=True)
    possible=sorted(set(sum(p['diagnostic_peak_rows'].values(),[])));candidates=[]
    for row in possible:
        if row-window<max(origin,lo) or row+window>=hi:continue
        before=slice(row-window,row);after=slice(row,row+window)
        def delta(k):
            a=float(np.median(sig[k][before]));b=float(np.median(sig[k][after]));return (b-a)/max(abs(a),1e-6)
        energy=delta('texture_energy');coherence=delta('orientation_coherence');wc=delta('width');dc=delta('distance_width')
        texture=bool(np.median(sig['texture_energy'][before])>=POLICY['minimum_texture_energy'] and (energy<=-POLICY['texture_relative_drop'] or coherence<=-POLICY['texture_relative_drop']))
        geometry=bool(abs(wc)>=POLICY['geometry_relative_change'] and abs(dc)>=POLICY['geometry_relative_change'])
        crease=bool(sig['crease_response'][row]>=1.5 and sig['crease_coverage'][row]>=.5)
        groups=dict(tip_axis=stable_tip,texture_transition=texture,width_distance_change=geometry,crease=crease)
        confidence=sum(groups.values())/4
        eligible=stable_tip and texture and (geometry or crease) and confidence>=POLICY['confidence_min']
        candidates.append(dict(row=int(row),confidence=float(confidence),eligible=bool(eligible),contributing_cues=[k for k,v in groups.items() if v],relative_changes=dict(energy=energy,coherence=coherence,width=wc,distance_width=dc)))
    accepted=[r for r in candidates if r['eligible']]
    if not accepted:return dict(source='unobserved',confidence=max([r['confidence'] for r in candidates],default=0.),contributing_cues=(max(candidates,key=lambda r:r['confidence'])['contributing_cues'] if candidates else []),reject_reason='distal_extent_low_confidence',row=None,candidates=candidates)
    selected=max(accepted,key=lambda r:(r['confidence'],-r['row']))
    return selected|dict(source='multicue_distal_transition',reject_reason=None,candidates=candidates)


def estimate(rgb,finger_masks,tip_hints=None):
    baseline=extract_pad_candidates(rgb,finger_masks,tip_hints=tip_hints);union=np.zeros(rgb.shape[:2],bool)
    for region,finger in zip(baseline['regions'],finger_masks):
        decision=select_distal_extent(region);region['distal_estimator']=decision
        region.update(proximal_boundary_source=decision['source'],confidence=decision['confidence'],contributing_cues=decision['contributing_cues'],reject_reason=decision['reject_reason'])
        region['diagnostic_geometry_mask']=region['mask'].copy()
        if decision['reject_reason'] is not None:region['mask']=np.zeros_like(finger)
        elif decision.get('row') is not None:
            clean,q=clean_mask(finger)
            if clean is None:region['mask']=np.zeros_like(finger);decision['reject_reason']='foreground_unstable'
            else:
                clean,_=refine_edge_connected_foreground(rgb,clean);axis=np.asarray(region['axis_xy']);y,x=np.where(clean)
                minimum=float(np.min(x*axis[0]+y*axis[1]));p=region['proximal_boundary'];distance=(decision['row']-p['tip_axial_row'])*p['analysis_to_native_scale']
                yy,xx=np.indices(finger.shape);region['mask']=region['mask']&(xx*axis[0]+yy*axis[1]<=minimum+distance)
        if not region['mask'].any() and decision['reject_reason'] is None:
            decision.update(source='rejected',confidence=0.,contributing_cues=[],reject_reason='empty_distal_mask')
        region.update(proximal_boundary_source=decision['source'],confidence=decision['confidence'],contributing_cues=decision['contributing_cues'],reject_reason=decision['reject_reason'])
        assert not (region['mask']&~finger).any()
        region['bbox']=bbox(region['mask']);union|=region['mask']
    baseline.update(mask=union,detector_version='experimental_distal_pad_multicue_v1',approved_for_use=False,confidence_policy=POLICY)
    return baseline
