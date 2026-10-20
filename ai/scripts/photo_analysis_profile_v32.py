"""Explicit semantic inference scale; native RGB and V27 rendering are retained.

Fast mode changes semantic masks and is experimental, not pixel-equivalent.
"""
PROFILES=('native','fast_v32')
SEMANTIC_INPUT_SIDE=1536


def profile(value):
    if value not in PROFILES:raise ValueError('unsupported_photo_analysis_profile')
    return value
