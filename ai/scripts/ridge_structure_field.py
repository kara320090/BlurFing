import cv2

import numpy as np

def field_snapshots(mask, pitch, seed, checkpoints=(2, 4, 8)):
    if mask.shape != (512, 512) or not mask.any():
        raise ValueError('Nonempty 512 mask required')
    if any(isinstance(k, bool) or k not in range(1, 9) for k in checkpoints):
        raise ValueError('Iterations 1..8 required')
    ys, xs = np.where(mask); x0, x1, y0, y1 = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
    w, h = x1 - x0 + 1, y1 - y0 + 1
    rng = np.random.default_rng(seed ^ 0xB1F16)
    pattern = ['arch', 'loop', 'whorl'][int(rng.integers(0, 3))]
    base = float(rng.uniform(-.2, .2)); poles = []
    if pattern == 'loop':
        poles = [(x0 + w * rng.uniform(.42, .58), y0 + h * rng.uniform(.40, .55), .5),
                 (x0 + w * (.16 if rng.integers(0, 2) else .84), y0 + h * .79, -.5)]
    elif pattern == 'whorl':
        poles = [(x0 + w * .42, y0 + h * .45, .5), (x0 + w * .58, y0 + h * .45, .5),
                 (x0 + w * .16, y0 + h * .8, -.5), (x0 + w * .84, y0 + h * .8, -.5)]
    yy, xx = np.mgrid[:512, :512]
    angle = np.full((512, 512), base, np.float32)
    for px, py, charge in poles:
        angle += charge * np.arctan2(yy - py, xx - px).astype(np.float32)
    if pattern == 'arch':
        angle += .55 * np.tanh((xx - (x0 + x1) / 2) / max(w * .3, 1)) * np.exp(-((yy - (y0 + h * .42)) / max(h * .45, 1)) ** 2)
    kernels = []
    for theta in np.arange(24) * np.pi / 24:
        kernel = cv2.getGaborKernel((61, 61), pitch * .65, theta, pitch, .4, 0, ktype=cv2.CV_32F)
        kernel -= kernel.mean(); kernel /= max(float(np.linalg.norm(kernel)), 1e-6); kernels.append(kernel)
    index = np.mod(angle, np.pi) * 24 / np.pi
    lo = np.floor(index).astype(int) % 24; hi = (lo + 1) % 24; blend = (index - np.floor(index)).astype(np.float32)
    texture = np.random.default_rng(seed).standard_normal((512, 512)).astype(np.float32)
    results = {}
    for iteration in range(1, max(checkpoints) + 1):
        field = np.zeros_like(texture)
        for j, kernel in enumerate(kernels):
            filtered = cv2.filter2D(texture, -1, kernel, borderType=cv2.BORDER_REFLECT_101)
            field += filtered * ((lo == j) * (1 - blend) + (hi == j) * blend)
        field -= float(field[mask].mean()); field /= max(float(field[mask].std()), 1e-6)
        texture = np.tanh(field).astype(np.float32)
        if iteration in checkpoints:
            result = texture.copy(); result -= float(result[mask].mean()); result /= max(float(result[mask].std()), 1e-6)
            results[iteration] = (result, dict(pattern=pattern, base_normal_angle=base, poles=poles,
                iterations=iteration, gabor_bins=24, original_phase_input=False,
                original_pixels_input=False, other_finger_donor=False, periodic_angle_perturbation=False))
    return results
