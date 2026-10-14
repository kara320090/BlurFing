"""Read-only candidate coverage/pitch observations; never expands protection."""
import hashlib
import json
import math
import re
import subprocess
import time
from dataclasses import asdict
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
import photo_region_pipeline_v1 as shared
from finger_body_distal_estimator import estimate
from photo_candidate_context_v1 import candidate_contexts
from photo_resize_safety_v1 import validate_resize, ResizeSafetyError
from ridge_evidence_frontend import ridge_evidence
from external_ridge_pitch_observer import observe

VERSION = 'photo_candidate_ridge_diagnostic_v1'


def pixel_sha(value):
    return hashlib.sha256(value.tobytes()).hexdigest()


def native_normal_pitch(pitch, orientation_deg, actual_resize_yx):
    """Convert perpendicular period using actual rounded resize dimensions.

    Working normal n_w maps to source normal A.T @ n_w; source period is
    working period / ||A.T @ n_w||. A has x/y resize ratios, not bbox scale.
    """
    if not isinstance(actual_resize_yx,(tuple,list)) or len(actual_resize_yx)!=2:
        raise ValueError('invalid_pitch_coordinate_contract')
    values = [pitch, orientation_deg, *actual_resize_yx]
    if (any(isinstance(v, bool) or not isinstance(v, (int, float))
            or not math.isfinite(v) for v in values) or pitch <= 0 or min(actual_resize_yx) <= 0):
        raise ValueError('invalid_pitch_coordinate_contract')
    sy, sx = actual_resize_yx
    theta = math.radians(orientation_deg)
    normal_scale = math.hypot(sx*math.cos(theta), sy*math.sin(theta))
    return pitch/normal_scale


def resolution_plans(shape):
    """Fixed resolution set; deduplicate identical rasters, never upscale."""
    if (not isinstance(shape,(tuple,list)) or len(shape)!=2 or
            any(type(v) is not int or v<=0 for v in shape)):
        raise ValueError('positive_image_shape_required')
    shape=tuple(shape)
    height, width = shape
    plans, seen = [], {}
    for target in [512, 1024, 2048, 'native']:
        scale = 1. if target == 'native' else min(1., target/max(shape))
        try:
            size, audit = validate_resize(height, width, scale)
            if size in seen:
                seen[size]['requested_resolutions'].append(target)
                continue
            plan = dict(status='planned', shape=list(size), nominal_scale=scale,
                actual_resize_yx=[size[0]/height, size[1]/width], native_resolution=size == shape,
                requested_resolutions=[target], resource_audit=audit)
            plans.append(plan); seen[size] = plan
        except ResizeSafetyError as error:
            plans.append(dict(status='rejected', requested_resolutions=[target],
                              reject_reason=error.reason, resource_audit=error.audit))
    return plans


def observe_candidate(rgb, body, pad, source_sha, *, save_support=None):
    if not isinstance(source_sha,str) or re.fullmatch('[0-9a-f]{64}',source_sha) is None:
        raise ValueError('invalid_source_hash')
    if (not isinstance(rgb, np.ndarray) or rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3 or
            not isinstance(body, np.ndarray) or body.dtype != np.bool_ or body.shape != rgb.shape[:2] or
            not isinstance(pad, np.ndarray) or pad.dtype != np.bool_ or pad.shape != body.shape or
            not body.any() or not pad.any() or np.any(pad & ~body)):
        raise ValueError('candidate_observation_contract_mismatch')
    before = [pixel_sha(a) for a in [rgb, body, pad]]
    ys = np.flatnonzero(body.any(axis=1)); xs = np.flatnonzero(body.any(axis=0))
    x0, y0, x1, y1 = int(xs[0]), int(ys[0]), int(xs[-1])+1, int(ys[-1])+1
    sl = np.s_[y0:y1, x0:x1]
    gray = cv2.cvtColor(rgb[sl], cv2.COLOR_RGB2GRAY)
    local_body, local_pad = body[sl], pad[sl]
    levels = []
    for index, plan in enumerate(resolution_plans(gray.shape), 1):
        level = dict(level_id=index, plan=plan)
        if plan['status'] == 'rejected':
            levels.append(level); continue
        height, width = plan['shape']
        scale = plan['nominal_scale']; actual = plan['actual_resize_yx']
        frame = (gray.copy() if plan['native_resolution'] else
                 cv2.resize(gray, (width, height), interpolation=cv2.INTER_AREA))
        working_pad = cv2.resize(local_pad.astype(np.uint8), (width, height), interpolation=cv2.INTER_NEAREST) > 0
        support, quality = ridge_evidence(gray, local_body, max_side=max(plan['shape']))
        # The shared observer returns support in this native crop, not working pixels.
        if support.shape != gray.shape or support.dtype != np.bool_ or np.any(support & ~local_body):
            raise ValueError('ridge_support_coordinate_contract_mismatch')
        level.update(ridge_quality=quality, support_native_roi_sha256=pixel_sha(support),
            support_native_roi_shape=list(support.shape),
            support_inside_pad_pixels=int(np.count_nonzero(support & local_pad)),
            support_outside_pad_pixels=int(np.count_nonzero(support & ~local_pad)),
            support_semantics='credible window support, not true ridge segmentation/GT/protection rate')
        if save_support is not None:
            level.update(save_support(index, support))
        if not working_pad.any():
            level['pitch'] = dict(status='unobserved', reason='pad_disappeared_at_resolution', value=None)
        else:
            space = 'native_source_pixels' if plan['native_resolution'] else 'normalized_working_pixels'
            evidence = observe(frame, working_pad, source_sha, image_scale=scale, coordinate_space=space)
            error = None
            try:
                evidence.validate(source_sha, pixel_sha(working_pad), frame.shape, space, scale, pixel_sha(frame))
            except ValueError as exc:
                error = str(exc)
            patches = []
            for patch in evidence.cue_results.get('patches', []):
                if patch.get('accepted') is not True:continue
                patches.append(dict(
                    center_encoded_source_xy=[x0+(patch['x']+.5)/actual[1]-.5,
                                              y0+(patch['y']+.5)/actual[0]-.5],
                    autocorrelation_perpendicular_native_pixels=native_normal_pitch(patch['autocorrelation'],patch['orientation_deg'],actual),
                    fft_perpendicular_native_pixels=native_normal_pitch(patch['fft'],patch['orientation_deg'],actual)))
            level['pitch'] = dict(status='observed' if error is None else 'unobserved',
                reason=error, evidence=asdict(evidence), observed_image_sha256=pixel_sha(frame),
                actual_resize_yx=actual, patch_native_coordinates=patches,
                coordinate_origin_encoded_source_xy=[x0,y0],
                evidence_semantics='existing ACF/FFT share a profile; not independent biometric evidence',
                renderer_binding_allowed=False, physical_DPI_known=False)
        levels.append(level)
    if before != [pixel_sha(a) for a in [rgb, body, pad]]:
        raise RuntimeError('candidate_observation_inputs_changed')
    return dict(bbox_encoded_source_xyxy=[x0,y0,x1,y1], body_pixels=int(body.sum()),
                pad_pixels=int(pad.sum()), levels=levels, protection_mask_changed=False,
                used_by_protection=False, default_pitch_generated=False)


def diagnose(source, output, *, photo_semantics=None, annotation_folder=None):
    source, output = Path(source), Path(output)
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise FileExistsError('fresh output directory required')
    start = time.perf_counter(); source_sha = shared.digest(source)
    # Decode preflight is a diagnostic resource contract, not an inference change.
    with Image.open(source) as image:
        if image.mode not in ['RGB', 'L']:raise ValueError('only 8-bit RGB/L inputs supported')
        orientation = image.getexif().get(274,1)
        if type(orientation) is not int or orientation not in range(1,9):
            raise ValueError('invalid_source_exif_orientation')
        validate_resize(image.height, image.width, 1.)
        rgb = np.asarray(image.convert('RGB')).copy()
    body, tip, inference = shared.load_semantics(source, rgb, photo_semantics)
    result = estimate(body, tip, preserve_candidates=True)
    contexts = candidate_contexts(result, body)
    original_hashes = [pixel_sha(a) for a in [rgb,body,tip,result['mask']]]
    output.mkdir(parents=True, exist_ok=True); rows = []
    for context in contexts:
        identity = context['candidate_id']; row = dict(candidate_id=identity,
            estimator_region_index=context['estimator_region_index'], reason=context['reject_reason'])
        if context['pad'] is not None and context['reject_reason'] is None:
            def save_support(level_id, support):
                name = f'candidate_{context["estimator_region_index"]:03d}_level_{level_id:02d}_window_support.png'
                Image.fromarray(support.astype(np.uint8)*255).save(output/name)
                return dict(support_path=name, support_file_sha256=shared.digest(output/name))
            row['observations'] = observe_candidate(rgb, context['body'], context['pad'], source_sha,
                                                   save_support=save_support)
        rows.append(row)
    # Human GT enters only here, after all region/resolution selection and observations.
    annotation, metrics = None, None
    if annotation_folder is not None:
        from evaluate_distal_pad_gt7 import validate_annotation, mask_metrics
        annotation_folder = Path(annotation_folder)
        annotation_hash = shared.digest(annotation_folder/'source.json')
        gt, annotation = validate_annotation(annotation_folder,source)
        if annotation['status'] in ['valid_positive','non_target']:
            metrics = mask_metrics(result['mask'],gt)
            if shared.digest(annotation_folder/'ground_truth_mask.png') != json.loads((annotation_folder/'source.json').read_text())['mask_sha256']:
                raise RuntimeError('annotation_mask_changed')
        if annotation_hash != shared.digest(annotation_folder/'source.json'):
            raise RuntimeError('annotation_metadata_changed')
    if (source_sha != shared.digest(source) or original_hashes !=
            [pixel_sha(a) for a in [rgb,body,tip,result['mask']]]):
        raise RuntimeError('diagnostic_source_or_masks_changed')
    report = dict(schema_version=VERSION, status='diagnostic_complete', source_sha256=source_sha,
        source_RGB_sha256=pixel_sha(rgb), source_exif_orientation=orientation,
        coordinate_system='encoded_original_pixels', regions=rows,
        detector_mask_sha256=pixel_sha(result['mask']), annotation=annotation,
        human_GT_mask_metrics=metrics, GT_used_by_observer=False,
        evaluation_scope='development_diagnostic', independent_validation=False,
        protection_mask_changed=False, protection_applied=False, thresholds_changed=False,
        renderer_binding_allowed=False, PHOTO_DETECTOR_APPROVED=False,
        PHOTO_PROTECTION_PRODUCTION_READY=False,
        semantics_source='configured_worker' if photo_semantics is None else 'validated_cache',
        timing=dict(COLFISPOOF=inference,total=time.perf_counter()-start))
    (output/'diagnostic.private.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    return report


if __name__ == '__main__':
    from protect_fingerprint import cli_progress_to_stderr, JSONArgumentParser
    parser = JSONArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--photo-semantics', type=Path)
    parser.add_argument('--annotation-folder', type=Path)
    args = parser.parse_args()
    try:
        with cli_progress_to_stderr():
            report = diagnose(args.input,args.output,photo_semantics=args.photo_semantics,
                              annotation_folder=args.annotation_folder)
        print(json.dumps(report,indent=2,allow_nan=False))
    except Exception as error:
        print(json.dumps(dict(status='error',error=type(error).__name__)))
        raise SystemExit(1)
