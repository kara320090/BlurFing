"""Opt-in PHOTO candidates retain estimator identity and native body context."""
import hashlib
import json
import subprocess
import tempfile
import time
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
import photo_region_pipeline_v1 as shared
from finger_body_distal_estimator import estimate
from photo_candidate_context_v1 import candidate_contexts, plan_candidate_scale
from contactless_finger_width_body_v1 import estimate_finger_width_body
from photo_quality_gate import state, summarize

VERSION = 'photo_region_pipeline_v3_candidate_context_experimental'
HANDLED = (ValueError, RuntimeError, OSError, subprocess.SubprocessError)


def render_candidate_region(rgb, artifact, axis_yx):
    """The artifact's body belongs to this estimator candidate, not a union."""
    height, width = artifact['working_shape']
    body = cv2.resize(shared.orient(artifact['body'].astype(np.uint8), artifact['exif_orientation']),
                      (width, height), interpolation=cv2.INTER_NEAREST) > 0
    padding = artifact['regions'][0]['padding']
    body = np.pad(body, ((0, padding['bottom']), (0, padding['right'])), constant_values=False)
    def observe(image, box, axis):
        return estimate_finger_width_body(image, box, axis, body, image_shape=(height, width))
    return shared.render_region(rgb, artifact, axis_yx, _width_observer=observe)


def _evaluate(source, semantics=None, detect_only=False):
    start = time.perf_counter()
    source_sha = shared.digest(source)
    with Image.open(source) as image:
        if image.mode not in ['RGB', 'L']:
            raise ValueError('only 8-bit RGB/L inputs supported')
        rgb = np.asarray(image.convert('RGB')).copy()
        orientation = image.getexif().get(274, 1)
    valid_orientation = type(orientation) is int and orientation in range(1, 9)
    source_rgb_sha = hashlib.sha256(rgb.tobytes()).hexdigest()
    route = shared.route_input(rgb)
    returned, union = rgb.copy(), np.zeros(rgb.shape[:2], bool)
    masks, bodies, regions = [], [], []
    inference, failure = 0., None
    if not valid_orientation:
        failure = dict(reject_reason='invalid_source_exif_orientation',
                       source_exif_orientation_repr=repr(orientation),
                       output_exif_orientation=1, exif_orientation_valid=False)
    elif route['input_type'] != 'PHOTO':
        failure = dict(reject_reason='experimental_photo_input_required')
    else:
        try:
            body, tip, inference = shared.load_semantics(source, rgb, semantics)
            result = estimate(body, tip, preserve_candidates=True)
            contexts = candidate_contexts(result, body)
            union = result['mask'].copy()
            gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
            for context in contexts:
                parent, native = context['parent'], context['pad']
                index, identity = context['estimator_region_index'], context['candidate_id']
                masks.append(native)
                bodies.append(context['body'])
                row = dict(region_id=index, candidate_id=identity, estimator_region_index=index,
                           body_component=parent['component'], watershed_part=parent['watershed_part'],
                           mask_pixels=int(native.sum()) if native is not None else 0,
                           mask_pixel_sha256=hashlib.sha256(native.tobytes()).hexdigest() if native is not None else None,
                           body_pixels=int(context['body'].sum()),
                           body_pixel_sha256=hashlib.sha256(context['body'].tobytes()).hexdigest(),
                           status='rejected', quality_status='REJECT_OTHER', reason=context['reject_reason'])
                try:
                    if row['reason'] is None:
                        plan = plan_candidate_scale(native, index)
                        row['scale_plan'] = plan
                        row['reason'] = plan['reject_reason']
                        if plan['status'] == 'planned':
                            # Single explicit parent; association never labels the union.
                            association = shared.associate_axis(native, [parent])
                            association.update(estimator_region_index=index, candidate_id=identity)
                            row['association'] = association
                            artifact, geometry = shared.prepare_region(rgb, gray, native, context['body'],
                                orientation, source_sha, plan, association)
                            row['geometry'], row['reason'] = geometry, geometry['reject_reason']
                            if artifact is not None:
                                if detect_only:
                                    row['reason'] = 'detect_only'
                                else:
                                    candidate, details = render_candidate_region(rgb, artifact, geometry['axis_working_yx'])
                                    row['renderer_details'] = details
                                    binding_id = f'coarse-{index}'
                                    row['renderer_binding_candidate_id'] = binding_id
                                    if len(details['regions']) != 1 or details['regions'][0].get('candidate_id') != binding_id:
                                        raise ValueError('region_renderer_identity_contract_mismatch')
                                    report = details['regions'][0]
                                    applied = bool(report.get('applied'))
                                    if applied and not report.get('structure_check', {}).get('structure_change_passed'):
                                        raise ValueError('region_structure_guard_contract_mismatch')
                                    row['reason'] = (None if applied else report.get('structure_check', {}).get('reason')
                                                     or report.get('status') or 'renderer_contract_not_satisfied')
                                    if applied:
                                        if (not isinstance(candidate, np.ndarray) or candidate.shape != rgb.shape or
                                                candidate.dtype != np.uint8 or not np.array_equal(candidate[~native], rgb[~native])):
                                            raise ValueError('region_renderer_output_contract_mismatch')
                                        returned[native] = candidate[native]
                                        row.update(status='transformed', quality_status='TRANSFORMED')
                    if row['status'] != 'transformed':
                        row['quality_status'] = state(row['reason'])
                except HANDLED as error:
                    row.update(reason=str(error), error=type(error).__name__, quality_status=state(str(error)))
                regions.append(row)
            for row, native in zip(regions, masks):
                if native is not None and row['status'] == 'rejected' and not np.array_equal(returned[native], rgb[native]):
                    raise RuntimeError('rejected_region_pixels_changed')
        except HANDLED as error:
            returned = rgb.copy()
            for row in regions:
                row.update(status='rejected', quality_status='REJECT_OTHER', reason='experiment_contract_failure')
            failure = dict(reject_reason=str(error), error=type(error).__name__)
            if getattr(error, 'audit', None) is not None:
                failure['resource_audit'] = error.audit
    if (not np.array_equal(returned[~union], rgb[~union]) or shared.digest(source) != source_sha or
            hashlib.sha256(rgb.tobytes()).hexdigest() != source_rgb_sha):
        raise RuntimeError('source_or_exterior_changed')
    metadata = summarize(regions) | dict(quality_gate_version=VERSION,
        schema_version='experimental-photo-candidates-v1', default_pipeline_enabled=False,
        PHOTO_FAIL_CLOSED_PIPELINE_READY=False, independent_validation_complete=False,
        algorithm_thresholds_unchanged=True, frozen_files_unchanged=True, input_type='photo', route=route,
        candidate_identity_preserved=True, union_relabeling_for_candidates=False,
        count_semantics='estimator candidates including geometry rejections; not true fingerprint count',
        source_sha256=source_sha, image_width=rgb.shape[1], image_height=rgb.shape[0],
        source_exif_orientation=orientation if type(orientation) is int else None,
        coordinate_system='encoded_original_pixels', exterior_preserved=True,
        changed_pixels=int(np.any(returned != rgb, axis=2).sum()),
        returned_RGB_sha256=hashlib.sha256(returned.tobytes()).hexdigest(),
        semantics_source='configured_worker' if semantics is None else 'validated_cache',
        timing=dict(COLFISPOOF=inference, total=time.perf_counter()-start))
    if failure:
        metadata.update(failure)
    return returned, union, metadata, masks, bodies


def evaluate_regions(source, semantics=None, detect_only=False):
    return _evaluate(source, semantics, detect_only)[:3]


def protect_photo_regions(source, output=None, *, photo_semantics=None, detect_only=False, strength=.5):
    if isinstance(strength, bool) or strength not in (0., .5):
        raise ValueError('strength must be 0 or 0.5')
    output = Path(tempfile.mkdtemp(prefix='blurfing_photo_candidates_')) if output is None else Path(output)
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise FileExistsError('fresh output directory required')
    returned, union, report, masks, bodies = _evaluate(source, photo_semantics, detect_only or strength == 0)
    output.mkdir(parents=True, exist_ok=True)
    exif = Image.Exif()
    exif[274] = report.get('output_exif_orientation', report['source_exif_orientation'])
    Image.fromarray(returned).save(output/'returned.png', exif=exif)
    Image.fromarray(union.astype(np.uint8)*255).save(output/'fingerprint_mask.png')
    for row, pad, body in zip(report['regions'], masks, bodies):
        # Save original candidate masks, never connected labels of their union.
        for name, mask in [('mask', pad), ('body', body)]:
            if mask is None:
                continue
            filename = f"candidate_{row['region_id']:03d}_{name}.png"
            Image.fromarray(mask.astype(np.uint8)*255).save(output/filename)
            row.update({name+'_path':filename, name+'_sha256':shared.digest(output/filename)})
    report['output_path'] = str(output/'returned.png')
    (output/'result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return returned, report


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
