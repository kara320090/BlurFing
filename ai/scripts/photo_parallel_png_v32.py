"""Lossless RGB8 PNG with parallel deflate blocks in ONE zlib stream.

Each row uses the standard Sub filter. FULL_FLUSH ends intermediate blocks
with an empty dictionary; only the final block uses FINISH. One header/Adler
checksum covers the whole raster. No pixel quantization or metadata changes.
"""
from concurrent.futures import ThreadPoolExecutor
import os,struct,zlib
import numpy as np


def chunk(kind,payload):
    return struct.pack('>I',len(payload))+kind+payload+struct.pack('>I',zlib.crc32(payload,zlib.crc32(kind))&0xffffffff)


def encode(rgb,*,workers=None):
    if rgb.dtype!=np.uint8 or rgb.ndim!=3 or rgb.shape[2]!=3 or not 0<rgb.shape[0]*rgb.shape[1]<=20_000_000:
        raise ValueError('parallel_PNG_RGB8_limit')
    if workers is None:workers=min(4,os.cpu_count() or 1)
    if type(workers) is not int or not 1<=workers<=4:raise ValueError('parallel_PNG_worker_limit')
    h,w=rgb.shape[:2];pixels=np.ascontiguousarray(rgb).reshape(h,w*3)
    raw=np.empty((h,w*3+1),np.uint8);raw[:,0]=1;raw[:,1:4]=pixels[:,:3]
    np.subtract(pixels[:,3:],pixels[:,:-3],out=raw[:,4:])
    count=min(workers,h);cuts=np.linspace(0,h,count+1,dtype=int)
    def deflate(i):
        compressor=zlib.compressobj(level=1,wbits=-15)
        return compressor.compress(memoryview(raw[cuts[i]:cuts[i+1]]))+compressor.flush(zlib.Z_FINISH if i==count-1 else zlib.Z_FULL_FLUSH)
    with ThreadPoolExecutor(max_workers=count) as pool:blocks=list(pool.map(deflate,range(count)))
    payload=b'\x78\x01'+b''.join(blocks)+struct.pack('>I',zlib.adler32(memoryview(raw))&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,2,0,0,0))+chunk(b'IDAT',payload)+chunk(b'IEND',b'')
