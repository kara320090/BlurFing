from __future__ import annotations

from dataclasses import dataclass

import cv2

import numpy as np

from scipy.optimize import linear_sum_assignment

from highres_ridge_quality import mask_distance

@dataclass(frozen=True)
class ValidationConfig:
    arm_radius: int = 12
    node_radius: int = 3
    min_component_pixels: int = 12
    roi_guard_px: float = 16.0
    match_radius_px: float = 6.0
    tile_size: int = 80
    tile_context: int = 16
    anchor_cell: int = 16
    max_pair_distance: float = 32.0

def crossing_numbers(skeleton):
    """Circular 8-neighbor transitions / 2; avoid array-edge wraparound."""
    mask = np.asarray(skeleton, dtype=bool)
    if mask.ndim != 2:
        raise ValueError("Skeleton must be a two-dimensional boolean mask.")
    h, w = mask.shape
    p = np.pad(mask, 1)
    offsets = [(-1, 0), (-1, 1), (0, 1), (1, 1),
               (1, 0), (1, -1), (0, -1), (-1, -1)]
    neighbors = np.stack([p[1+dy:1+dy+h, 1+dx:1+dx+w] for dy, dx in offsets])
    cn = np.sum(neighbors != np.roll(neighbors, -1, axis=0), axis=0) // 2
    return np.where(mask, cn, 0).astype(np.uint8)

def local_arm_count(skeleton, x, y, config=ValidationConfig()):
    """Count distinct supported arms after removing a small node disk.

    Isolate the candidate's connected component INSIDE the radius first, so
    unrelated parallel ridges are not counted. A loop that rejoins inside the
    disk can reduce the count. Closely spaced true minutiae can also fail this
    conservative diagnostic; rejection does not mean a false minutia.
    """
    r, inner = config.arm_radius, config.node_radius
    h, w = skeleton.shape
    x0, x1, y0, y1 = max(0, x-r), min(w, x+r+1), max(0, y-r), min(h, y+r+1)
    yy, xx = np.indices((y1-y0, x1-x0))
    radial = np.hypot(xx+x0-x, yy+y0-y)
    local = skeleton[y0:y1, x0:x1] & (radial <= r)
    _, labels = cv2.connectedComponents(local.astype(np.uint8), connectivity=8)
    component_id = int(labels[y-y0, x-x0])
    if not component_id:
        raise ValueError("Arm analysis requires a skeleton pixel.")
    component = labels == component_id
    arms = component & (radial > inner)
    count, arm_labels = cv2.connectedComponents(arms.astype(np.uint8), connectivity=8)
    supported, rays = 0, []
    for label in range(1, count):
        arm = arm_labels == label
        if not np.any(arm & (radial <= inner+1.5)):
            continue
        if not np.any(arm & (radial >= r-1.5)):
            continue
        supported += 1
        yy_arm, xx_arm = np.nonzero(arm & (radial >= r-2))
        rays.append(float(np.degrees(np.arctan2(np.mean(yy_arm+y0-y), np.mean(xx_arm+x0-x))) % 360))
    return supported, sorted(rays)

def extract_candidates(skeleton, roi=None, safe=None, config=ValidationConfig()):
    skeleton = np.asarray(skeleton, dtype=bool)
    roi = np.ones_like(skeleton) if roi is None else np.asarray(roi, dtype=bool)
    safe = roi if safe is None else np.asarray(safe, dtype=bool)
    if not (skeleton.shape == roi.shape == safe.shape):
        raise ValueError("Skeleton and support masks must have identical dimensions.")
    cn = crossing_numbers(skeleton)
    _, component_labels, component_stats, _ = cv2.connectedComponentsWithStats(
        skeleton.astype(np.uint8), connectivity=8)
    roi_distance = mask_distance(roi)
    candidates = []
    for kind, value in (("ending", 1), ("bifurcation", 3), ("complex", 4)):
        raw = skeleton & (cn == value)
        n, labels = cv2.connectedComponents(raw.astype(np.uint8), connectivity=8)
        ys, xs = np.nonzero(raw)
        groups = {}
        for y, x in zip(ys.tolist(), xs.tolist()):
            groups.setdefault(int(labels[y, x]), []).append((y, x))
        for label in range(1, n):
            points = np.array(groups[label])
            center = points.mean(axis=0)
            y, x = points[np.argmin(np.sum((points-center)**2, axis=1))].tolist()
            arm_count, rays = local_arm_count(skeleton, x, y, config)
            comp_size = int(component_stats[component_labels[y, x], cv2.CC_STAT_AREA])
            flags = []
            if roi_distance[y, x] < config.roi_guard_px:
                flags.append("roi_boundary")
            if not safe[y, x]:
                flags.append("outside_guarded_quality")
            if comp_size < config.min_component_pixels:
                flags.append("short_component")
            if kind == "complex":
                flags.append("complex_crossing")
            elif arm_count != (1 if kind == "ending" else 3):
                flags.append("unsupported_local_arms")
            candidates.append({"x": x, "y": y, "type": kind, "crossing_number": value,
                               "cluster_pixels": len(points), "supported_arms": arm_count,
                               "arm_directions_image_deg": rays, "component_pixels": comp_size,
                               "inside_guarded_quality": bool(safe[y, x]), "flags": flags})
    candidates.sort(key=lambda p: (p["y"], p["x"], p["type"]))
    for i, candidate in enumerate(candidates):
        candidate["candidate_id"] = i
    return candidates

def match_points(reference, predicted, radius=6.0, respect_type=True):
    """Maximum-cardinality one-to-one matching, then minimum distance.

    Explicit dummy columns keep a forbidden pairing from displacing an allowed
    match. Distance exactly equal to radius is allowed; neither set is mutated.
    """
    if not np.isfinite(radius) or radius <= 0:
        raise ValueError("Match radius must be positive and finite.")
    if not reference or not predicted:
        return []
    a = np.array([[p["x"], p["y"]] for p in reference], dtype=float)
    b = np.array([[p["x"], p["y"]] for p in predicted], dtype=float)
    distance = np.linalg.norm(a[:, None]-b[None, :], axis=2)
    allowed = distance <= radius
    if respect_type:
        allowed &= np.array([[p["type"] == q["type"] or p["type"] == "unknown"
                             for q in predicted] for p in reference])
    penalty = (max(len(reference), len(predicted))+1)*(radius+1)
    costs = np.full((len(reference), len(predicted)+len(reference)), penalty, dtype=float)
    costs[:, :len(predicted)] = np.where(allowed, distance, penalty*3)
    rows, cols = linear_sum_assignment(costs)
    return [(int(i), int(j), float(distance[i, j])) for i, j in zip(rows, cols)
            if j < len(predicted) and allowed[i, j]]
