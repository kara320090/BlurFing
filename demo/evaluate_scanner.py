"""Independent scanner-reference comparison using the existing SourceAFIS runtime.

Run with the validated scanner AI Python and its NBIS/SourceAFIS environment.
Scores are raw similarities, never identity probabilities or privacy approval.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np
from PIL import Image


def evaluate(reference, original, processed, output, dpi=500, *, matcher=None):
    if type(dpi) is not int or not 250 <= dpi <= 2000:
        raise ValueError('configured_dpi_required')
    paths = dict(reference=Path(reference), original=Path(original), processed=Path(processed))
    before, pixels, shapes = {}, {}, {}
    for name, path in paths.items():
        before[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        with Image.open(path) as image:
            if image.width * image.height > 4_000_000 or getattr(image, 'n_frames', 1) != 1:
                raise ValueError('single_scanner_frame_required')
            rgb = np.asarray(image.convert('RGB'))
        if not np.array_equal(rgb[..., 0], rgb[..., 1]) or not np.array_equal(rgb[..., 0], rgb[..., 2]):
            raise ValueError('grayscale_scanner_required')
        pixels[name] = hashlib.sha256(rgb.tobytes()).hexdigest()
        shapes[name] = rgb.shape
    if shapes['original'] != shapes['processed']:
        raise ValueError('original_and_processed_shape_mismatch')
    if pixels['reference'] in (pixels['original'], pixels['processed']):
        raise ValueError('separately_acquired_reference_required')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    (output / 'INCOMPLETE').touch()
    if matcher is None:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ai/scripts'))
        from sourceafis_matcher import run_matcher_job
        matcher = run_matcher_job
    pairs = [dict(key=name + '_reference', probe=name, candidate='reference') for name in ('original', 'processed')]
    pairs.append(dict(key='original_processed', probe='original', candidate='processed'))
    report = dict(schema_version='blurfing-scanner-reference-v1', input_sha256=before,
                  configured_dpi=dpi, physical_dpi_verified=False, matcher='SourceAFIS', pairs=[],
                  same_finger_attested=True, privacy_validated=False,
                  note='Compare original-reference validity first. Raw scores have no new identity threshold; zero/features failure is not protection success.')
    try:
        raw = matcher(paths, pairs, dpi=float(dpi), run_name='independent_scanner_reference')
        version = raw.get('sourceafis_version')
        if not isinstance(version, str) or not version or len(raw.get('pairs', [])) != 3:
            raise ValueError('matcher_result_contract')
        report['matcher_version'] = version
        indexed = {row['key']: row for row in raw['pairs']}
        if set(indexed) != {row['key'] for row in pairs}:
            raise ValueError('matcher_pair_binding')
        for expected in pairs:
            result = indexed[expected['key']]
            score = result.get('score')
            counts = [result.get('probe_minutiae'), result.get('candidate_minutiae')]
            counts = [n if type(n) is int and n >= 0 else None for n in counts]
            measured = (result.get('status') == 'ok' and all(type(n) is int and n > 0 for n in counts)
                        and type(score) in (int, float) and math.isfinite(score) and score >= 0)
            report['pairs'].append(dict(key=expected['key'], status='measured' if measured else 'unmeasurable',
                                        score=score if measured else None,
                                        probe_minutiae=counts[0], candidate_minutiae=counts[1]))
    except Exception:
        report['pairs'] = [dict(key=p['key'], status='unavailable', score=None) for p in pairs]
    for name, path in paths.items():
        if hashlib.sha256(path.read_bytes()).hexdigest() != before[name]:
            raise ValueError('input_changed_during_evaluation')
    (output / 'report.private.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    (output / 'INCOMPLETE').unlink()
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('reference', 'original', 'processed', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--dpi', type=int, default=500)
    parser.add_argument('--same-finger-confirmed', action='store_true', required=True)
    args = parser.parse_args()
    try:
        report = evaluate(args.reference, args.original, args.processed, args.output, args.dpi)
        measured = all(pair['status'] == 'measured' for pair in report['pairs'])
        print('Independent-reference raw scores recorded; privacy protection is NOT approved.')
        raise SystemExit(0 if measured else 2)
    except (OSError, ValueError, KeyError):
        print('Reference evaluation rejected; check private files and acquisition conditions.')
        raise SystemExit(2)
