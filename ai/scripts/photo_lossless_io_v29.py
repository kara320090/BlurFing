"""Request-scoped lossless PNG acceleration; never cache inference results.

Decoded inputs are keyed by a fresh SHA256 of their complete encoded bytes.
Every caller still performs its original source/model/asset verification.
The bounded cache is destroyed at request exit, including exceptions.
"""
from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
import copy
import hashlib
import io
import os
from pathlib import Path
import struct
import zlib
import cv2
import numpy as np
from PIL import Image

_state=ContextVar('photo_lossless_io',default=None)
_open=Image.open
_save=Image.Image.save
_read_bytes=Path.read_bytes
MAX_ENCODED=32*1024**2
MAX_CACHE=192*1024**2
MAX_FILE_CACHE=128*1024**2


class State:
    def __init__(self):
        self.cache=OrderedDict();self.bytes=0;self.hits=0;self.encodes=0
        self.files=OrderedDict();self.file_bytes=0;self.pins={};self.file_hits=0
    def verify_files(self):
        for path,sha in self.pins.items():
            if hashlib.sha256(_read_bytes(path)).digest()!=sha:raise ValueError('request_file_snapshot_changed')
    def clear(self):
        self.cache.clear();self.bytes=0;self.files.clear();self.file_bytes=0;self.pins.clear()


def _identity(path):
    stat=path.stat()
    return stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns


def _read_snapshot(path):
    state=_state.get()
    if state is None or path.suffix.lower() not in ('.png','.pt','.npz','.json'):return _read_bytes(path)
    path=path.absolute();identity=_identity(path)
    if path in state.files:
        previous,data=state.files.pop(path)
        if previous==identity:
            state.files[path]=(previous,data);state.file_hits+=1
            return data
        state.file_bytes-=len(data)
    data=_read_bytes(path)
    if _identity(path)!=identity:raise ValueError('request_file_changed_during_read')
    state.pins[path]=hashlib.sha256(data).digest()
    if len(data)<=MAX_FILE_CACHE:
        while state.files and state.file_bytes+len(data)>MAX_FILE_CACHE:
            _,(_,old)=state.files.popitem(last=False);state.file_bytes-=len(old)
        state.files[path]=(identity,data);state.file_bytes+=len(data)
    return data


def _content(fp):
    if isinstance(fp,io.BytesIO):
        return fp.getvalue() if fp.getbuffer().nbytes<=MAX_ENCODED else None
    if isinstance(fp,(str,bytes,os.PathLike)):
        if Path(fp).stat().st_size>MAX_ENCODED:return None
        data=Path(fp).read_bytes()
        return data if len(data)<=MAX_ENCODED else None
    return None


def _opened(fp,mode='r',formats=None):
    state=_state.get()
    if state is None or mode!='r' or (formats is not None and 'PNG' not in formats):return _open(fp,mode,formats)
    data=_content(fp)
    if (data is None or len(data)<33 or data[:8]!=b'\x89PNG\r\n\x1a\n' or data[12:16]!=b'IHDR'):
        return _open(fp,mode,formats)
    width,height=struct.unpack('>II',data[16:24])
    if not 0<width<=32768 or not 0<height<=32768 or width*height>20_000_000:return _open(fp,mode,formats)
    key=hashlib.sha256(data).digest()
    if key in state.cache:
        kind,size,raw,info=state.cache.pop(key);state.cache[key]=(kind,size,raw,info)
        image=Image.frombytes(kind,size,raw);image.info=copy.deepcopy(info);image.format='PNG'
        image.filename=os.fspath(fp) if isinstance(fp,(str,bytes,os.PathLike)) else ''
        state.hits+=1
        return image
    image=_open(io.BytesIO(data),mode,formats)
    if image.mode not in ('RGB','L') or getattr(image,'n_frames',1)!=1:return image
    image.load();raw=image.tobytes()
    if len(raw)<=MAX_CACHE:
        while state.cache and state.bytes+len(raw)>MAX_CACHE:
            _,record=state.cache.popitem(last=False);state.bytes-=len(record[2])
        state.cache[key]=(image.mode,image.size,raw,copy.deepcopy(image.info));state.bytes+=len(raw)
    return image


def _saved(image,fp,format=None,**params):
    state=_state.get()
    png=(str(format).upper()=='PNG' if format else
         isinstance(fp,(str,bytes,os.PathLike)) and str(fp).lower().endswith('.png'))
    allowed={'compress_level','exif'}
    if (state is None or not png or image.mode not in ('RGB','L') or image.info or
            not set(params)<=allowed):return _save(image,fp,format,**params)
    level=params.get('compress_level',1)
    if type(level) is not int or not 0<=level<=9:return _save(image,fp,format,**params)
    exif=params.get('exif',b'')
    if isinstance(exif,Image.Exif):exif=exif.tobytes()
    if not isinstance(exif,bytes):return _save(image,fp,format,**params)
    if exif.startswith(b'Exif\0\0'):exif=exif[6:]
    values=np.asarray(image)
    if image.mode=='RGB':values=cv2.cvtColor(values,cv2.COLOR_RGB2BGR)
    success,encoded=cv2.imencode('.png',values,[cv2.IMWRITE_PNG_COMPRESSION,level])
    if not success:raise OSError('lossless_PNG_encode_failed')
    content=encoded.tobytes()
    if exif:
        chunk=b'eXIf'+exif
        content=content[:33]+struct.pack('>I',len(exif))+chunk+struct.pack('>I',zlib.crc32(chunk)&0xffffffff)+content[33:]
    # A faster compressor must not reject an image the old 15 MiB wire
    # encoder could handle. Retry the original encoder for large RGB PNGs.
    if image.mode=='RGB' and len(content)>15*1024**2 and 'compress_level' not in params:
        return _save(image,fp,format,**params)
    if isinstance(fp,(str,bytes,os.PathLike)):
        with open(fp,'wb') as stream:stream.write(content)
    else:fp.write(content)
    state.encodes+=1


@contextmanager
def lossless_io():
    # Hooks are inert in other contexts/threads. No raster survives the scope.
    Image.open=_opened;Image.Image.save=_saved;Path.read_bytes=_read_snapshot
    import photo_mask_roi_v29 as sparse
    sparse.install();sparse_token=sparse.enabled.set(True)
    state=State();token=_state.set(state)
    try:yield state
    finally:
        try:state.verify_files()
        finally:state.clear();_state.reset(token);sparse.enabled.reset(sparse_token)
