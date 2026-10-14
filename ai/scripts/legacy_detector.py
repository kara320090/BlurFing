"""Preserved baseline diagnostic access. Never silently approves protection."""

def detect_legacy(rgb):
    from automatic_boundary_v1 import detect_boundaries
    return detect_boundaries(rgb)


def estimate_legacy_sam(rgb,masks,tip_hints=None):
    from sam_pad_detector import extract_pad_candidates
    return extract_pad_candidates(rgb,masks,tip_hints=tip_hints)
