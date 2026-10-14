"""Unified fail-closed PHOTO/scanner public API. Optional runtimes stay external."""
import argparse,json,time,tempfile,contextlib,sys,os,subprocess
from pathlib import Path
import numpy as np
from PIL import Image
from sam_pad_detector import digest
from fingerprint_input_router import route_input
from scanner_fingerprint_detector import detect_scanner
from external_fingerphoto_detector import detect_photo,MediaPipeSAMRuntime,PhotoRuntimeUnavailable


@contextlib.contextmanager
def cli_progress_to_stderr():
    """CLI-only descriptor redirection also captures child Java stdout.

    Library callers are unaffected. The descriptor is restored on exceptions.
    """
    sys.stdout.flush();out_fd=sys.stdout.fileno();err_fd=sys.stderr.fileno();saved=os.dup(out_fd)
    try:
        os.dup2(err_fd,out_fd)
        with contextlib.redirect_stdout(sys.stderr):yield
    finally:
        sys.stderr.flush();os.dup2(saved,out_fd);os.close(saved)


def protect_fingerprint(source,output=None,photo_runtime=None,experimental_scanner=False,strength=.5,structure_guard=None,*,photo_semantics=None):
    if isinstance(strength,bool) or strength not in (0.,.5):raise ValueError('strength must be 0 or 0.5')
    source=Path(source);sha=digest(source)
    with Image.open(source) as im:
        if im.mode not in ['RGB','L']:raise ValueError('only 8-bit RGB/L inputs supported; no implicit alpha/dynamic-range loss')
        rgb=np.asarray(im.convert('RGB')).copy();orientation=im.getexif().get(274,1);mode=im.mode
    tick=time.perf_counter();route=route_input(rgb);regions=[];detail={};timing=dict(routing=time.perf_counter()-tick);tick=time.perf_counter()
    if route['input_type']=='PHOTO' and photo_runtime is None:
        from photo_quality_gate import evaluate
        try:
            returned,photo=evaluate(source,photo_semantics,detect_only=not experimental_scanner or strength==0)
        except (RuntimeError,ValueError,FileNotFoundError,subprocess.SubprocessError) as exc:
            returned=rgb.copy();photo=dict(status='rejected',fingerprints_detected=0,fingerprints_transformed=0,fingerprints_rejected=0,regions=[],reject_reason='photo_runtime_or_contract_failure',error=type(exc).__name__,PHOTO_DETECTOR_APPROVED=False,PHOTO_PROTECTION_PRODUCTION_READY=False)
        output=Path(tempfile.mkdtemp(prefix='blurfing_frontend_')) if output is None else Path(output)
        if output.exists() and any(output.iterdir()):raise FileExistsError('fresh output directory required')
        output.mkdir(parents=True,exist_ok=True);path=output/'returned.png';exif=Image.Exif();exif[274]=orientation;Image.fromarray(returned).save(path,exif=exif)
        mask=photo.pop('coarse_mask',np.zeros(rgb.shape[:2],bool))
        assert np.array_equal(returned[~mask],rgb[~mask]) and digest(source)==sha
        from scipy import ndimage
        labels,_=ndimage.label(mask)
        Image.fromarray(mask.astype(np.uint8)*255).save(output/'fingerprint_mask.png')
        for region in photo['regions']:
            name=f"region_{region['region_id']:03d}_mask.png";Image.fromarray((labels==region['region_id']).astype(np.uint8)*255).save(output/name);region.update(mask_path=name,mask_sha256=digest(output/name))
        result=photo|dict(schema_version='unified-fingerprint-v2',input_type='photo',source_sha256=sha,image_width=rgb.shape[1],image_height=rgb.shape[0],source_exif_orientation=orientation,coordinate_system='encoded_original_pixels',output_path=str(path),route=route,exterior_preserved=True,independent_validation_complete=False)
        (output/'result.json').write_text(json.dumps(result,indent=2));return returned,result
    if route['input_type']=='PHOTO':
        try:regions,detail=detect_photo(rgb,sha,orientation,photo_runtime)
        except (RuntimeError,ValueError) as e:regions=[];detail=dict(status='blocked',reject_reason='photo_runtime_or_geometry_failure',error=type(e).__name__)
        if photo_runtime is not None and not regions:
            from legacy_detector import detect_legacy
            legacy=detect_legacy(rgb);detail['legacy_fallback']=dict(proposals=legacy['proposal_count'],review_regions=len(legacy['regions']),approved_for_use=False)
    elif route['input_type']=='FINGERPRINT_IMAGE':regions,detail=detect_scanner(rgb,sha)
    else:detail=dict(status='rejected',reject_reason=route['reason'])
    timing['detection']=time.perf_counter()-tick;returned=rgb.copy();transform=dict(applied=False,reason='detector_development_gate_not_passed');transformed=0
    if regions and route['input_type']=='FINGERPRINT_IMAGE' and experimental_scanner:
        if structure_guard is None:transform=dict(applied=False,reason='scanner_structure_guard_required')
        else:
            from scanner_renderer_experimental import render_scanner
            tick=time.perf_counter()
            try:candidate,transform=render_scanner(rgb,regions[0],strength)
            except Exception as e:candidate=rgb.copy();transform=dict(applied=False,reason='scanner_renderer_failure_original_returned',error=type(e).__name__)
            timing['transform']=time.perf_counter()-tick
            if transform['applied']:
                try:guard=structure_guard(rgb,candidate)
                except Exception as e:guard=dict(structure_change_passed=False,reason='structure_runtime_failure',error=type(e).__name__)
                transform['structure_check']=guard
                if guard.get('structure_change_passed'):returned=candidate;transformed=1
                else:transform.update(applied=False,reason='structure_check_failed_original_returned')
    # PHOTO remains gated until real GT7 validation succeeds; legacy is not auto-primary.
    union=np.logical_or.reduce([r.binary_mask>0 for r in regions]) if regions else np.zeros(rgb.shape[:2],bool);assert np.array_equal(returned[~union],rgb[~union]);assert digest(source)==sha
    output=Path(tempfile.mkdtemp(prefix='blurfing_frontend_')) if output is None else Path(output)
    if output.exists() and any(output.iterdir()):raise FileExistsError('fresh output directory required')
    output.mkdir(parents=True,exist_ok=True);path=output/'returned.png';image=Image.fromarray(returned[:,:,0] if mode=='L' else returned);exif=Image.Exif();exif[274]=orientation;image.save(path,exif=exif)
    for i,r in enumerate(regions):Image.fromarray(r.binary_mask).save(output/f'region_{i:03d}_mask.png');Image.fromarray(r.normalized_roi).save(output/f'region_{i:03d}_normalized.png')
    result=dict(schema_version='unified-fingerprint-v2',input_type=route['input_type'].lower(),source_sha256=sha,image_width=rgb.shape[1],image_height=rgb.shape[0],coordinate_system='encoded_original_pixels',source_exif_orientation=orientation,fingerprints_detected=len(regions),fingerprints_transformed=transformed,status='applied_experimental' if transformed else 'blocked' if detail.get('status')=='blocked' else 'unchanged',output_path=str(path),route=route,detection=detail,regions=[r.metadata()|dict(mask_path=f'region_{i:03d}_mask.png',mask_sha256=digest(output/f'region_{i:03d}_mask.png'),normalized_roi_path=f'region_{i:03d}_normalized.png') for i,r in enumerate(regions)],transform=transform,exterior_preserved=True,timing=timing,independent_validation_complete=False)
    result['fingerprints_rejected']=len(regions)-transformed;result['legacy_status']=result['status'];result['status']='success' if transformed and transformed==len(regions) else 'partial_success' if transformed else 'rejected'
    (output/'result.json').write_text(json.dumps(result,indent=2));return returned,result

def protect_image(source,output=None,*,detect_only=False,strength=.5,photo_semantics=None):
    """Complete routed API; legacy protect_fingerprint signature remains available."""
    guard=None
    if not detect_only:
        from scanner_structure_guard import scanner_structure_guard
        guard=scanner_structure_guard
    return protect_fingerprint(source,output,experimental_scanner=not detect_only,strength=strength,structure_guard=guard,photo_semantics=photo_semantics)

class JSONArgumentParser(argparse.ArgumentParser):
    def error(self,message):
        self.print_usage(sys.stderr);print(json.dumps(dict(status='error',error='invalid_arguments')));raise SystemExit(2)

if __name__=='__main__':
    p=JSONArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path);p.add_argument('--photo-semantics',type=Path);p.add_argument('--hand-model',type=Path);p.add_argument('--sam-checkpoint',type=Path);p.add_argument('--experimental-scanner-transform',action='store_true',help='compatibility alias: scanner transform is attempted by default');p.add_argument('--detect-only',action='store_true');p.add_argument('--strength',type=float,default=.5);a=p.parse_args();runtime=None
    runtime_error=None
    if bool(a.hand_model)!=bool(a.sam_checkpoint):p.error('both hand and SAM model paths are required')
    if a.hand_model and a.sam_checkpoint:
        try:
            with cli_progress_to_stderr():runtime=MediaPipeSAMRuntime(a.hand_model,a.sam_checkpoint)
        except PhotoRuntimeUnavailable as e:runtime_error=str(e)
    try:
        guard=None
        if not a.detect_only:
            from scanner_structure_guard import scanner_structure_guard
            guard=scanner_structure_guard
        with cli_progress_to_stderr():_,r=protect_fingerprint(a.input,a.output,runtime,not a.detect_only,a.strength,guard,photo_semantics=a.photo_semantics)
        if runtime_error:r.setdefault('detection',{})['runtime_setup_error']=runtime_error
        print(json.dumps(r,indent=2))
    except Exception as exc:
        print(json.dumps(dict(status='error',error=type(exc).__name__)));sys.exit(1)
    finally:
        if runtime is not None:runtime.close()
