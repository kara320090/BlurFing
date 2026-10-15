"""Independent protection source inventory; never part of the V6 training hash.

Capture all selected public sources before work and compare the complete set
after work. Keys are AI-root-relative POSIX paths; values hash exact bytes.
External runtimes/weights/data retain their existing separate asset contracts.
"""
from dataclasses import dataclass
import hashlib,json,os,stat
from pathlib import Path
from types import MappingProxyType

VERSION='protection_runtime_source_snapshot_v1'
SOURCE_DIRECTORIES=('scripts','platform')
SOURCE_SUFFIXES=frozenset({'.py','.java','.ps1','.c','.cpp','.h','.hpp'})
EXCLUDED_DIRECTORIES=frozenset({'.git','.venv','venv','__pycache__','.pytest_cache','.mypy_cache','.ruff_cache',
    '.tox','.nox','site-packages','node_modules','vendor','third_party','third-party','thirdparty','external',
    'private','weights','cache','caches'})


def _reparse(path):
    info=path.lstat()
    return path.is_symlink() or bool(getattr(info,'st_file_attributes',0)&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',0))


def _identity(info):
    return info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns


def _hash_source(path,root):
    before=path.lstat()
    if _reparse(path) or not stat.S_ISREG(before.st_mode):raise RuntimeError('runtime_source_link_or_nonregular_file')
    resolved=path.resolve(strict=True)
    try:resolved.relative_to(root)
    except ValueError:raise RuntimeError('runtime_source_path_escaped_AI_root') from None
    digest=hashlib.sha256()
    with resolved.open('rb') as stream:
        if _identity(os.fstat(stream.fileno()))!=_identity(before):raise RuntimeError('runtime_source_changed_during_snapshot')
        for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
        final=os.fstat(stream.fileno())
    if (_reparse(path) or path.resolve(strict=True)!=resolved or
            _identity(path.lstat())!=_identity(before) or _identity(final)!=_identity(before)):
        raise RuntimeError('runtime_source_changed_during_snapshot')
    return digest.hexdigest()


@dataclass(frozen=True)
class RuntimeSourceSnapshot:
    root:Path
    files:object

    def provenance(self):
        files=dict(self.files)
        serialized=json.dumps(files,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode('utf-8')
        return dict(version=VERSION,path_format='AI_root_relative_POSIX_paths',
            selected_directories=list(SOURCE_DIRECTORIES),selected_suffixes=sorted(SOURCE_SUFFIXES),
            excluded_directory_names=sorted(EXCLUDED_DIRECTORIES),file_count=len(files),
            source_set_sha256=hashlib.sha256(serialized).hexdigest(),files=files,
            training_hash_contract_modified=False,external_assets_included=False)


def capture_runtime_sources(ai_root=None):
    root=Path(ai_root) if ai_root is not None else Path(__file__).absolute().parents[1]
    if _reparse(root):raise RuntimeError('runtime_AI_root_link_not_supported')
    root=root.resolve(strict=True)
    if not root.is_dir():raise RuntimeError('runtime_AI_root_directory_required')
    files={}
    def inventory_error(error):raise RuntimeError('runtime_source_inventory_failed') from error
    for name in SOURCE_DIRECTORIES:
        folder=root/name
        if _reparse(folder) or not folder.is_dir():raise RuntimeError('runtime_source_directory_link_or_missing')
        for directory,children,filenames in os.walk(folder,topdown=True,followlinks=False,onerror=inventory_error):
            parent=Path(directory);kept=[]
            for child in sorted(children):
                if child.casefold() in EXCLUDED_DIRECTORIES:continue
                candidate=parent/child
                if _reparse(candidate):raise RuntimeError('runtime_source_directory_link_not_supported')
                kept.append(child)
            children[:]=kept
            for name in sorted(filenames):
                path=parent/name
                if path.suffix.lower() not in SOURCE_SUFFIXES:continue
                key=path.relative_to(root).as_posix()
                files[key]=_hash_source(path,root)
    if not files:raise RuntimeError('runtime_source_inventory_empty')
    return RuntimeSourceSnapshot(root,MappingProxyType(dict(sorted(files.items()))))


def assert_runtime_sources_unchanged(expected):
    if not isinstance(expected,RuntimeSourceSnapshot):raise TypeError('runtime_source_snapshot_required')
    actual=capture_runtime_sources(expected.root)
    if actual.files!=expected.files:
        before,after=set(expected.files),set(actual.files)
        changed=sorted(key for key in before&after if expected.files[key]!=actual.files[key])
        summary=dict(changed=changed[:10],added=sorted(after-before)[:10],deleted=sorted(before-after)[:10])
        raise RuntimeError('protection_runtime_source_set_changed:'+json.dumps(summary,sort_keys=True,separators=(',',':')))
    return expected.provenance()
