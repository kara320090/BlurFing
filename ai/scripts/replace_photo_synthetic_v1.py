"""Opt-in synthetic replacement of a verified native run's black fallback mask.

Uses original source pixels + hash-bound permission, NEVER guesses a mask by
looking for black pixels in a photograph. Accepted native pixels stay intact.
No frozen native renderer or gate decisions are changed.
"""
import json
from pathlib import Path
import numpy as np
from PIL import Image
from photo_source_rgb_v1 import canonical_rgb
from photo_rejection_resolution_v1 import cover_rejected, pixel_hash
from photo_synthetic_replacement_v1 import render
from pad_refinement_data_contract_v2 import digest
from final_png_color_metadata_v1 import save_final_rgb_png
from protection_runtime_sources_v1 import capture_runtime_sources, assert_runtime_sources_unchanged


def _array(path, shape, *, binary=False):
    with Image.open(path) as image:
        if (image.height, image.width) != shape:
            raise ValueError('synthetic_artifact_shape_mismatch')
        a = np.array(image)
    if binary:
        if a.dtype != np.uint8 or a.ndim != 2 or not np.all((a == 0) | (a == 255)):
            raise ValueError('synthetic_artifact_binary_mask_required')
        return a > 0
    return a


def run(source, protection_run, output, *, seed=None, renderer='v1'):
    if renderer not in ('v1', 'v2', 'v3'):
        raise ValueError('unsupported_synthetic_renderer')
    render_selected = render
    if renderer == 'v2':
        from photo_synthetic_replacement_v2 import render as render_selected
    elif renderer == 'v3':
        from photo_synthetic_replacement_v3 import render as render_selected
    source, protection_run, output = map(Path, (source, protection_run, output))
    if output.exists() or output.is_symlink():
        raise FileExistsError('fresh_output_required')
    snapshot = capture_runtime_sources()
    names = ['result.private.json', 'permission_mask.png', 'accepted_mask.png',
             'fallback_mask.png', 'region_labels.png', 'returned.png']
    pins = {name: digest(protection_run/name) for name in names}
    report = json.loads((protection_run/'result.private.json').read_text(encoding='utf-8'))
    rgb, identity = canonical_rgb(source)
    if report.get('input_type') != 'PHOTO' or report.get('input_identity') != identity:
        raise ValueError('synthetic_source_identity_mismatch')
    shape = rgb.shape[:2]
    permission, accepted, fallback = [_array(protection_run/(name+'.png'), shape, binary=True)
                                     for name in ('permission_mask', 'accepted_mask', 'fallback_mask')]
    labels = _array(protection_run/'region_labels.png', shape)
    native = _array(protection_run/'returned.png', shape)
    # Reuse the complete existing region/report/actual-RGB validation, including
    # rejection-vs-runtime-error distinction. Cached native results remain old
    # results; this function never claims they ran under today's source snapshot.
    _, verified_fallback, resolution = cover_rejected(rgb, native, permission, accepted, labels, report)
    if not np.array_equal(fallback, verified_fallback):
        raise ValueError('synthetic_fallback_binding_mismatch')
    replacement_labels = np.where(fallback, labels, 0).astype(np.uint16)
    synthetic, metadata = render_selected(rgb, fallback, replacement_labels, seed=seed)
    synthetic[accepted] = native[accepted]
    if (not np.array_equal(synthetic[~permission], rgb[~permission]) or
            not np.array_equal(synthetic[accepted], native[accepted])):
        raise RuntimeError('synthetic_composite_contract')
    output.mkdir(parents=True, exist_ok=False)
    color = save_final_rgb_png(source, identity['original_source_sha256'], synthetic,
                              output/'synthetic.png', identity['source_exif_orientation'])
    exif = Image.Exif(); exif[274] = identity['source_exif_orientation']
    with (output/'replacement_mask.png').open('xb') as stream:
        Image.fromarray(fallback.astype(np.uint8)*255).save(stream, format='PNG', exif=exif)
    for name, expected in pins.items():
        if digest(protection_run/name) != expected:
            raise ValueError('synthetic_upstream_artifact_changed')
    if digest(source) != identity['original_source_sha256']:
        raise ValueError('synthetic_source_changed')
    metadata.update(**color, input_identity=identity, synthetic_renderer=renderer,
        method='opaque_synthetic_texture_on_rejected_permission',
        cached_native_report_sha256=pins['result.private.json'],
        cached_native_status=report['status'],
        native_transformed_regions=resolution['native_transformed_regions'],
        native_rejected_regions=resolution['native_rejected_regions'],
        native_gate_decisions_changed=False, rejected_native_counted_as_native_success=False,
        native_accepted_pixels_preserved=True, candidate_pixels=int(permission.sum()),
        untreated_candidate_pixels=0, cached_native_run_reexecuted=False,
        actual_changed_pixels=int(np.any(synthetic != rgb, axis=2).sum()),
        output_RGB_sha256=pixel_hash(synthetic),
        output_path=str((output/'synthetic.png').resolve()),
        upstream_artifact_hashes=pins,
        runtime_source_snapshot=assert_runtime_sources_unchanged(snapshot),
        runtime_source_snapshot_verified=True, independent_accuracy_evaluation=False)
    with (output/'result.private.json').open('x', encoding='utf-8') as stream:
        json.dump(metadata, stream, indent=2)
    return synthetic, metadata


if __name__ == '__main__':
    from protect_fingerprint import JSONArgumentParser, cli_progress_to_stderr
    parser = JSONArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--protection-run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seed', type=int, help='Optional reproducibility seed; default uses fresh random seed.')
    parser.add_argument('--renderer', choices=('v1', 'v2', 'v3'), default='v1')
    args = parser.parse_args()
    try:
        with cli_progress_to_stderr():
            _, result = run(args.input, args.protection_run, args.output, seed=args.seed, renderer=args.renderer)
        print(json.dumps(result, indent=2))
    except Exception as error:
        print(json.dumps(dict(status='error', reason=str(error), error=type(error).__name__)))
        raise SystemExit(1)
