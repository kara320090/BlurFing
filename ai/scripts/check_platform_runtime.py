"""Read-only prerequisite check; never invokes extraction or matching."""
import argparse
import json
import shutil
import sys
from nbis_matcher import inspect_runtime
from sourceafis_matcher import _runtime

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--nbis-config')
    p.add_argument('--require-all', action='store_true')
    a = p.parse_args()
    report = {'python_compatible': sys.version_info >= (3, 10), 'checks': {}}
    for key, check in [('nbis', lambda: inspect_runtime(a.nbis_config)), ('sourceafis', _runtime)]:
        try:
            check()
            report['checks'][key] = {'status': 'ok', 'execution_performed': False}
        except (OSError, ValueError, RuntimeError, KeyError) as exc:
            report['checks'][key] = {'status': 'missing_or_invalid', 'reason': str(exc)}
    report['javac_available'] = bool(shutil.which('javac') or shutil.which('javac.exe'))
    print(json.dumps(report, indent=2))
    return 0 if report['python_compatible'] and (not a.require_all or
        all(v['status'] == 'ok' for v in report['checks'].values()) and report['javac_available']) else 1

if __name__ == '__main__':
    raise SystemExit(main())
