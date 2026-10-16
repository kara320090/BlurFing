"""Rounded detection permissions followed by the existing fingerprint renderer.

This is an opt-in development path. A black detection preview never becomes
the protection result. Rejected components keep original source RGB.
"""
import io,json
from pathlib import Path
import numpy as np
from PIL import Image, ImageOps, ImageDraw, ImageCms
import pad_refinement_tiles_v3 as tiles
from pad_refinement_data_contract_v2 import digest, read_mask, native_shape, read_body
from photo_source_rgb_v1 import canonical_rgb
from photo_pose_native_pipeline_v1 import geometry_from_worker
from photo_rounded_pad_v1 import rounded_pads
from photo_rounded_native_pipeline_v1 import evaluate, VERSION
from photo_learned_pad_pipeline_v1 import pixel_hash
from final_png_color_metadata_v1 import save_final_rgb_png, _source_metadata
from protection_runtime_sources_v1 import capture_runtime_sources, assert_runtime_sources_unchanged
from photo_consumed_replay_v1 import development_replay as replay_scope


def save_artifacts(source, identity, rgb, mask, returned, accepted, output):
    """Display actual returned RGB and actual change, with original metadata."""
    orientation=identity['source_exif_orientation'];sha=identity['original_source_sha256']
    if not np.array_equal(returned[~accepted],rgb[~accepted]) or np.any(accepted & ~mask):
        raise ValueError('rounded_native_artifact_permission_contract')
    save_final_rgb_png(source,sha,rgb,output/'original.png',orientation)
    save_final_rgb_png(source,sha,returned,output/'protected.png',orientation)
    changed=np.any(returned!=rgb,axis=2)
    exif=Image.Exif();exif[274]=orientation
    for name,a in dict(permission_mask=mask,accepted_mask=accepted,rejected_mask=mask & ~accepted,changed_mask=changed).items():
        with (output/(name+'.png')).open('xb') as stream:Image.fromarray(a.astype(np.uint8)*255).save(stream,format='PNG',exif=exif)
    canvas=Image.new('RGB',(1440,410),'#eeeeee');draw=ImageDraw.Draw(canvas)
    _,_,_,icc=_source_metadata(source,sha)
    for i,(label,a) in enumerate([('Original',rgb),('Rounded permission (not applied)',mask),('Actually changed pixels',changed),('Returned fingerprint transform',returned)]):
        image=Image.fromarray(a if a.ndim==3 else a.astype(np.uint8)*255);image.info['exif']=exif.tobytes()
        image=ImageOps.exif_transpose(image);image.thumbnail((350,350))
        if a.ndim==3 and icc is not None:
            image=ImageCms.profileToProfile(image,ImageCms.ImageCmsProfile(io.BytesIO(icc)),ImageCms.createProfile('sRGB'),outputMode='RGB')
        canvas.paste(image,(i*360+(360-image.width)//2,28));draw.text((i*360+5,8),label,fill='black')
    draw.text((6,389),'Actual returned RGB. Rejected regions remain original. Structure change is not a privacy proof.',fill='#880000')
    with (output/'comparison.png').open('xb') as stream:canvas.save(stream,format='PNG')


def protect_detection(source, detection, registry_path, output, *, development_replay=False, detect_only=False, crease_boundary=False):
    if type(development_replay) is not bool or type(detect_only) is not bool or type(crease_boundary) is not bool:
        raise ValueError('rounded_native_flags_must_be_boolean')
    if Path(output).exists() or Path(output).is_symlink():raise FileExistsError('fresh_output_required')
    registry,_=tiles.json_snapshot(Path(registry_path));tiles.validate_registry(registry)
    original=tiles.image_identity(Path(source))
    if not development_replay:tiles.exclude_consumed(original,registry)
    manifest,_=tiles.json_snapshot(Path(detection)/'private/dataset/manifest.input.private.json')
    if len(manifest['sources'])!=1:raise ValueError('single_rounded_source_required')
    canonical=tiles.image_identity(Path(manifest['sources'][0]['source_path']))
    # Tile preflight also checks the canonical PNG. Keep its explicit replay
    # scope alive through both preflight and final verification; strict calls
    # retain the original consumed-source barrier.
    with replay_scope(registry,[original,canonical],enabled=development_replay):
        return _protect_detection(source,detection,registry_path,output,
            development_replay=development_replay,detect_only=detect_only,crease_boundary=crease_boundary)


def _protect_detection(source, detection, registry_path, output, *, development_replay=False, detect_only=False, crease_boundary=False):
    if type(development_replay) is not bool or type(detect_only) is not bool or type(crease_boundary) is not bool:
        raise ValueError('rounded_native_flags_must_be_boolean')
    source,detection,registry_path,output=map(Path,(source,detection,registry_path,output))
    if output.exists() or output.is_symlink():raise FileExistsError('fresh_output_required')
    snapshot=capture_runtime_sources()
    registry,registry_sha=tiles.json_snapshot(registry_path);tiles.validate_registry(registry)
    original_identity=tiles.image_identity(source)
    if not development_replay:tiles.exclude_consumed(original_identity,registry)
    rgb,identity=canonical_rgb(source)
    detection_report,report_sha=tiles.json_snapshot(detection/'result.private.json')
    if (detection_report.get('input_type')!='PHOTO' or detection_report.get('rounded_pad_metadata') is None or
            detection_report.get('input_identity')!=identity or detection_report.get('input_RGB_sha256')!=pixel_hash(rgb)):
        raise ValueError('rounded_native_detection_source_binding_mismatch')
    dataset=detection/'private/dataset'
    manifest,manifest_sha=tiles.json_snapshot(dataset/'manifest.input.private.json')
    if len(manifest['sources'])!=1:raise ValueError('single_rounded_source_required')
    tiles.check_tiles(dataset,manifest,'inference');record=manifest['sources'][0]
    if record['source_RGB_sha256']!=pixel_hash(rgb) or record['source_exif_orientation']!=identity['source_exif_orientation']:
        raise ValueError('rounded_native_manifest_RGB_binding_mismatch')
    shape=native_shape(record);body=read_body(record)
    tip=read_mask(record['tip_path'],record['tip_sha256'],shape)
    paths=[detection/n for n in ['refined_mask.png','before_rounding_mask.png','candidate_mask.png']]
    pins={p:digest(p) for p in paths}
    mask,before,coarse=[read_mask(p,pins[p],shape) for p in paths]
    if pixel_hash(mask)!=detection_report['mask_pixel_sha256']:
        raise ValueError('rounded_native_detection_mask_binding_mismatch')
    worker=detection/'private/hand.private.json';worker_sha=None;pose=None;hand_record=None
    if worker.exists():
        hand_record,worker_sha=tiles.json_snapshot(worker)
        if hand_record.get('hand_count')==1:pose=geometry_from_worker(record,rgb,hand_record)
        else:
            from photo_pose_native_pipeline_v1 import verify_worker
            verify_worker(record,rgb,hand_record)
    recomputed,rounding=rounded_pads(before,coarse,body,tip,pose_geometry=pose)
    if not np.array_equal(recomputed,mask) or rounding!=detection_report['rounded_pad_metadata']:
        raise ValueError('rounded_native_geometry_replay_mismatch')
    output.mkdir(parents=True,exist_ok=False)
    if crease_boundary:
        from photo_crease_native_adapter_v1 import prepare
        record,mask,rounding,pose=prepare(record,rgb,before,rounding,hand_record,output/'private/crease_boundary')
    returned,report,accepted,labels=evaluate(record,mask,pixel_hash(mask),rounding,pose_geometry=pose,detect_only=detect_only)
    if pixel_hash(returned)!=report['returned_RGB_sha256']:
        raise ValueError('rounded_native_return_RGB_hash_mismatch')
    color=save_final_rgb_png(source,identity['original_source_sha256'],returned,output/'returned.png',identity['source_exif_orientation'])
    save_artifacts(source,identity,rgb,mask,returned,accepted,output)
    with (output/'region_labels.png').open('xb') as stream:Image.fromarray(labels).save(stream,format='PNG')
    if not detect_only:
        from photo_rejection_resolution_v1 import save_resolution_artifacts
        resolution=save_resolution_artifacts(source,identity,rgb,returned,mask,accepted,labels,report,output)
        report['rejection_resolution']=resolution
    tiles.check_tiles(dataset,manifest,'inference');tiles.unchanged(dataset/'manifest.input.private.json',manifest_sha)
    tiles.unchanged(detection/'result.private.json',report_sha);tiles.unchanged(registry_path,registry_sha)
    for p,sha in pins.items():tiles.unchanged(p,sha)
    if worker_sha is not None:tiles.unchanged(worker,worker_sha)
    tiles.unchanged(source,identity['original_source_sha256'])
    report.update(**color,input_identity=identity,version=VERSION,input_type='PHOTO',
        method='natural_auto_04_boundaryblend_02_with_V12_actual_native_gate',
        detection_path=str(detection.resolve()),detection_report_sha256=report_sha,
        model_sha256=detection_report['model_sha256'],rounded_pad_metadata=rounding,
        original_source_sha256=identity['original_source_sha256'],GT_used=False,detect_only=detect_only,
        crease_boundary=crease_boundary,mask_scope=('RGB_silhouette_to_observed_crease_experimental' if crease_boundary else 'rounded_cap_experimental'),
        development_replay=development_replay,independent_final_test=False,
        output_path=str((output/'returned.png').resolve()),protected_path=str((output/'protected.png').resolve()),
        comparison_path=str((output/'comparison.png').resolve()),
        runtime_source_snapshot=assert_runtime_sources_unchanged(snapshot),runtime_source_snapshot_verified=True)
    (output/'result.private.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return returned,report


def run(source,model,registry_path,output,*,development_replay=False,photo_semantics=None,detect_only=False,crease_boundary=False):
    if type(development_replay) is not bool or type(detect_only) is not bool or type(crease_boundary) is not bool:
        raise ValueError('rounded_native_flags_must_be_boolean')
    output=Path(output)
    if output.exists() or output.is_symlink():raise FileExistsError('fresh_output_required')
    from protect_photo_pitch_free_v1 import run as detect
    detection=output/'detection_preview'
    detect(source,model,registry_path,detection,photo_semantics=photo_semantics,
        development_replay=development_replay,include_observed_pose=True,
        include_coarse_pad=True,complete_holes=True,rounded_pads=True)
    return protect_detection(source,detection,registry_path,output/'protection',
        development_replay=development_replay,detect_only=detect_only,crease_boundary=crease_boundary)


if __name__=='__main__':
    from protect_fingerprint import JSONArgumentParser,cli_progress_to_stderr
    parser=JSONArgumentParser(description=__doc__)
    for name in ['input','model','consumed-registry','output']:parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--development-replay',action='store_true');parser.add_argument('--detect-only',action='store_true')
    parser.add_argument('--crease-boundary',action='store_true',help='Opt-in RGB silhouette and observed transverse crease boundary; requires visual review.')
    args=parser.parse_args()
    try:
        with cli_progress_to_stderr():_,report=run(args.input,args.model,args.consumed_registry,args.output,
            development_replay=args.development_replay,detect_only=args.detect_only,crease_boundary=args.crease_boundary)
        print(json.dumps(report,indent=2))
    except Exception as error:
        print(json.dumps(dict(status='error',reason=str(error),error=type(error).__name__)));raise SystemExit(1)
