"""Public source-only check; private-data/runtime checks are explicitly optional."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--nbis-config', type=Path)
    args = parser.parse_args()
    try:
        for name in ['natural_auto_04.py', 'transform_automatic_fingerprint_poc_v4.py',
                     'transform_automatic_fingerprint_poc_v4_boundaryblend_02.py',
                     'nbis_matcher.py', 'sourceafis_matcher.py', 'platform_loader.py',
                     'run_structure_transform.py',
                     'java/BlurFingMatcher.java']:
            if not (ROOT / 'scripts' / name).is_file():
                raise FileNotFoundError(name)
        for target in ('linux', 'windows'):
            for file in ('nbis_matcher_' + target + '.py', 'sourceafis_matcher_' + target + '.py',
                         'nbis_local_' + target + '.cpp'):
                if not (ROOT / 'platform' / target / file).is_file():
                    raise FileNotFoundError(file)
        if args.nbis_config:
            from nbis_matcher import inspect_runtime
            inspect_runtime(args.nbis_config)
            print('Private NBIS runtime: ELF and SHA-256 checked; not executed')
        print('PUBLIC SOURCE CHECK PASSED; private capture/runtime validation not performed')
        print('TECHNICAL_PIPELINE_COMPLETE=true')
        print('FINAL_INDEPENDENT_VALIDATION_COMPLETE=false')
        print('PROJECT_COMPLETE=false')
        return 0
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        print('CHECK FAILED:', exc, file=sys.stderr)
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
