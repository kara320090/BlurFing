"""Independent ridge synthesis in a frame whose Y axis follows the finger.

V3-specific normal/tangent convention; the frozen ridge_structure_field stays
unchanged. A Gabor theta is the ridge NORMAL, so an across-finger arch starts
near pi/2 in this frame. Shape/seed are the only inputs, not source intensities.
"""
import cv2
import numpy as np
from irregular_synthetic_ridge_field import deform_synthetic_field


def orientation(mask, seed):
    if mask.shape != (512, 512) or mask.dtype != np.bool_ or not mask.any():
        raise ValueError('Nonempty Boolean 512 mask required')
    ys, xs = np.where(mask)
    x0, x1, y0, y1 = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
    w, h = x1-x0+1, y1-y0+1
    rng = np.random.default_rng(seed ^ 0xB1F16)
    pattern = ['arch', 'loop', 'whorl'][int(rng.integers(0, 3))]
    base = float(rng.uniform(-.2, .2)); poles = []
    if pattern == 'loop':
        poles = [(x0+w*rng.uniform(.42, .58), y0+h*rng.uniform(.40, .55), .5),
                 (x0+w*(.16 if rng.integers(0, 2) else .84), y0+h*.79, -.5)]
    elif pattern == 'whorl':
        poles = [(x0+w*.42, y0+h*.45, .5), (x0+w*.58, y0+h*.45, .5),
                 (x0+w*.16, y0+h*.8, -.5), (x0+w*.84, y0+h*.8, -.5)]
    yy, xx = np.mgrid[:512, :512]
    angle = np.full((512, 512), np.pi/2+base, np.float32)
    for px, py, charge in poles:
        angle += charge*np.arctan2(yy-py, xx-px).astype(np.float32)
    if pattern == 'arch':
        angle += .55*np.tanh((xx-(x0+x1)/2)/max(w*.3, 1))*np.exp(-((yy-(y0+h*.42))/max(h*.45, 1))**2)
    return angle, dict(pattern=pattern, base_normal_angle=np.pi/2+base, poles=poles,
        coordinate_frame='Y_along_finger_X_across_finger', angle_is_ridge_normal=True,
        original_phase_input=False, original_pixels_input=False, other_finger_donor=False)


def independent_photographic_field(mask, pitch, seed):
    if not np.isfinite(pitch) or not 4 <= pitch <= 16:
        raise ValueError('V3 synthesis pitch must be between 4 and 16 canonical pixels')
    angle, recipe = orientation(mask, seed)
    kernels = []
    for theta in np.arange(24)*np.pi/24:
        kernel = cv2.getGaborKernel((61, 61), pitch*.65, theta, pitch, .4, 0, ktype=cv2.CV_32F)
        kernel -= kernel.mean(); kernel /= max(float(np.linalg.norm(kernel)), 1e-6)
        kernels.append(kernel)
    index = np.mod(angle, np.pi)*24/np.pi
    lo = np.floor(index).astype(int)%24; hi = (lo+1)%24
    blend = (index-np.floor(index)).astype(np.float32)
    texture = np.random.default_rng(seed).standard_normal((512, 512)).astype(np.float32)
    for _ in range(2):
        field = np.zeros_like(texture)
        for j, kernel in enumerate(kernels):
            filtered = cv2.filter2D(texture, -1, kernel, borderType=cv2.BORDER_REFLECT_101)
            field += filtered*((lo == j)*(1-blend)+(hi == j)*blend)
        field -= float(field[mask].mean()); field /= max(float(field[mask].std()), 1e-6)
        texture = np.tanh(field).astype(np.float32)
    texture -= float(texture[mask].mean()); texture /= max(float(texture[mask].std()), 1e-6)
    result, deformation = deform_synthetic_field(texture, pitch, seed)
    return result, recipe | dict(iterations=2, gabor_bins=24, deformation=deformation)
