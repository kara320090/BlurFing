"""Explicit development replay of exact identities; frozen exclusion stays strict.

Only the owning synchronous process/thread can replay the declared source and
its persisted canonical RGB copy. No registry, model or frozen code is edited.
"""
from contextlib import contextmanager
import os
import threading
import pad_refinement_tiles_v3 as tiles

_LOCK=threading.RLock()
_LOCAL=threading.local()
_KEYS=('source_sha256','encoded_RGB_sha256','upright_RGB_sha256')
_REASON='consumed_source_or_decoded_pixels_forbidden'


def identity_key(identity):
    if not isinstance(identity,dict) or set(identity)!=set(_KEYS):
        raise ValueError('replay_exact_identity_required')
    values=tuple(identity[k] for k in _KEYS)
    if any(not isinstance(v,str) or len(v)!=64 or any(c not in '0123456789abcdef' for c in v) for v in values):
        raise ValueError('replay_identity_hash_contract')
    return values


def consumed_roles(identity,registry):
    tiles.validate_registry(registry);identity_key(identity)
    pixels={identity[k] for k in _KEYS[1:]}
    return sorted({r['role'] for r in registry if identity['source_sha256']==r['source_sha256'] or
                   pixels & {r[k] for k in _KEYS[1:]}})


@contextmanager
def development_replay(registry,identities,*,enabled=False):
    if type(enabled) is not bool:raise ValueError('development_replay_flag_must_be_boolean')
    if not enabled:
        yield
        return
    if getattr(_LOCAL,'active',False):raise ValueError('nested_development_replay_forbidden')
    tiles.validate_registry(registry)
    allowed=frozenset(identity_key(i) for i in identities)
    if not allowed:raise ValueError('replay_exact_identity_required')
    frozen_registry=tiles.hash_json(registry);owner=(os.getpid(),threading.get_ident())
    with _LOCK:
        original=tiles.exclude_consumed
        def check(identity,current_registry):
            if ((os.getpid(),threading.get_ident())==owner and
                    tiles.hash_json(current_registry)!=frozen_registry):
                raise ValueError('replay_frozen_registry_mismatch')
            try:return original(identity,current_registry)
            except ValueError as error:
                if (str(error)!=_REASON or (os.getpid(),threading.get_ident())!=owner or
                        tiles.hash_json(current_registry)!=frozen_registry or identity_key(identity) not in allowed):
                    raise
        try:
            _LOCAL.active=True
            tiles.exclude_consumed=check
            yield
        finally:
            tiles.exclude_consumed=original
            _LOCAL.active=False
