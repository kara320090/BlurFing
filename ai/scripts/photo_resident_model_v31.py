"""Explicit resident checkpoint reuse, with file and in-memory state checks."""
from contextvars import ContextVar
import hashlib
from pathlib import Path
import random

_models=ContextVar('photo_resident_verified_models',default=None)


def state_hash(model):
    value=hashlib.sha256()
    for name,tensor in sorted(model.state_dict().items()):
        value.update(name.encode());value.update(str(tensor.dtype).encode())
        value.update(str(tuple(tensor.shape)).encode());value.update(tensor.cpu().contiguous().numpy().tobytes())
    return value.hexdigest()


class Models:
    def __init__(self):self.entries={};self.token=_models.set(self)
    def verify(self):
        for model,sha,_ in self.entries.values():
            if state_hash(model)!=sha:raise ValueError('resident_model_state_changed')
    def close(self):
        self.entries.clear()
        if self.token is not None:_models.reset(self.token);self.token=None


def verified_checkpoint(path,sha,*,loader):
    models=_models.get()
    if models is None:return loader(path,sha)
    import numpy as np
    import torch
    from pad_refinement_data_contract_v2 import checked_bytes
    key=(str(Path(path).resolve()),sha)
    if key not in models.entries:
        model=loader(path,sha)
        rng=(random.getstate(),np.random.get_state(),torch.random.get_rng_state().clone())
        models.entries[key]=(model,state_hash(model),rng)
    else:
        checked_bytes(path,sha)
        model,expected,rng=models.entries[key]
        if state_hash(model)!=expected:raise ValueError('resident_model_state_changed')
        # load_model reseeds before constructing its old temporary model. Keep
        # the exact post-construction RNG state on a reuse as well.
        random.setstate(rng[0]);np.random.set_state(rng[1]);torch.random.set_rng_state(rng[2])
    return model
