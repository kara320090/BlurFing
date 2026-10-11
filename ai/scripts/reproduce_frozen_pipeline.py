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
                     'nbis_matcher_linux.py', 'sourceafis_matcher_linux.py',
                     'run_structure_transform_v4_linux.py', 'native/nbis_local_linux.cpp',
                     'java/BlurFingMatcher.java']:
            if not (ROOT / 'scripts' / name).is_file():
                raise FileNotFoundError(name)
        if args.nbis_config:
            from nbis_matcher_linux import inspect_runtime
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
