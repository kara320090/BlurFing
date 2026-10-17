"""Bounded camera-pixel texture summaries and independent band synthesis.

Only <=48 four-scalar contrast vectors cross the source/renderer boundary.
They are appearance statistics, not validated biometric privacy features.
"""
import cv2
import numpy as np
from scipy import ndimage

SIGMAS = (.65, 1.4, 3.2, 7., 15.)
TILE = 256
MAX_SAMPLES_PER_CELL = 4096
MAX_PIXELS = 4*1024*1024
MAX_BBOX = 8*1024*1024


def kernel(sigma):
    radius = int(np.ceil(4*sigma))
    x = np.arange(-radius, radius+1, dtype=float)
    a = np.exp(-.5*(x/sigma)**2)
    return a/a.sum()


def blur(a, sigma):
    k = kernel(sigma)
    return cv2.sepFilter2D(a, -1, k, k, borderType=cv2.BORDER_REFLECT_101)


def observe(pixels, local, u, v, width, length, *, tile=TILE):
    """No resize: filter bounded tiles with exact finite-kernel halos."""
    if (not isinstance(local, np.ndarray) or local.ndim != 2 or local.dtype != np.bool_
            or local.size > MAX_BBOX or not all(local.shape)):
        raise ValueError('texture_mask_resource_or_dtype_contract')
    if (type(tile) is not int or not 32 <= tile <= 512 or len(pixels) > MAX_PIXELS
            or pixels.shape != (int(local.sum()), 3) or pixels.dtype != np.uint8):
        raise ValueError('texture_pixel_resource_or_dtype_contract')
    if (u.shape != (len(pixels),) or v.shape != u.shape or not np.isfinite(u).all()
            or not np.isfinite(v).all() or not np.isfinite([width,length]).all()
            or width <= 0 or length <= 0):
        raise ValueError('texture_geometry_contract')
    nx, ny = min(6, max(1, int(width)//80)), min(8, max(1, int(length)//80))
    cells = np.clip(((v+1)*ny/2).astype(int),0,ny-1)*nx+np.clip(((u+1)*nx/2).astype(int),0,nx-1)
    y, x = np.nonzero(local)
    valid = ndimage.distance_transform_edt(np.pad(local,1))[1:-1,1:-1][local] > 16
    selected = []
    for cell in np.unique(cells[valid]):
        take = np.flatnonzero(valid & (cells == cell))
        if len(take) < 32: continue
        # Fixed random subsampling avoids regular-grid alias with periodic ridges.
        if len(take) > MAX_SAMPLES_PER_CELL:
            take = np.random.default_rng(0xCA1800+int(cell)).choice(take,MAX_SAMPLES_PER_CELL,replace=False)
        selected.append(take)
    stats = np.zeros((ny,nx,4)); seen = np.zeros((ny,nx),bool)
    maximum_tile = [0,0]
    if selected:
        indices = np.concatenate(selected); qy, qx = y[indices], x[indices]
        bands = np.empty((len(indices),4),np.float32)
        gray = np.zeros(local.shape,np.float32)
        gray[local] = pixels @ np.array([.299,.587,.114])
        weight = local.astype(np.float32)
        stride = (local.shape[1]+tile-1)//tile
        groups = qy//tile*stride+qx//tile
        halo = int(np.ceil(4*max(SIGMAS)))
        for group in np.unique(groups):
            top,left = (int(group)//stride)*tile,(int(group)%stride)*tile
            bottom,right = min(top+tile,local.shape[0]),min(left+tile,local.shape[1])
            a,b = max(0,top-halo),max(0,left-halo)
            c,d = min(local.shape[0],bottom+halo),min(local.shape[1],right+halo)
            g,w = gray[a:c,b:d],weight[a:c,b:d]
            maximum_tile = [int(n) for n in np.maximum(maximum_tile,g.shape)]
            points = np.flatnonzero(groups == group)
            query = (qy[points]-a,qx[points]-b)
            values = [blur(g,s)[query]/np.maximum(blur(w,s)[query],1e-6) for s in SIGMAS]
            bands[points] = np.column_stack([p-q for p,q in zip(values,values[1:])])
        for cell in np.unique(cells[indices]):
            take = bands[cells[indices] == cell]
            row,col = divmod(int(cell),nx)
            stats[row,col] = 1.4826*np.median(abs(take-np.median(take,axis=0)),axis=0)
            seen[row,col] = True
        near = ndimage.distance_transform_edt(~seen,return_distances=False,return_indices=True)
        stats = ndimage.gaussian_filter(stats[tuple(near)],(.5,.5,0),mode='nearest')
    stats = np.clip(stats,0,16.)
    return stats, dict(method='tiled_source_pixel_multiband_MAD',grid=[nx,ny],
        source_pixel_filter_sigmas=list(SIGMAS),analysis_scale=1.,
        maximum_statistics=nx*ny*4,populated_cells=int(seen.sum()),energies=stats.tolist(),
        maximum_samples_per_cell=MAX_SAMPLES_PER_CELL,maximum_filtered_tile_shape=maximum_tile,
        source_phase_exported=False,source_orientation_exported=False,
        source_filtered_raster_exported=False,calibrated_focus_measurement=False)


def missing_gains(target,existing):
    if (target.shape != existing.shape or target.ndim != 3 or target.shape[2] != 4
            or not 1 <= target.shape[0] <= 8 or not 1 <= target.shape[1] <= 6
            or not np.isfinite(target).all() or not np.isfinite(existing).all()
            or np.any(target < 0) or np.any(existing < 0)):
        raise ValueError('texture_energy_contract')
    # This is an opt-in appearance gain, never a native acceptance threshold.
    return np.clip(target/np.maximum(existing,.05)-1.,0.,2.)


def equalize_generated(detail,local,u,v,gains,*,tile=TILE):
    """Only filter independently generated material, never source RGB residuals."""
    from photo_synthetic_replacement_v10 import sample_style
    if (not isinstance(local,np.ndarray) or local.ndim != 2 or local.dtype != np.bool_
            or local.size > MAX_BBOX or not all(local.shape) or int(local.sum()) > MAX_PIXELS
            or type(tile) is not int or not 32 <= tile <= 512):
        raise ValueError('texture_generation_resource_contract')
    if (detail.shape != (int(local.sum()),) or not np.isfinite(detail).all()
            or u.shape != detail.shape or v.shape != detail.shape
            or not np.isfinite(u).all() or not np.isfinite(v).all()
            or gains.ndim != 3 or not 1 <= gains.shape[0] <= 8
            or not 1 <= gains.shape[1] <= 6 or gains.shape[2] != 4
            or not np.isfinite(gains).all() or np.any(gains < 0) or np.any(gains > 2)):
        raise ValueError('texture_generated_material_contract')
    if not np.any(gains): return np.zeros(len(detail))
    y,x = np.nonzero(local)
    gray = np.zeros(local.shape,np.float32);gray[local]=detail
    weight = local.astype(np.float32);amplitude = sample_style(gains,u,v)
    out = np.zeros(len(detail));stride = (local.shape[1]+tile-1)//tile
    groups = y//tile*stride+x//tile;halo = int(np.ceil(4*max(SIGMAS)))
    for group in np.unique(groups):
        top,left = int(group)//stride*tile,int(group)%stride*tile
        bottom,right = min(top+tile,local.shape[0]),min(left+tile,local.shape[1])
        a,b = max(0,top-halo),max(0,left-halo)
        c,d = min(local.shape[0],bottom+halo),min(local.shape[1],right+halo)
        points = np.flatnonzero(groups == group)
        query = (y[points]-a,x[points]-b)
        g,w = gray[a:c,b:d],weight[a:c,b:d]
        values = [blur(g,s)[query]/np.maximum(blur(w,s)[query],1e-6) for s in SIGMAS]
        out[points] = np.sum(np.column_stack([p-q for p,q in zip(values,values[1:])])*amplitude[points],axis=1)
    return out


