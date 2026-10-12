"""Load platform adapters without shadowing Python's standard platform module."""
import importlib.util
from pathlib import Path
import platform
import sys

ROOT = Path(__file__).resolve().parents[1]

def load_adapter(kind, system=None):
    system = platform.system() if system is None else system
    if kind not in ('nbis', 'sourceafis'):
        raise ValueError('Unknown matcher')
    if system not in ('Linux', 'Windows'):
        raise RuntimeError('Unsupported operating system: ' + system)
    target = system.lower()
    name = '_blurfing_' + kind + '_' + target
    if name not in sys.modules:
        path = ROOT / 'platform' / target / (kind + '_matcher_' + target + '.py')
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise ImportError('Platform adapter unavailable')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        sys.modules[name] = module
    return sys.modules[name]
