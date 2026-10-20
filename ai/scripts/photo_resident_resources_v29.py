"""Owned resident model/pool resources; one request at a time, bounded IPC."""
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
import json
import multiprocessing
import os
from pathlib import Path
import queue
import subprocess
import threading
import uuid


def _fit_init():
    # Each fit uses small matrices. Avoid 4 processes each creating 32 BLAS threads.
    for name in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):os.environ[name]='1'


def _warm_fit(_):
    import photo_junction_appearance_v23
    return os.getpid()


class SemanticClient:
    def __init__(self,python,source,model):
        self.frames=queue.Queue(maxsize=2);self.sequence=None
        command=[str(python),str(Path(__file__).with_name('photo_resident_semantics_v29.py')),
            '--external-source',str(source),'--model',str(model)]
        self.process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
            text=True,encoding='utf-8',bufsize=1,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        self.reader=threading.Thread(target=self._read,daemon=True);self.reader.start()
        try:
            if self.frames.get(timeout=180)!={'status':'ready','protocol':'photo-semantic-resident-v29'}:
                raise ValueError('semantic_worker_not_ready')
        except BaseException:self.close();raise
    def _read(self):
        try:
            while True:
                line=self.process.stdout.readline(16385)
                if not line or len(line)>16384 or not line.endswith('\n'):break
                self.frames.put(json.loads(line))
        finally:
            try:self.frames.put_nowait(None)
            except queue.Full:pass
    @contextmanager
    def job(self,source,output):
        if self.sequence is not None or self.process.poll() is not None:raise ValueError('semantic_worker_unavailable')
        self.sequence=uuid.uuid4().hex
        try:
            self.process.stdin.write(json.dumps(dict(id=self.sequence,input=str(source),output=str(output)))+'\n')
            self.process.stdin.flush()
            yield self
            if self.sequence is not None:raise ValueError('semantic_worker_result_not_consumed')
        except BaseException:self.close();raise
    def finish(self):
        if self.sequence is None:return
        frame=self.frames.get(timeout=300)
        if frame!={'status':'ok','id':self.sequence}:raise ValueError('semantic_worker_result_mismatch')
        self.sequence=None
    def close(self):
        process=self.process
        if process.poll() is None:
            if os.name=='nt':subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),check=False)
            if process.poll() is None:process.kill()
        process.wait(timeout=15)
        for stream in (process.stdin,process.stdout):
            try:stream.close()
            except (OSError,ValueError):pass
        self.reader.join(timeout=5)


class Resources:
    def __init__(self):
        self.semantic=SemanticClient(os.environ['BLURFING_COLFISPOOF_PYTHON'],
            os.environ['BLURFING_COLFISPOOF_SOURCE'],os.environ['BLURFING_COLFISPOOF_MODEL'])
        self.fit_pool=None
        try:
            self.fit_pool=ProcessPoolExecutor(max_workers=4,mp_context=multiprocessing.get_context('spawn'),initializer=_fit_init)
            list(self.fit_pool.map(_warm_fit,range(4)))
        except BaseException:self.close();raise
    def semantic_job(self,source,output):return self.semantic.job(source,output)
    def close(self):
        self.semantic.close()
        if self.fit_pool is not None:self.fit_pool.shutdown(wait=True,cancel_futures=True)
