"""Read-only runtime inventory; stdout is JSON, never claims inference validation."""
import json,os,hashlib,shutil,sys
from pathlib import Path

def check():
    report=dict(check_scope='read-only file/hash/prerequisite inventory; no execution-equivalence claim',javac_available=bool(shutil.which('javac')),python=sys.version.split()[0],java_available=bool(shutil.which('java')),PHOTO_DETECTOR_APPROVED=False,PHOTO_PROTECTION_PRODUCTION_READY=False)
    for name,kind in [('nbis','nbis'),('sourceafis','sourceafis')]:
        try:
            from platform_loader import load_adapter
            adapter=load_adapter(kind)
            if name=='nbis':adapter.inspect_runtime(os.environ.get('BLURFING_NBIS_CONFIG') or os.environ.get('BLURFING_NBIS_LINUX_CONFIG'))
            else:adapter._runtime()
            report[name]='available'
        except Exception as exc:report[name]='unavailable:'+type(exc).__name__
    values=[os.environ.get(k) for k in ['BLURFING_COLFISPOOF_PYTHON','BLURFING_COLFISPOOF_SOURCE','BLURFING_COLFISPOOF_MODEL']]
    report['photo_runtime_configured']=all(values)
    report['photo_runtime_paths_exist']=bool(all(values) and all(Path(v).exists() for v in values))
    report['COLFISPOOF_model_hash_ok']=bool(values[2] and Path(values[2]).is_file() and hashlib.sha256(Path(values[2]).read_bytes()).hexdigest()=='f58d510ac9e83c4b5398f580446aef6028890993da052cacab048f434888b60f')
    return report
if __name__=='__main__':print(json.dumps(check()))
