"""Overlap independent model startup; always reap owned child processes."""
from contextlib import contextmanager
import math
import os
import subprocess
import time


class PendingWorker:
    def __init__(self,command,timeout):
        if type(timeout) not in (int,float) or not math.isfinite(timeout) or timeout<=0:
            raise ValueError('positive_worker_timeout_required')
        self.command=command;self.deadline=time.monotonic()+timeout
        self.process=subprocess.Popen(command,shell=False,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        self.completed=False;self.stderr=None

    def finish(self):
        if not self.completed:
            try:
                _,self.stderr=self.process.communicate(timeout=max(.001,self.deadline-time.monotonic()))
            except BaseException:
                self.close();raise
            self.completed=True
        if self.process.returncode:
            raise subprocess.CalledProcessError(self.process.returncode,self.command,stderr=self.stderr)

    def close(self):
        if not self.completed:
            if self.process.poll() is None:
                if os.name=='nt':
                    # Windows venv launchers own a second Python process. Kill
                    # only this job's subtree so inherited pipes cannot hang.
                    subprocess.run(['taskkill','/PID',str(self.process.pid),'/T','/F'],
                        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False,
                        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                if self.process.poll() is None:self.process.kill()
            _,self.stderr=self.process.communicate()
            self.completed=True


@contextmanager
def pending_worker(command,timeout=300):
    job=PendingWorker(command,timeout)
    try:yield job
    finally:job.close()
