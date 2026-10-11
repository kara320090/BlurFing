from __future__ import annotations

import cv2

import numpy as np

from skimage.measure import euler_number

from highres_skeleton_preview import component_areas

def enclosed_background(binary):
    """4-connected background complements the 8-connected foreground.

    Explicitly exclude labels touching the image frame, including tiny regions.
    """
    _, labels, stats, _ = cv2.connectedComponentsWithStats(
        (~binary).astype(np.uint8), connectivity=4
    )
    enclosed = np.ones(len(stats), dtype=bool)
    enclosed[0] = False
    border_labels = np.unique(np.concatenate((labels[0], labels[-1], labels[:, 0], labels[:, -1])))
    enclosed[border_labels] = False
    return labels, stats[:, cv2.CC_STAT_AREA], enclosed

def diagnostics(binary, skeleton, roi):
    _, hole_areas, enclosed = enclosed_background(binary)
    hole_areas = hole_areas[enclosed]
    n_binary = len(component_areas(binary))
    n_skel, labels, stats, _ = cv2.connectedComponentsWithStats(
        skeleton.astype(np.uint8), connectivity=8
    )
    short_labels = np.flatnonzero(stats[:, cv2.CC_STAT_AREA] < 12)
    short_labels = short_labels[short_labels != 0]
    # Pad so the exterior of a full-frame ROI is also treated as background.
    distance = cv2.distanceTransform(np.pad(roi.astype(np.uint8), 1), cv2.DIST_L2, 5)[1:-1, 1:-1]
    short_near_edge = sum(bool(np.any(distance[labels == label] < 16)) for label in short_labels)
    euler = int(euler_number(binary, connectivity=2))
    if n_binary - euler != len(hole_areas):
        raise RuntimeError("Hole counting and Euler characteristic disagree.")
    return {
        "ridge_components": n_binary,
        "skeleton_components": n_skel - 1,
        "enclosed_cavities": len(hole_areas),
        "cavities_area_le_4px": int((hole_areas <= 4).sum()),
        "cavities_area_5_to_12px": int(((hole_areas > 4) & (hole_areas <= 12)).sum()),
        "skeleton_pixels": int(skeleton.sum()),
        "short_components_lt_12px": len(short_labels),
        "short_components_touching_16px_roi_edge": short_near_edge,
        "short_components_fully_interior": len(short_labels) - short_near_edge,
        "euler_binary": euler,
        "euler_skeleton": int(euler_number(skeleton, connectivity=2)),
    }
