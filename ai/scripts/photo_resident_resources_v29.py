"""Owned resident model/pool resources; one request at a time, bounded IPC."""
from concurrent.futures import ProcessPoolExecutor,ThreadPoolExecutor
from contextlib import contextmanager
import json
import multiprocessing
import os
from pathlib import Path
import queue
import subprocess
import threading
import time
import uuid


def _fit_init():
    # Each fit uses small matrices. Avoid 4 processes each creating 32 BLAS threads.
    for name in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):os.environ[name]='1'


def _warm_fit(_):
    import photo_junction_appearance_v23
    return os.getpid()


class ModelClient:
    def __init__(self,command,protocol,*,timeout=300):
        self.frames=queue.Queue(maxsize=2);self.sequence=None;self.timeout=timeout
        self.process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
            text=True,encoding='utf-8',bufsize=1,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        self.reader=threading.Thread(target=self._read,daemon=True);self.reader.start()
        try:
            if self.frames.get(timeout=180)!={'status':'ready','protocol':protocol}:
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
        self.deadline=time.monotonic()+self.timeout
        try:
            self.process.stdin.write(json.dumps(dict(id=self.sequence,input=str(source),output=str(output)))+'\n')
            self.process.stdin.flush()
            yield self
            if self.sequence is not None:raise ValueError('semantic_worker_result_not_consumed')
        except BaseException:self.close();raise
    def finish(self):
        if self.sequence is None:return
        frame=self.frames.get(timeout=max(0.,self.deadline-time.monotonic()))
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


class SemanticClient(ModelClient):
    def __init__(self,python,source,model):
        super().__init__([str(python),str(Path(__file__).with_name('photo_resident_semantics_v29.py')),
            '--external-source',str(source),'--model',str(model)],'photo-semantic-resident-v29')


class HandClient(ModelClient):
    def __init__(self,python,model):
        super().__init__([str(python),str(Path(__file__).with_name('photo_resident_hand_v31.py')),
            '--model',str(model)],'photo-hand-resident-v31',timeout=60)


class Resources:
    def __init__(self):
        from photo_resident_model_v31 import Models
        self.models=Models()
        self.semantic=self.hand=None
        self.fit_pool=None
        try:
            from photo_junction_fit_runtime_v1 import MAX_WORKERS
            workers=min(MAX_WORKERS,os.cpu_count() or 1)
            self.fit_pool=ProcessPoolExecutor(max_workers=workers,mp_context=multiprocessing.get_context('spawn'),initializer=_fit_init)
            fits=[self.fit_pool.submit(_warm_fit,i) for i in range(workers)]
            errors=[]
            with ThreadPoolExecutor(max_workers=2) as loaders:
                jobs=[('semantic',loaders.submit(SemanticClient,os.environ['BLURFING_COLFISPOOF_PYTHON'],
                    os.environ['BLURFING_COLFISPOOF_SOURCE'],os.environ['BLURFING_COLFISPOOF_MODEL'])),
                    ('hand',loaders.submit(HandClient,os.environ['BLURFING_HAND_PYTHON'],os.environ['BLURFING_HAND_MODEL']))]
                for name,future in jobs:
                    try:setattr(self,name,future.result())
                    except BaseException as error:errors.append(error)
            if errors:raise errors[0]
            for future in fits:future.result()
        except BaseException:self.close();raise
    def semantic_job(self,source,output):return self.semantic.job(source,output)
    def hand_job(self,source,output):return self.hand.job(source,output)
    def close(self):
        errors=[]
        try:
            for worker in (self.semantic,self.hand):
                if worker is not None:
                    try:worker.close()
                    except BaseException as error:errors.append(error)
            if self.fit_pool is not None:
                try:self.fit_pool.shutdown(wait=True,cancel_futures=True)
                except BaseException as error:errors.append(error)
        finally:self.models.close()
        if errors:raise errors[0]
