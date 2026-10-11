import cv2

import numpy as np

def independent_skin_relief(mask, pitch, seed):
    if mask.ndim != 2 or mask.dtype != np.bool_ or not mask.any():
        raise ValueError('Nonempty Boolean pad mask required')
    if not np.isfinite(pitch) or pitch < 2:
        raise ValueError('Observed positive ridge pitch required')
    rng = np.random.default_rng(seed ^ 0x723D1)
    h, w = mask.shape
    raw = rng.standard_normal((h, w)).astype(np.float32)
    fine = cv2.GaussianBlur(raw, (0, 0), max(.35, pitch * .10))
    fine -= cv2.GaussianBlur(fine, (0, 0), max(.7, pitch * .32))
    fine /= max(float(fine[mask].std()), 1e-6)
    # Draw at four times resolution to avoid jagged, single-pixel creases.
    scale = 4
    canvas = np.zeros((h * scale, w * scale), np.float32)
    positions = np.argwhere(mask)
    count = max(1, round(mask.sum() / (pitch * pitch * 22)))
    for k in range(count):
        y, x = positions[rng.integers(len(positions))]
        angle = rng.uniform(0, np.pi)
        length = pitch * rng.uniform(1.2, 4.0)
        bend = pitch * rng.uniform(-.18, .18)
        t = np.linspace(-.5, .5, 9)
        xs = x + np.cos(angle) * t * length - np.sin(angle) * bend * (1 - 4*t*t)
        ys = y + np.sin(angle) * t * length + np.cos(angle) * bend * (1 - 4*t*t)
        points = np.rint(np.column_stack([xs, ys]) * scale).astype(np.int32)
        cv2.polylines(canvas, [points], False, float(rng.uniform(.6, 1.0)),
                      max(1, round(pitch * rng.uniform(.09, .16) * scale)))
    creases = cv2.resize(canvas, (w, h), interpolation=cv2.INTER_AREA)
    creases = cv2.GaussianBlur(creases, (0, 0), max(.3, pitch*.08))
    # A light shoulder beside a shallow crease gives surface relief, not ink.
    shoulder = cv2.GaussianBlur(creases, (0, 0), max(.65, pitch*.25))
    relief = shoulder - creases
    relief -= float(relief[mask].mean())
    relief /= max(float(relief[mask].std()), 1e-6)
    surface = .55*fine + .8*np.clip(relief, -3, 3)
    surface -= float(surface[mask].mean())
    surface /= max(float(surface[mask].std()), 1e-6)
    surface = np.clip(surface, -4, 4).astype(np.float32)
    surface[~mask] = 0
    return surface, dict(method='independent shallow skin creases and fine relief',
        crease_count=count, seed=seed, source_pixels_input=False,
        source_phase_input=False, source_orientation_input=False,
        another_fingerprint_donor=False, human_naturalness_validated=False)
