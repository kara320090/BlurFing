from __future__ import annotations

import numpy as np

from highres_ridge_quality import build_ridge_quality, mask_distance

from highres_minutiae_validation import ValidationConfig, extract_candidates, match_points

MINUTIA_CONFIG = ValidationConfig()

def detect_minutiae(skeleton, roi, support):
    raw = extract_candidates(skeleton, roi, support, MINUTIA_CONFIG)
    return [p for p in raw if not p['flags']]

def prepare_fingerprint(image):
    gray = np.asarray(image)
    if gray.shape != (512, 512) or gray.dtype != np.uint8:
        raise ValueError('Expected 512x512 uint8 grayscale; no implicit resize or scaling.')
    stages, stats = build_ridge_quality(gray)
    # Frozen PoC gate: no FFT quality erosion or parameter-perturbation requirement.
    # This deliberately trades expert-grade validation for a small functional PoC.
    support = stages['roi'] & (mask_distance(stages['roi']) >= 16)
    support &= (stages['contrast'] >= 8) & (stages['coherence'] >= .60)
    stages['poc_support'] = support
    points = detect_minutiae(stages['skeleton_full'], stages['roi'], support)
    return stages, points, stats

def point_similarity(before, after):
    matched = len(match_points(before, after, radius=6, respect_type=True))
    denominator = len(before) + len(after)
    return {'before_count': len(before), 'after_count': len(after), 'matched': matched,
            'removed': len(before)-matched, 'added': len(after)-matched,
            'similarity': 2*matched/denominator if denominator else None,
            'metric': 'same-coordinate same-type one-to-one Dice within 6px; not a matcher score'}

def minutiae_overlay(gray, skeleton, points):
    import cv2
    rgb = np.repeat(gray[...,None],3,axis=2)
    rgb[skeleton] = (230,60,60)
    for p in points:
        center = (p['x'], p['y'])
        if p['type'] == 'ending':
            cv2.circle(rgb, center, 3, (20,220,240), 1)
        else:
            x,y=center
            cv2.rectangle(rgb,(x-3,y-3),(x+3,y+3),(240,210,20),1)
    return rgb
