"""Automatic observed-ridge transformation PoC; never claims protection.

This separate functional API does not replace the checked protection API.
Naturalness ratings and cross-capture protection evaluation remain separate.
"""

import hashlib

import subprocess

import numpy as np

from automatic_fingertip_proposals import detect_fingertips

from protect_visible_pad_checked_v2 import observed_seed_pitch

from visible_pad_scope_quality import propose_visible_pad

from automatic_ridge_consensus import observe_fallback

from whole_pad_skin_relief import render_whole_pad_candidate

from fingerprint_structure_check import check_structure_change

from fingerprint_topology import validate_strength

def transform_fingerprint_photo(image,strength=.5,*,return_details=True):
    if not isinstance(return_details,(bool,np.bool_)):raise ValueError('Boolean return_details required')
    if isinstance(strength,(bool,np.bool_)):raise ValueError('Numeric strength required')
    strength=validate_strength(strength)
    if strength not in (0.,.5):raise ValueError('Supported prototype strengths: 0 or 0.5')
    detection=detect_fingertips(image);original=np.asarray(image);output=original.copy();occupied=np.zeros(original.shape[:2],bool)
    meta=dict(method='automatic_structure_transform_skin_relief_v4',strength=strength,detection=detection,regions=[],applied=False,
        transformation_function_passed=False,protection_verified=False,privacy_validated=False,human_naturalness_validated=False,
        human_ridge_confirmation=False,manual_coordinates_used=False,joint_region_protected=False,
        undetected_fingertips_possible=True,full_photo_privacy_validated=False,
        default_protection_api_replaced=False,other_captures_required_for_protection_evidence=True,
        matcher_scores_used_to_select_roi_or_renderer=False)
    def finish(status):
        meta.update(status=status,changed_pixels=int(np.count_nonzero(np.any(output!=original,axis=2))),
            transformed_candidate_count=sum(r.get('applied',False) for r in meta['regions']),outside_all_masks_preserved=bool(np.array_equal(output[~occupied],original[~occupied])))
        meta['applied']=meta['transformed_candidate_count']>0;meta['transformation_function_passed']=meta['applied']
        meta['all_detected_candidates_transformed']=bool(meta['regions']) and all(r.get('applied',False) for r in meta['regions'])
        if not return_details and strength>0 and not meta['applied']:raise RuntimeError('No fingertip transformation; request details for skipped status')
        return (output,meta) if return_details else output
    if strength==0:return finish('zero_strength')
    for candidate in detection['candidates']:
        region=dict(candidate_id=candidate['candidate_id'],applied=False);meta['regions'].append(region)
        selected=candidate;pitch,measurement,raw=observed_seed_pitch(original,candidate['seed_roi'])
        scope,mask,quality=propose_visible_pad(original,candidate['seed_roi'])
        region['primary_observation']=dict(pitch_native=pitch,pitch_measurement=measurement,scope_quality=quality,human_verified=False)
        if pitch is None and quality.get('automatic_boundary_accepted',False):
            fallback,observation=observe_fallback(original,candidate,region['primary_observation']);region['fallback_observation']=observation
            if fallback is not None:
                selected=fallback;pitch,measurement,raw=observed_seed_pitch(original,selected['seed_roi']);scope,mask,quality=propose_visible_pad(original,selected['seed_roi'])
        if pitch is None or scope is None:region['status']='unobserved_ridges_or_uncertain_boundary_unchanged';continue
        a,b,c,d=scope
        if np.any(occupied[b:d,a:c]&mask):region['status']='overlapping_masks_unchanged';continue
        seed=int(hashlib.sha256(raw.tobytes()).hexdigest()[:8],16)
        candidate_image,render=render_whole_pad_candidate(original,selected['seed_roi'],pitch_native=pitch,seed=seed)
        assert render['rendered'] and render['roi_xyxy']==scope
        region.update(selected_candidate=selected,render=render,scope=scope)
        try:check=check_structure_change(original,candidate_image,selected['seed_roi'])
        except (RuntimeError,ValueError,subprocess.TimeoutExpired,subprocess.CalledProcessError) as exc:
            region.update(status='structure_inspection_failed_unchanged',inspection_error=str(exc));continue
        region['structure_check']=check
        if not check['structure_change_passed']:region['status']='structure_change_not_demonstrated_unchanged';continue
        assert np.array_equal(candidate_image[b:d,a:c][~mask],original[b:d,a:c][~mask])
        output[b:d,a:c][mask]=candidate_image[b:d,a:c][mask];occupied[b:d,a:c]|=mask
        region.update(applied=True,status='structure_changed_protection_unverified')
    return finish('transformed_functional_poc_protection_unverified' if np.any(occupied) else 'no_transformable_fingertip_unchanged')
