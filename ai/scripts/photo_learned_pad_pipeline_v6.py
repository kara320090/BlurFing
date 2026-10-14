"""Opt-in original-quality seed selection; unchanged rendering/return gates.

Use the fixed V4 body-supported observation bank, selecting the first seed
that passes original width, frozen pitch and original feature availability.
Rendering occurs once, after selection. No generated-feature/matcher search.
"""
from pathlib import Path
import cv2
import photo_learned_pad_pipeline_v1 as base
import photo_region_pipeline_v1 as shared
from photo_learned_pad_pipeline_v3 import prepare_scoped_region as prepare_body_scale
from photo_body_observation_seed_v1 import prepare_region as prepare_observed_region
from photo_spatial_observation_bank_v1 import observation_seeds as seeds
from photo_owner_partition_v1 import partition
from photo_native_owner_context_v1 import restore_contexts
from photo_returned_rgb_structure_v1 import returned_structure_check
from contactless_finger_width_body_v1 import estimate_finger_width_body
from photo_source_feature_preflight_v1 import observe as observe_original_features

VERSION='photo_learned_pad_pipeline_v6_original_quality_selection_experimental'


def prepare_region(rgb,gray,mask,body,orientation,source_sha,plan,association):
    upright=shared.orient(rgb,orientation);shape,_=shared.validate_resize(*upright.shape[:2],plan['working_scale'])
    scale=plan['working_scale'];working=cv2.resize(upright,(shape[1],shape[0]),interpolation=cv2.INTER_AREA if scale<1 else cv2.INTER_CUBIC)
    axis=shared.orient_axis(association['axis_native_yx'],orientation,[shape[0]/upright.shape[0],shape[1]/upright.shape[1]])
    attempts=[]
    def proposals(working_mask,working_body,*unused):
        for proposal in seeds(working_mask,working_body):
            box=proposal['box']
            if proposal['side']<32:
                attempts.append(proposal|dict(reject_reason='coarse_pad_too_small_for_seed'));continue
            width=estimate_finger_width_body(working,box,axis,working_body)
            if width['status']!='estimated':
                attempts.append(proposal|dict(width=width,reject_reason='original_width_unavailable'));continue
            pitch,measurement,_=shared.observed_seed_pitch(working,box)
            if pitch is None or not 2<=pitch<=50:
                attempts.append(proposal|dict(pitch_measurement=measurement,reject_reason='body_supported_pitch_unobserved'));continue
            availability=observe_original_features(working,box,width)
            record=proposal|dict(width=width,pitch_measurement=measurement,source_feature_preflight=availability)
            attempts.append(record|dict(reject_reason=availability['reason']))
            if availability['eligible'] is True:return [record]
        return []
    artifact,geometry=prepare_observed_region(rgb,gray,mask,body,orientation,source_sha,plan,association,_proposals=proposals)
    geometry.update(source_quality_seed_policy=VERSION,source_quality_attempts=attempts,
                    seed_selection_uses_generated_features=False,seed_selection_uses_matcher_scores=False)
    if artifact is None:
        reasons=[r.get('reject_reason') for r in attempts]
        reason=('insufficient_features' if 'insufficient_features' in reasons else 'body_supported_pitch_unobserved'
            if 'body_supported_pitch_unobserved' in reasons else 'original_width_unavailable'
            if 'original_width_unavailable' in reasons else 'body_supported_seed_unavailable')
        geometry['reject_reason']=reason
    return artifact,geometry


def prepare_scoped_region(*args):
    return prepare_body_scale(*args,_preparer=prepare_region,_version=VERSION,_postprocess=returned_structure_check)


def evaluate_learned_mask(source,mask,expected_pixel_sha256,*,detect_only=False):
    return base.evaluate_learned_mask(source,mask,expected_pixel_sha256,detect_only=detect_only,
        _scope_adapter=prepare_scoped_region,_version=VERSION,_candidate_builder=partition,_context_adapter=restore_contexts)


def protect_bundle(folder,root,output,detect_only=False):
    return base.protect_bundle(folder,root,output,detect_only,_mask_evaluator=evaluate_learned_mask,_version=VERSION)


if __name__=='__main__':
    from protect_fingerprint import JSONArgumentParser,cli_progress_to_stderr
    p=JSONArgumentParser(description=__doc__);p.add_argument('--model',type=Path,required=True)
    p.add_argument('--inputs',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--detect-only',action='store_true');a=p.parse_args()
    try:
        with cli_progress_to_stderr():result=protect_bundle(a.model,a.inputs,a.output,a.detect_only)
        print(__import__('json').dumps(result,indent=2))
    except Exception as error:
        print(__import__('json').dumps(dict(status='error',error=type(error).__name__,reason=str(error))))
        raise SystemExit(1)
