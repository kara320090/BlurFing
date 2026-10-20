"""Request-scoped, bounded parallel evaluation of unchanged V23 patch fits."""
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
from contextvars import ContextVar
import multiprocessing
import os

MAX_WORKERS = 8
MAX_TASKS = 96
_session = ContextVar("junction_fit_session", default=None)


def _fit(task):
    # Workers load the appearance code, not the detector/model runtime.
    from photo_junction_appearance_v23 import fit_patch
    return fit_patch(*task)


class _Session:
    def __init__(self, workers, pool=None):
        self.workers = workers
        self.executor = pool
        self.owns_executor = pool is None

    def fit(self, tasks):
        if self.executor is None:
            self.executor = ProcessPoolExecutor(
                max_workers=self.workers, mp_context=multiprocessing.get_context("spawn"))
        # map preserves node order regardless of worker completion order.
        return list(self.executor.map(_fit, tasks, chunksize=1))

    def close(self):
        if self.executor is not None and self.owns_executor:
            self.executor.shutdown(wait=True, cancel_futures=True)


@contextmanager
def fit_session(workers=None, *, pool=None):
    """Reuse a lazy pool across fingers; never retain patient pixels across requests."""
    if workers is None:
        workers = min(MAX_WORKERS if pool is not None else 4, os.cpu_count() or 1)
    if type(workers) is not int or not 1 <= workers <= MAX_WORKERS:
        raise ValueError("junction_worker_limit")
    if _session.get() is not None:
        raise ValueError("junction_fit_session_already_active")
    session = _Session(workers, pool)
    token = _session.set(session)
    try:
        yield
    finally:
        _session.reset(token)
        session.close()


def fit_patches(tasks, serial_fit):
    if len(tasks) > MAX_TASKS:
        raise ValueError("junction_task_limit")
    session = _session.get()
    if session is None or session.workers == 1 or len(tasks) < 2:
        return [serial_fit(*task) for task in tasks]
    return session.fit(tasks)
