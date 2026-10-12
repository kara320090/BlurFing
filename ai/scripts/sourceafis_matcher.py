"""Common SourceAFIS interface; shared Java source and platform runtime wiring."""
from platform_loader import load_adapter

def _runtime():
    return load_adapter('sourceafis')._runtime()

def run_matcher_job(images, pairs, *, dpi=500., run_name='poc_matcher'):
    return load_adapter('sourceafis').run_matcher_job(images, pairs, dpi=dpi, run_name=run_name)

def match_fingerprints(probe_path, candidate_path, *, dpi=500.):
    return load_adapter('sourceafis').match_fingerprints(probe_path, candidate_path, dpi=dpi)
