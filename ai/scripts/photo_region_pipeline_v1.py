"""Opt-in PHOTO region geometry experiment; the unified default is unchanged.

Keeps native masks and frozen pitch/renderer/feature criteria. Each coarse
component gets its own resource plan and an unambiguous estimator-parent axis.
The axis width observer is scoped under the existing renderer's shared lock.
"""
import hashlib
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from scipy import ndimage

from canonical_fingerprint_roi import canonical_roi
from contactless_finger_width_axis_v1 import estimate_finger_width_axis
from evaluate_finger_body_distal import read_binary
from finger_body_distal_estimator import estimate
from fingerprint_input_router import route_input
from photo_coarse_adapter_v2 import orient, seed_square, square_scope, validate_semantic_policy
import photo_coarse_renderer_adapter_v1 as renderer_binding
from photo_quality_gate import pitch_failure_reason, state, summarize
from photo_region_scale_plan_v1 import plan_region_scales
from photo_resize_safety_v1 import validate_resize
from protect_visible_pad_checked_v2 import observed_seed_pitch
from ridge_evidence_frontend import ridge_evidence

VERSION = 'photo_region_pipeline_v1_experimental'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def orient_axis(axis_yx, orientation, scale_yx=(1., 1.)):
    """Transform a direction, not a point; translations do not affect it."""
    axis = np.asarray(axis_yx, dtype=np.float64)
    scales = np.asarray(scale_yx, dtype=np.float64)
    if (axis.shape != (2,) or scales.shape != (2,) or not np.isfinite(axis).all()
            or not np.isfinite(scales).all() or (scales <= 0).any()
            or type(orientation) is not int or orientation not in range(1, 9)):
        raise ValueError('invalid_axis_coordinate_contract')
    y, x = axis
    transformed = {1:(y,x), 2:(y,-x), 3:(-y,-x), 4:(-y,x),
                   5:(x,y), 6:(x,-y), 7:(-x,-y), 8:(-x,y)}[orientation]
    transformed = np.asarray(transformed) * scales
    length = float(np.linalg.norm(transformed))
    if not np.isfinite(length) or length == 0:
        raise ValueError('invalid_axis_coordinate_contract')
    return (transformed / length).tolist()


def associate_axis(mask, estimator_regions):
    """Reject ambiguous parents; body component IDs are not watershed IDs."""
    matches = []
    for index, parent in enumerate(estimator_regions, 1):
        native = parent.get('mask')
        if parent.get('reject_reason') is not None or native is None:
            continue
        if native.shape != mask.shape or native.dtype != np.bool_:
            raise ValueError('estimator_parent_mask_contract_mismatch')
        if np.any(mask & native):
            matches.append((index, parent))
    if len(matches) != 1:
        raise ValueError('coarse_axis_parent_unavailable' if not matches else 'coarse_axis_parent_ambiguous')
    index, parent = matches[0]
    if np.any(mask & ~parent['mask']):
        raise ValueError('coarse_component_crosses_parent')
    if parent.get('metadata_coordinate_system') != 'working_image_pixels':
        raise ValueError('estimator_axis_coordinate_contract_mismatch')
    scale = float(parent['working_scale'])
    if not np.isfinite(scale) or not 0 < scale <= 1:
        raise ValueError('estimator_axis_scale_contract_mismatch')
    height, width = mask.shape
    # The estimator rounds both resize dimensions. Undo their actual ratios.
    actual = np.array([max(1, round(height*scale))/height,
                       max(1, round(width*scale))/width])
    native_axis = orient_axis(parent['major_axis_yx'], 1, 1/actual)
    return dict(estimator_region_index=index, body_component=parent['component'],
                axis_native_yx=native_axis, estimator_resize_yx=actual.tolist(),
                distal_endpoint_source=parent.get('distal_endpoint_source'))


def prepare_region(rgb, gray, mask, body, orientation, source_sha, plan, association):
    scale = plan['working_scale']
    upright = orient(rgb, orientation)
    shape, audit = validate_resize(*upright.shape[:2], scale)
    axis = orient_axis(association['axis_native_yx'], orientation,
                       [shape[0]/upright.shape[0], shape[1]/upright.shape[1]])
    working = cv2.resize(upright, (shape[1], shape[0]),
                         interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC)
    working_mask = cv2.resize(orient(mask.astype(np.uint8), orientation),
                             (shape[1], shape[0]), interpolation=cv2.INTER_NEAREST) > 0
    seed = seed_square(working_mask)
    pitch, measurement, _ = observed_seed_pitch(working, seed)
    geometry = dict(working_scale=scale, working_shape=list(shape), working_seed=seed,
                    axis_working_yx=axis, actual_resize_yx=[shape[0]/upright.shape[0],
                    shape[1]/upright.shape[1]], resize_audit=audit,
                    observed_pitch_working=pitch, pitch_measurement=measurement)
    if pitch is None:
        return None, geometry | dict(reject_reason=pitch_failure_reason(measurement))
    if not 2 <= pitch <= 50:
        return None, geometry | dict(reject_reason='renderer_pitch_out_of_range')
    y, x = np.where(mask)
    _, quality = ridge_evidence(gray[y.min():y.max()+1, x.min():x.max()+1],
                                mask[y.min():y.max()+1, x.min():x.max()+1])
    quality |= dict(pitch_native=float(pitch/scale), pitch_source='frozen_observed_seed_pitch',
                    confidence_semantics='ridge credible-window fraction; unapproved geometric candidate')
    roi = canonical_roi(gray, mask, source_sha, 'PHOTO', quality,
                        'COLFISPOOF_finger_body_distal_experimental')
    roi.validate(rgb, source_sha)
    if np.any(mask & ~body):
        raise ValueError('pad_outside_body')
    scope, padding = square_scope(working_mask)
    _, padding_audit = validate_resize(shape[0]+padding['bottom'], shape[1]+padding['right'], 1)
    audit['square_padding_allocation'] = padding_audit
    entry = dict(roi=roi, working_seed=seed, working_scope=scope, padding=padding,
                 pitch_measurement=measurement, component=plan['component'])
    artifact = dict(source_sha256=source_sha, source_rgb_sha256=hashlib.sha256(rgb.tobytes()).hexdigest(),
                    exif_orientation=orientation, working_shape=shape, working_scale=scale,
                    regions=[entry], coarse_mask=mask, body=body)
    return artifact, geometry | dict(reject_reason=None, observed_pitch_native=float(pitch/scale))


def render_region(rgb, artifact, axis_yx, *, _width_observer=None):
    """Keep frozen files intact; restore the observer even if rendering fails."""
    import fingerprint_structure_check as structure
    observations = []
    expected_seed = artifact['regions'][0]['working_seed']
    def observe(image, box):
        if list(box) != expected_seed:
            raise ValueError('axis_width_seed_contract_mismatch')
        measurement = (_width_observer or estimate_finger_width_axis)(image, box, axis_yx)
        observations.append(measurement)
        return measurement
    # Default renderer structure calls hold this same RLock. No observer leak
    # into another adapter call, including one waiting in another thread.
    with renderer_binding._LOCK:
        previous = structure.estimate_finger_width
        try:
            structure.estimate_finger_width = observe
            returned, details = renderer_binding.transform(rgb, artifact)
        finally:
            structure.estimate_finger_width = previous
    return returned, details | dict(width_observations=observations)


def load_semantics(source, rgb, semantics):
    inference = 0.
    if semantics is None:
        config = [os.environ.get(key) for key in ['BLURFING_COLFISPOOF_PYTHON',
                  'BLURFING_COLFISPOOF_SOURCE', 'BLURFING_COLFISPOOF_MODEL']]
        if not all(config):
            raise ValueError('photo_runtime_not_configured')
        semantics = Path(tempfile.mkdtemp(prefix='blurfing_photo_semantics_'))/'semantics'
        command = [config[0], str(Path(__file__).with_name('colfispoof_body_semantics.py')),
                   '--input', str(Path(source).resolve()), '--output', str(semantics),
                   '--external-source', config[1], '--model', config[2]]
        start = time.perf_counter()
        subprocess.run(command, check=True, timeout=300, shell=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        inference = time.perf_counter()-start
    semantics = Path(semantics)
    identity = json.loads((semantics/'semantics.json').read_text(encoding='utf-8'))
    validate_semantic_policy(identity)
    if (identity['source_sha256'] != digest(source) or
            (identity['image_height'], identity['image_width']) != rgb.shape[:2]):
        raise ValueError('source_semantics_contract_mismatch')
    body = read_binary(semantics/'body.png', rgb.shape[:2], identity['body_sha256'])
    tip = read_binary(semantics/'tip.png', rgb.shape[:2], identity['tip_sha256'])
    return body, tip, inference


def evaluate_regions(source, semantics=None, detect_only=False, *, _region_renderer=None, _pipeline_version=VERSION):
    start = time.perf_counter()
    source_sha = digest(source)
    with Image.open(source) as image:
        if image.mode not in ['RGB', 'L']:
            raise ValueError('only 8-bit RGB/L inputs supported')
        rgb = np.asarray(image.convert('RGB')).copy()
        orientation = image.getexif().get(274, 1)
    # Undefined/nonstandard EXIF cannot establish an axis transform. Reject
    # normally before worker/rendering; preserve encoded RGB and source bytes.
    valid_orientation = type(orientation) is int and orientation in range(1, 9)
    returned = rgb.copy()
    mask = np.zeros(rgb.shape[:2], bool)
    route = route_input(rgb)
    regions, inference, failure = [], 0., None
    if not valid_orientation:
        failure = dict(reject_reason='invalid_source_exif_orientation',
                       source_exif_orientation_repr=repr(orientation),
                       output_exif_orientation=1, exif_orientation_valid=False)
    elif route['input_type'] != 'PHOTO':
        failure = dict(reject_reason='experimental_photo_input_required')
    else:
        try:
            body, tip, inference = load_semantics(source, rgb, semantics)
            result = estimate(body, tip)
            proposed = result['mask']
            if not isinstance(proposed, np.ndarray) or proposed.shape != rgb.shape[:2] or proposed.dtype != np.bool_ or np.any(proposed & ~body):
                raise ValueError('coarse_mask_contract_mismatch')
            mask = proposed
            plans = plan_region_scales(mask)
            labels, _ = ndimage.label(mask)
            gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
            for plan in plans['regions']:
                native = labels == plan['component']
                row = dict(region_id=plan['component'], mask_pixels=int(native.sum()),
                           mask_pixel_sha256=hashlib.sha256(native.tobytes()).hexdigest(),
                           scale_plan=plan, status='rejected', quality_status='REJECT_OTHER',
                           reason=plan['reject_reason'])
                try:
                    if plan['status'] == 'rejected':
                        regions.append(row)
                        continue
                    row['association'] = associate_axis(native, result['regions'])
                    artifact, geometry = prepare_region(rgb, gray, native, body, orientation,
                                                        source_sha, plan, row['association'])
                    row['geometry'] = geometry
                    row['reason'] = geometry['reject_reason']
                    if artifact is not None:
                        if detect_only:
                            row['reason'] = 'detect_only'
                        else:
                            if _region_renderer is None:
                                candidate, details = render_region(rgb, artifact, geometry['axis_working_yx'])
                            else:
                                candidate, details = _region_renderer(rgb, artifact, geometry['axis_working_yx'],
                                                                       row['association'], result['regions'])
                            row['renderer_details'] = details
                            if len(details['regions']) != 1 or details['regions'][0].get('candidate_id') != f"coarse-{plan['component']}":
                                raise ValueError('region_renderer_identity_contract_mismatch')
                            report = details['regions'][0]
                            applied = bool(report.get('applied'))
                            if applied and not report.get('structure_check',{}).get('structure_change_passed'):
                                raise ValueError('region_structure_guard_contract_mismatch')
                            row['reason'] = (None if applied else report.get('structure_check',{}).get('reason')
                                             or report.get('status') or 'renderer_contract_not_satisfied')
                            if applied:
                                if candidate.shape != rgb.shape or candidate.dtype != np.uint8 or not np.array_equal(candidate[~native], rgb[~native]):
                                    raise ValueError('region_renderer_output_contract_mismatch')
                                returned[native] = candidate[native]
                                row.update(status='transformed', quality_status='TRANSFORMED')
                    if row['status'] != 'transformed':
                        row['quality_status'] = state(row['reason'])
                except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as error:
                    row.update(reason=str(error), error=type(error).__name__, quality_status=state(str(error)))
                if row['status'] == 'rejected' and not np.array_equal(returned[native], rgb[native]):
                    raise RuntimeError('rejected_region_pixels_changed')
                regions.append(row)
        except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as error:
            # A whole-run contract failure invalidates every previously applied region.
            returned = rgb.copy()
            for row in regions:
                row.update(status='rejected', quality_status='REJECT_OTHER', reason='experiment_contract_failure')
            failure = dict(reject_reason=str(error), error=type(error).__name__)
    if not np.array_equal(returned[~mask], rgb[~mask]) or digest(source) != source_sha:
        raise RuntimeError('source_or_exterior_changed')
    metadata = summarize(regions) | dict(quality_gate_version=_pipeline_version, default_pipeline_enabled=False,
        PHOTO_FAIL_CLOSED_PIPELINE_READY=False,
        axis_width_experimental=True, algorithm_thresholds_unchanged=True, frozen_files_unchanged=True,
        independent_validation_complete=False, input_type='photo', route=route, source_sha256=source_sha,
        image_width=rgb.shape[1], image_height=rgb.shape[0],
        source_exif_orientation=orientation if type(orientation) is int else None,
        coordinate_system='encoded_original_pixels', exterior_preserved=True,
        changed_pixels=int(np.any(returned != rgb, axis=2).sum()),
        returned_RGB_sha256=hashlib.sha256(returned.tobytes()).hexdigest(),
        semantics_source='configured_worker' if semantics is None else 'validated_cache',
        timing=dict(COLFISPOOF=inference, total=time.perf_counter()-start))
    if failure:
        metadata.update(failure)
    return returned, mask, metadata


def protect_photo_regions(source, output=None, *, photo_semantics=None, detect_only=False, strength=.5,
                          _region_renderer=None, _pipeline_version=VERSION):
    if isinstance(strength, bool) or strength not in (0., .5):
        raise ValueError('strength must be 0 or 0.5')
    output = Path(tempfile.mkdtemp(prefix='blurfing_photo_regions_')) if output is None else Path(output)
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise FileExistsError('fresh output directory required')
    returned, mask, metadata = evaluate_regions(source, photo_semantics, detect_only or strength == 0,
                                                _region_renderer=_region_renderer, _pipeline_version=_pipeline_version)
    output.mkdir(parents=True, exist_ok=True)
    exif = Image.Exif()
    exif[274] = metadata.get('output_exif_orientation', metadata['source_exif_orientation'])
    Image.fromarray(returned).save(output/'returned.png', exif=exif)
    Image.fromarray(mask.astype(np.uint8)*255).save(output/'fingerprint_mask.png')
    labels, _ = ndimage.label(mask)
    for row in metadata['regions']:
        name = f"region_{row['region_id']:03d}_mask.png"
        Image.fromarray((labels == row['region_id']).astype(np.uint8)*255).save(output/name)
        row.update(mask_path=name, mask_sha256=digest(output/name))
    metadata.update(schema_version='experimental-photo-regions-v1', output_path=str(output/'returned.png'))
    (output/'result.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    return returned, metadata


if __name__ == '__main__':
    from protect_fingerprint import cli_progress_to_stderr, JSONArgumentParser
    parser = JSONArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--photo-semantics', type=Path)
    parser.add_argument('--detect-only', action='store_true')
    parser.add_argument('--strength', type=float, default=.5)
    args = parser.parse_args()
    try:
        with cli_progress_to_stderr():
            _, report = protect_photo_regions(args.input, args.output, photo_semantics=args.photo_semantics,
                                               detect_only=args.detect_only, strength=args.strength)
        print(json.dumps(report, indent=2))
    except Exception as error:
        print(json.dumps(dict(status='error', error=type(error).__name__)))
        raise SystemExit(1)
