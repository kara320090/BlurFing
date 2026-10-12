"""Run one frozen v4 transform with platform extraction and temporary outputs.

No batch evaluation, NBIS, model loading, or changes to frozen source files.
The structure-check bindings are overridden only within this invocation.
"""

import argparse

import hashlib

import json

import os

from pathlib import Path

import sys

import tempfile

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]

def load_implementation():
    # Imported legacy helpers load Matplotlib; keep its configuration cache isolated too.
    if not getattr(load_implementation, '_cache_dir', None):
        load_implementation._cache_dir = tempfile.mkdtemp(prefix='blurfing_v4_mpl_', dir=tempfile.gettempdir())
    os.environ['MPLCONFIGDIR'] = load_implementation._cache_dir
    import fingerprint_structure_check as structure
    import sourceafis_matcher as matcher
    from transform_automatic_fingerprint_poc_v4 import transform_fingerprint_photo
    return structure, matcher, transform_fingerprint_photo

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--strength', type=float, choices=(0., .5), default=.5)
    parser.add_argument('--dry-run', action='store_true',
                        help='Check imports, input and Java dependencies without transforming or writing job results')
    args = parser.parse_args()
    source = args.input.expanduser().resolve(strict=True)
    if not source.is_file():
        parser.error('Input must be a file')
    structure, matcher, transform = load_implementation()
    java, classes, jars = matcher._runtime()
    from PIL import Image, ImageOps
    import numpy as np
    source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    with Image.open(source) as im:
        original = np.array(ImageOps.exif_transpose(im).convert('RGB'))
    if args.dry_run:
        print(json.dumps(dict(input_path=str(source),shape=list(original.shape),
                              project_root=str(ROOT),java=java,
                              classes=str(classes),jars=jars,
                              output_parent=tempfile.gettempdir(),dry_run=True)))
        return

    folder = Path(tempfile.mkdtemp(prefix='blurfing_v4_linux_smoke_', dir=tempfile.gettempdir()))
    old_out, old_matcher = structure.OUT, structure.run_matcher_job
    extraction_jobs = []

    def extract(images, pairs, **kwargs):
        if pairs:
            raise RuntimeError('This functional entry point permits extraction only')
        result = matcher.run_matcher_job(images, pairs, **kwargs)
        extraction_jobs.append(result['output_folder'])
        return result

    # In-memory wiring only. v4's imported function reads these globals at call time.
    structure.OUT = folder
    structure.run_matcher_job = extract
    try:
        modified, details = transform(original, args.strength)
    finally:
        structure.OUT, structure.run_matcher_job = old_out, old_matcher
    if hashlib.sha256(source.read_bytes()).hexdigest() != source_sha:
        raise RuntimeError('Input file changed during transformation')
    if not details['outside_all_masks_preserved']:
        raise RuntimeError('Pixels outside processing masks changed')
    output = folder / 'modified.png'
    Image.fromarray(modified).save(output)
    with Image.open(output) as saved:
        if not np.array_equal(np.array(saved), modified):
            raise RuntimeError('Saved PNG differs from returned image')
    details.update(input_path=str(source),source_sha256=source_sha,
                   output_path=str(output),sourceafis_linux_jobs=extraction_jobs,
                   platform_entry_point=True)
    (folder / 'details.json').write_text(json.dumps(details,indent=2),encoding='utf-8')
    print(json.dumps(dict(output_folder=str(folder),output_path=str(output),
                          status=details['status'],applied=details['applied'],
                          changed_pixels=details['changed_pixels'],
                          transformed_regions=details['transformed_candidate_count'],
                          sourceafis_calls=len(extraction_jobs),
                          protection_verified=False,privacy_validated=False)))

if __name__ == '__main__':
    main()
