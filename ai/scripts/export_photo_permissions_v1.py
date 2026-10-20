"""Export one explicit PHOTO engine's verified arrays to experimental transport.

No inference fallback, bounding-box authorization, input conversion or re-render
is performed by the verifier. Diagnostic paths and biometric feature data stay
in private local artifacts; the wire response is an explicit allowlist.
"""
import hashlib,json,sys,time
from pathlib import Path
import numpy as np
from PIL import Image
import pad_refinement_tiles_v3 as tiles
from pad_refinement_data_contract_v2 import verify_source,read_source_rgb,read_body,read_mask,native_shape,digest
from photo_consumed_replay_v1 import development_replay as replay_scope
from photo_experimental_transport_v1 import (ENGINES,MAX_REQUEST_PNG_BYTES,decode_request_png,validate_native_result,require_request_id)
from protection_runtime_sources_v1 import capture_runtime_sources,assert_runtime_sources_unchanged
from protect_fingerprint import protect_image,validate_photo_options,cli_progress_to_stderr
from fingerprint_input_router import route_input


def _request_id(value):
    require_request_id(value)


def _request(path):
    path=Path(path)
    if path.is_symlink() or not path.is_file() or not 0<path.stat().st_size<=MAX_REQUEST_PNG_BYTES:
        raise ValueError('request_PNG_byte_limit')
    with path.open('rb') as stream:content=stream.read(MAX_REQUEST_PNG_BYTES+1)
    return decode_request_png(content),hashlib.sha256(content).hexdigest()


class ArtifactGuard:
    def __init__(self,root):self.root=Path(root).resolve();self.hashes={}
    def pin(self,path,*,external=False):
        path=Path(path)
        if not external:
            try:path.resolve().relative_to(self.root)
            except ValueError:raise ValueError('engine_artifact_escaped_fresh_output') from None
        sha=digest(path)
        if path in self.hashes and self.hashes[path]!=sha:raise ValueError('engine_artifact_changed')
        self.hashes[path]=sha;return sha
    def json(self,path):
        sha=self.pin(path);value,actual=tiles.json_snapshot(path)
        if actual!=sha:raise ValueError('engine_artifact_changed')
        return value,sha
    def unchanged(self):
        for path,expected in self.hashes.items():
            if digest(path)!=expected:raise ValueError('engine_artifact_changed')


def _same(actual,expected,reason):
    if tiles.hash_json(actual)!=tiles.hash_json(expected):raise ValueError(reason)


def reconstruct(engine_output,engine,source_rgb,source_sha,report,registry,development_replay,photo_model=None):
    """Reconstruct exact native labels from fresh, hash-bound engine inputs."""
    folder=Path(engine_output);guard=ArtifactGuard(folder)
    saved,_=guard.json(folder/'result.json');private_report,_=guard.json(folder/'result.private.json')
    _same(saved,report,'in_memory_and_saved_unified_result_mismatch')
    for key in ['regions','status','fingerprints_detected','fingerprints_transformed','fingerprints_rejected',
                'changed_pixels','returned_RGB_sha256','input_identity','single_photo_entrypoint','prediction_pixel_sha256','reject_reason']:
        _same(private_report.get(key),report.get(key),'private_unified_result_mismatch:'+key)
    if (report.get('schema_version')!='unified-fingerprint-v2' or report.get('photo_engine')!=engine or
            report.get('input_type')!='photo' or report.get('source_sha256')!=source_sha):
        raise ValueError('unified_selected_PHOTO_engine_binding_mismatch')
    manifest,manifest_sha=guard.json(folder/'private/dataset/manifest.input.private.json')
    if len(manifest.get('sources',[]))!=1 or manifest.get('GT_present') is not False or manifest.get('development_replay') is not development_replay:
        raise ValueError('fresh_single_GT_free_manifest_required')
    if tiles.hash_json(manifest.get('consumed_registry'))!=tiles.hash_json(registry):raise ValueError('export_registry_binding_mismatch')
    source=manifest['sources'][0]
    if source.get('source_id')!='INPUT':raise ValueError('single_INPUT_source_required')
    for key in ['source_path','body_path','tip_path','semantics_path','coarse_path']:guard.pin(source[key])
    verify_source(source,'inference');rgb=read_source_rgb(source['source_path'],source['source_sha256'])
    if not np.array_equal(rgb,source_rgb) or source['source_exif_orientation']!=1:raise ValueError('canonical_request_RGB_or_orientation_mismatch')
    with replay_scope(registry,[tiles.image_identity(source['source_path'])],enabled=development_replay):
        tiles.check_tiles(folder/'private/dataset',manifest,'inference')
    for crop in manifest['crops']:guard.pin(folder/'private/dataset'/crop['path'])
    shape=native_shape(source);body=read_body(source);tip=read_mask(source['tip_path'],source['tip_sha256'],shape)
    coarse=read_mask(source['coarse_path'],source['coarse_sha256'],shape)
    reason=None
    if engine=='pose_v14':
        import photo_pose_native_pipeline_v1 as pose
        worker,worker_sha=guard.json(folder/'private/hand-landmarks.private.json')
        if (report.get('hand_observation_file_sha256')!=worker_sha or
                report.get('hand_model_sha256')!=worker.get('model_sha256')):raise ValueError('pose_worker_file_binding_mismatch')
        pose.verify_worker(source,rgb,worker) # Invalid worker identity never authorizes an empty rejection.
        try:geometry=pose.geometry_from_worker(source,rgb,worker)
        except (ValueError,TypeError,KeyError) as error:
            reason=str(error)
            if (report.get('reject_reason')!=reason or report.get('regions')!=[] or report.get('pose_geometry_metadata') is not None):
                raise ValueError('pose_empty_permission_rejection_not_reproduced')
            permission=np.zeros(shape,bool);labels=np.zeros(shape,np.uint16)
        else:
            labels,_=pose.build_candidates(geometry);permission=geometry['proposed_labels']>0
            if report.get('pose_worker_record_sha256')!=tiles.hash_json(worker):raise ValueError('pose_worker_record_binding_mismatch')
            metadata,_=guard.json(folder/'private/pose-geometry/metadata.private.json')
            _same(metadata,dict(axes=geometry['axes'],metadata=geometry['metadata']),'pose_geometry_metadata_binding_mismatch')
            _same(report.get('pose_geometry_metadata'),geometry['metadata'],'pose_geometry_metadata_binding_mismatch')
            for key in ['owner_labels','proposed_labels','permission_labels','rejected_labels']:
                path=folder/'private/pose-geometry'/(key+'.png');guard.pin(path)
                with Image.open(path) as image:actual=np.asarray(image).copy()
                if not np.array_equal(actual,geometry[key]) or report.get('pose_label_sha256',{}).get(key)!=hashlib.sha256(geometry[key].tobytes()).hexdigest():
                    raise ValueError('pose_saved_geometry_binding_mismatch')
            _same(report.get('pose_axes'),geometry['axes'],'pose_axes_binding_mismatch')
    else:
        if engine=='native_v12':
            inference,_=guard.json(folder/'private/protection/predictions/inference.private.json')
            if inference.get('GT_used') is not False or inference.get('input_manifest_sha256')!=manifest_sha or len(inference.get('rows',[]))!=1:
                raise ValueError('prediction_manifest_binding_mismatch')
            row=inference['rows'][0];path=folder/'private/protection/predictions/INPUT.png';guard.pin(path)
            permission=read_mask(path,row['prediction_sha256'],shape)
            cfg_path=Path(photo_model)/'final_config.private.json';checkpoint=Path(photo_model)/'final_context_whole_pad.pt'
            guard.pin(cfg_path,external=True);model_sha=guard.pin(checkpoint,external=True)
            config,_=tiles.json_snapshot(cfg_path)
            if row.get('source_id')!='INPUT' or inference.get('model_sha256')!=model_sha or report.get('model_sha256')!=model_sha or config.get('model_sha256')!=model_sha:
                raise ValueError('prediction_model_binding_mismatch')
            if (row.get('source_sha256')!=source['source_sha256'] or row.get('native_shape')!=list(shape) or
                    type(row.get('body_exterior_pixels')) is not int or row['body_exterior_pixels']!=0):
                raise ValueError('prediction_source_geometry_binding_mismatch')
            from whole_pad_context_inputs_v6 import context_image,local_grid
            import infer_whole_pad_context_v6 as infer
            _,context=context_image(rgb,body)
            binding=inference.get('context_bindings',{}).get('INPUT')
            if not isinstance(binding,dict):raise ValueError('prediction_context_binding_mismatch')
            for key,expected in context.items():_same(binding.get(key),expected,'prediction_context_binding_mismatch')
            if (binding.get('source_id')!='INPUT' or binding.get('source_sha256')!=source['source_sha256'] or
                    binding.get('encoder_sha256')!=config.get('context_encoder_sha256') or
                    inference.get('context_encoder_sha256')!=config.get('context_encoder_sha256') or
                    inference.get('inference_code_sha256')!=digest(Path(infer.__file__)) or
                    inference.get('development_only') is not True or inference.get('independent_final_test') is not False or
                    inference.get('approved_for_protection') is not False):
                raise ValueError('prediction_context_binding_mismatch')
            grid_rows=[]
            for crop in manifest['crops']:
                grid,valid=local_grid(crop,context)
                grid_rows.append(dict(bbox=crop['bbox'],grid_sha256=hashlib.sha256(grid.tobytes()).hexdigest(),valid_sha256=hashlib.sha256(valid.tobytes()).hexdigest()))
            _same(binding.get('tiles'),grid_rows,'prediction_context_grid_binding_mismatch')
        elif engine=='distal_v13':permission=coarse
        else:raise ValueError('unsupported_experimental_engine')
        if np.any(permission&~body):raise ValueError('permission_outside_observed_BODY')
        from finger_body_distal_estimator import estimate
        from photo_candidate_context_v1 import candidate_contexts
        from photo_native_owner_context_v1 import restore_contexts
        from photo_component_local_evidence_v1 import connected_partition
        contexts=restore_contexts(candidate_contexts(estimate(body,tip,preserve_candidates=True),body),body)
        labels=connected_partition(permission,contexts)['labels']
    path=folder/'returned.png';guard.pin(path)
    with path.open('rb') as stream:returned=decode_request_png(stream.read(MAX_REQUEST_PNG_BYTES+1))
    guard.unchanged();verify_source(source,'inference')
    return returned,permission,labels,reason,guard


def run(source,output,*,photo_engine,consumed_registry,request_id,photo_model=None,development_replay=False,
        automatic_policy=None,execution_context=None):
    _request_id(request_id)
    if type(development_replay) is not bool:raise ValueError('development_replay_flag_must_be_boolean')
    if photo_engine not in ENGINES:raise ValueError('unsupported_experimental_engine')
    if photo_engine == 'synthetic_v23':
        from photo_automatic_v23 import run as automatic_run
        return automatic_run(source,output,photo_model=photo_model,consumed_registry=consumed_registry,
                             request_id=request_id,development_replay=development_replay,
                             automatic_policy=automatic_policy or 'surface_v26',
                             **(dict(execution_context=execution_context) if execution_context is not None else {}))
    if automatic_policy is not None:raise ValueError('automatic_policy_requires_synthetic_v23')
    validate_photo_options(photo_engine,photo_model,consumed_registry,development_replay)
    source,output,registry_path=Path(source),Path(output),Path(consumed_registry)
    if output.exists():raise FileExistsError('fresh_export_output_required')
    rgb,source_sha=_request(source)
    if route_input(rgb)['input_type']!='PHOTO':raise ValueError('experimental_PHOTO_input_required')
    registry,registry_sha=tiles.json_snapshot(registry_path);tiles.validate_registry(registry)
    if digest(registry_path)!=registry_sha:raise ValueError('export_configuration_changed')
    before=capture_runtime_sources();start=time.perf_counter()
    # These two files are included by the repository snapshot after integration;
    # explicit pins also protect a private, unintegrated review invocation.
    import photo_experimental_transport_v1 as transport
    code_paths=[Path(__file__),Path(transport.__file__)]
    code_pins={path:digest(path) for path in code_paths}
    external={registry_path:registry_sha}
    if photo_engine=='native_v12':
        for path in [Path(photo_model)/'final_config.private.json',Path(photo_model)/'final_context_whole_pad.pt']:external[path]=digest(path)
    output.mkdir(parents=True,exist_ok=False);engine_output=output/'engine'
    returned,report=protect_image(source,engine_output,photo_engine=photo_engine,photo_model=photo_model,
        consumed_registry=registry_path,development_replay=development_replay,detect_only=False)
    actual,permission,labels,empty_reason,guard=reconstruct(engine_output,photo_engine,rgb,source_sha,report,registry,development_replay,photo_model)
    if not np.array_equal(returned,actual):raise ValueError('unified_saved_actual_return_mismatch')
    verified=validate_native_result(rgb,actual,permission,labels,report,source_sha256=source_sha,engine=photo_engine,orientation=1,
        verified_empty_permission_reason=empty_reason)
    response=verified.response(request_id,int(round((time.perf_counter()-start)*1000)))
    if _request(source)[1]!=source_sha:raise ValueError('request_source_changed_during_export')
    for path,expected in external.items():
        if digest(path)!=expected:raise ValueError('export_configuration_changed')
    guard.unchanged();provenance=assert_runtime_sources_unchanged(before)
    target=output/'result.transport.json'
    with target.open('x',encoding='utf-8') as stream:json.dump(response,stream,separators=(',',':'),ensure_ascii=True,allow_nan=False)
    (output/'export.private.json').write_text(json.dumps(dict(runtime_source_snapshot=provenance,
        transport_sha256=digest(target),engine_artifact_count=len(guard.hashes),verified_empty_permission_reason=empty_reason),indent=2),encoding='utf-8')
    guard.unchanged();assert_runtime_sources_unchanged(before)
    if _request(source)[1]!=source_sha:raise ValueError('request_source_changed_during_export')
    for path,expected in external.items():
        if digest(path)!=expected:raise ValueError('export_configuration_changed')
    for path,expected in code_pins.items():
        if digest(path)!=expected:raise ValueError('export_bridge_code_changed')
    return target


def main(argv=None):
    from protect_fingerprint import JSONArgumentParser
    parser=JSONArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--photo-engine',choices=sorted(ENGINES),required=True);parser.add_argument('--photo-model',type=Path)
    parser.add_argument('--consumed-registry',type=Path,required=True);parser.add_argument('--request-id',required=True)
    parser.add_argument('--development-replay',action='store_true')
    parser.add_argument('--automatic-policy',choices=('surface_v26','strict_ridge_v23'))
    args=parser.parse_args(argv)
    try:
        with cli_progress_to_stderr():
            target=run(args.input,args.output,photo_engine=args.photo_engine,photo_model=args.photo_model,
                consumed_registry=args.consumed_registry,development_replay=args.development_replay,
                request_id=args.request_id,automatic_policy=args.automatic_policy)
    except Exception as error:
        print(type(error).__name__,file=sys.stderr);print(json.dumps(dict(status='error')));return 1
    print(json.dumps(dict(status='ok',transport_path=str(target.resolve()))));return 0


if __name__=='__main__':raise SystemExit(main())
