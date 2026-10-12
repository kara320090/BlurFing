"""Common NBIS interface; dispatches at call time, never launches on import."""
import os
from platform_loader import load_adapter

def inspect_runtime(config_path=None):
    return load_adapter('nbis').inspect_runtime(config_path or os.environ.get('BLURFING_NBIS_CONFIG'))

def run_nbis_job(images, pairs, *, run_name):
    adapter = load_adapter('nbis')
    return adapter.run_nbis_job(images, pairs, run_name=run_name)
