"""Synthetic file/binding checks; no detector, renderer, training or biometric scores."""
import contextlib,copy,hashlib,io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
import export_photo_permissions_v1 as export
import pad_refinement_tiles_v3 as tiles
from pad_refinement_data_contract_v2 import digest,COORDINATES,read_mask
from photo_experimental_transport_v1 import ENTRYPOINTS,sha,validate_native_result


def write_json(path,value):
    path.write_text(json.dumps(value,indent=2),encoding='utf-8')


class ExportFixture(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.registry=[dict(source_sha256=f'{i:064x}',encoded_RGB_sha256=f'{i+100:064x}',
            upright_RGB_sha256=f'{i+200:064x}',role='consumed_GT7' if i<8 else 'consumed_holdout') for i in range(1,16)]
        self.registry_path=self.root/'registry.private.json';write_json(self.registry_path,self.registry)
        self.rgb=np.zeros((80,60,3),np.uint8);self.rgb[:]=[180,120,100]
        self.source=self.root/'request.png';Image.fromarray(self.rgb).save(self.source)
        self.source_sha=digest(self.source);self.output=self.root/'export'
        self.model=self.root/'model';self.model.mkdir();(self.model/'final_context_whole_pad.pt').write_bytes(b'synthetic-hash-only-no-model-load')
        write_json(self.model/'final_config.private.json',dict(model_sha256=digest(self.model/'final_context_whole_pad.pt'),context_encoder_sha256='d'*64))

    def fresh_engine(self,folder,engine='distal_v13'):
        """Produce genuine synthetic tile/semantics artifacts, all local to fresh output."""
        folder=Path(folder);private=folder/'private';private.mkdir(parents=True)
        canonical=private/'canonical_input.png';canonical.write_bytes(self.source.read_bytes())
        semantics=private/'semantics';semantics.mkdir()
        body=np.zeros(self.rgb.shape[:2],np.uint8);body[5:75,20:40]=255
        tip=np.zeros_like(body);tip[5:15,20:40]=255
        Image.fromarray(body).save(semantics/'body.png');Image.fromarray(tip).save(semantics/'tip.png')
        write_json(semantics/'semantics.json',dict(source_sha256=digest(canonical),body_sha256=digest(semantics/'body.png'),
            tip_sha256=digest(semantics/'tip.png'),coordinate_system=COORDINATES,body_classes=[1,2],tip_class=2,
            minimum_votes=2,image_height=80,image_width=60))
        data=tiles.prepare([dict(source_id='INPUT',source_path=str(canonical.resolve()),source_sha256=digest(canonical),
            semantics=str(semantics.resolve()),acquisition_group='synthetic',group_provenance='generated_test_only')],
            self.registry,private/'dataset',purpose='inference')
        data['development_replay']=False;manifest_path=private/'dataset/manifest.input.private.json';write_json(manifest_path,data)
        source=data['sources'][0];permission=read_mask(source['coarse_path'],source['coarse_sha256'],self.rgb.shape[:2])
        from finger_body_distal_estimator import estimate
        from photo_candidate_context_v1 import candidate_contexts
        from photo_native_owner_context_v1 import restore_contexts
        from photo_component_local_evidence_v1 import connected_partition
        contexts=restore_contexts(candidate_contexts(estimate(body>0,tip>0,preserve_candidates=True),body>0),body>0)
        labels=connected_partition(permission,contexts)['labels']
        model_sha=digest(self.model/'final_context_whole_pad.pt')
        if engine=='native_v12':
            from whole_pad_context_inputs_v6 import context_image,local_grid
            import infer_whole_pad_context_v6 as infer
            _,info=context_image(self.rgb,body>0)
            info.update(source_id='INPUT',source_sha256=source['source_sha256'],encoder_sha256='d'*64,feature_sha256='e'*64,tiles=[])
            for crop in data['crops']:
                grid,valid=local_grid(crop,info)
                info['tiles'].append(dict(bbox=crop['bbox'],grid_sha256=sha(grid),valid_sha256=sha(valid)))
            pred=private/'protection/predictions';pred.mkdir(parents=True)
            Image.fromarray(permission.astype(np.uint8)*255).save(pred/'INPUT.png')
            write_json(pred/'inference.private.json',dict(GT_used=False,input_manifest_sha256=digest(manifest_path),
                model_sha256=model_sha,context_encoder_sha256='d'*64,context_bindings=dict(INPUT=info),
                inference_code_sha256=digest(Path(infer.__file__)),development_only=True,independent_final_test=False,approved_for_protection=False,
                rows=[dict(source_id='INPUT',source_sha256=source['source_sha256'],
                prediction_sha256=digest(pred/'INPUT.png'),native_shape=[80,60],body_exterior_pixels=0)]))
        if engine=='pose_v14':
            import mediapipe_hand_worker_v1 as hand
            worker=dict(version=hand.VERSION,source_sha256=source['source_sha256'],encoded_RGB_sha256=sha(self.rgb),
                upright_RGB_sha256=sha(self.rgb),encoded_shape=list(self.rgb.shape),upright_shape=list(self.rgb.shape),
                source_exif_orientation=1,model_sha256=hand.MODEL_SHA256,worker_code_sha256=digest(Path(hand.__file__)),
                configuration=hand.CONFIGURATION,GT_used=False,runtime=dict(mediapipe_version=hand.MEDIAPIPE_VERSION),
                hand_count=0,hands=[],status='no_hand_observed')
            write_json(private/'hand-landmarks.private.json',worker)
            permission=np.zeros(self.rgb.shape[:2],bool);labels=np.zeros(self.rgb.shape[:2],np.uint16)
        rows=[]
        for region in sorted(int(v) for v in np.unique(labels) if v):
            mask=labels==region;rows.append(dict(region_id=region,status='rejected',quality_status='REJECT_OTHER',
                mask_pixel_sha256=sha(mask),mask_pixels=int(mask.sum())))
        report=dict(single_photo_entrypoint=ENTRYPOINTS[engine],status='rejected',regions=rows,
            fingerprints_detected=len(rows),fingerprints_transformed=0,fingerprints_rejected=len(rows),changed_pixels=0,
            input_identity=dict(original_source_sha256=self.source_sha,canonical_RGB_sha256=sha(self.rgb),source_exif_orientation=1),
            coordinate_system=COORDINATES,prediction_pixel_sha256=sha(permission),returned_RGB_sha256=sha(self.rgb),
            approved_for_protection=False,privacy_validated=False,source_sha256=source['source_sha256'])
        if engine=='native_v12':report['model_sha256']=model_sha
        if engine=='pose_v14':
            del report['prediction_pixel_sha256']
            report.update(reject_reason='pose_exactly_one_observed_hand_required',
                hand_observation_file_sha256=digest(private/'hand-landmarks.private.json'),hand_model_sha256=hand.MODEL_SHA256)
        write_json(folder/'result.private.json',report)
        report=report|dict(schema_version='unified-fingerprint-v2',photo_engine=engine,input_type='photo',source_sha256=self.source_sha)
        write_json(folder/'result.json',report);Image.fromarray(self.rgb).save(folder/'returned.png')
        return self.rgb.copy(),report,data,permission,labels

    def reconstruct(self,engine,report):
        return export.reconstruct(self.output,engine,self.rgb,self.source_sha,report,self.registry,False,
            self.model if engine=='native_v12' else None)


class ExportTests(ExportFixture):
    def test_export_request_id_rejected_before_source_or_unified_execution(self):
        for value in ['550e8400-e29b-41d4-a716-446655440000','photo:case_1.v2','A'*200,'0']:export._request_id(value)
        with patch.object(export,'protect_image') as invoke:
            for value in ['',None,True,123,'A'*201,'photo test','test\n','test\r','test\t','test\0','test/path','test\\path','한글','é','Ａ','_start',':start']:
                with self.subTest(invalid=value),self.assertRaisesRegex(ValueError,'invalid_request_id'):
                    export.run(self.root/'missing.png',self.output,photo_engine='distal_v13',consumed_registry=self.registry_path,request_id=value)
        invoke.assert_not_called();self.assertFalse(self.output.exists())

    def test_fresh_distal_exact_partition_and_original_rejection(self):
        _,report,_,permission,labels=self.fresh_engine(self.output)
        self.assertTrue(permission.any());returned,p,l,reason,_=self.reconstruct('distal_v13',report)
        np.testing.assert_array_equal(returned,self.rgb);np.testing.assert_array_equal(p,permission);np.testing.assert_array_equal(l,labels)
        self.assertIsNone(reason)
        wire=validate_native_result(self.rgb,returned,p,l,report,source_sha256=self.source_sha,engine='distal_v13',orientation=1).response('synthetic',0)
        self.assertEqual(wire['status'],'rejected');self.assertEqual(wire['accepted_permission_mask']['pixels'],0)

    def test_manifest_external_source_cannot_substitute_same_RGB(self):
        _,report,data,_,_=self.fresh_engine(self.output)
        data['sources'][0]['source_path']=str(self.source)
        write_json(self.output/'private/dataset/manifest.input.private.json',data)
        with self.assertRaisesRegex(ValueError,'escaped_fresh'):self.reconstruct('distal_v13',report)

    def test_tampered_semantic_mask_is_not_authorized_by_report(self):
        _,report,data,_,_=self.fresh_engine(self.output)
        path=Path(data['sources'][0]['body_path']);mask=np.asarray(Image.open(path)).copy();mask[0,0]=255;Image.fromarray(mask).save(path)
        with self.assertRaisesRegex(ValueError,'hash_mismatch'):self.reconstruct('distal_v13',report)

    def test_tampered_saved_unified_report_is_rejected(self):
        _,report,_,_,_=self.fresh_engine(self.output)
        saved=copy.deepcopy(report);saved['changed_pixels']=1;write_json(self.output/'result.json',saved)
        with self.assertRaisesRegex(ValueError,'in_memory_and_saved'):self.reconstruct('distal_v13',report)

    def test_native_model_source_row_and_mask_are_bound_without_loading_model(self):
        _,report,_,permission,labels=self.fresh_engine(self.output,'native_v12')
        _,p,l,_,_=self.reconstruct('native_v12',report)
        np.testing.assert_array_equal(p,permission);np.testing.assert_array_equal(l,labels)
        path=self.output/'private/protection/predictions/inference.private.json';data=json.loads(path.read_text())
        data['rows'][0]['source_sha256']='b'*64;write_json(path,data)
        with self.assertRaisesRegex(ValueError,'source_geometry_binding'):self.reconstruct('native_v12',report)

    def test_prediction_model_hash_mismatch_fails_before_transport(self):
        _,report,_,_,_=self.fresh_engine(self.output,'native_v12')
        (self.model/'final_context_whole_pad.pt').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'model_binding'):self.reconstruct('native_v12',report)

    def test_context_source_geometry_grid_is_reconstructed_without_features(self):
        _,report,_,_,_=self.fresh_engine(self.output,'native_v12')
        path=self.output/'private/protection/predictions/inference.private.json';data=json.loads(path.read_text())
        data['context_bindings']['INPUT']['tiles'][0]['grid_sha256']='b'*64;write_json(path,data)
        with self.assertRaisesRegex(ValueError,'context_grid_binding'):self.reconstruct('native_v12',report)

    def test_valid_pose_saved_geometry_is_exact_and_tamper_cannot_relabel(self):
        import photo_pose_native_pipeline_v1 as pose
        _,report,data,_,_=self.fresh_engine(self.output,'pose_v14');path=self.output/'private/hand-landmarks.private.json'
        worker=json.loads(path.read_text());points=np.tile([30.5/60,50.5/80],(21,1))
        for joint,tip,x in [(3,4,22),(7,8,26),(11,12,30),(15,16,34),(19,20,38)]:
            points[joint]=[(x+.5)/60,25.5/80];points[tip]=[(x+.5)/60,8.5/80]
        worker.update(hand_count=1,hands=[dict(normalized_xy=points.tolist())],status='observed');write_json(path,worker)
        geometry=pose.geometry_from_worker(data['sources'][0],self.rgb,worker);labels,_=pose.build_candidates(geometry)
        directory=self.output/'private/pose-geometry';directory.mkdir()
        for key in ['owner_labels','proposed_labels','permission_labels','rejected_labels']:Image.fromarray(geometry[key]).save(directory/(key+'.png'))
        write_json(directory/'metadata.private.json',dict(axes=geometry['axes'],metadata=geometry['metadata']))
        rows=[]
        for region in sorted(int(v) for v in np.unique(labels) if v):
            mask=labels==region;rows.append(dict(region_id=region,status='rejected',quality_status='REJECT_OTHER',mask_pixel_sha256=sha(mask),mask_pixels=int(mask.sum())))
        report.pop('reject_reason');report.update(regions=rows,fingerprints_detected=len(rows),fingerprints_rejected=len(rows),
            prediction_pixel_sha256=sha(geometry['proposed_labels']>0),hand_observation_file_sha256=digest(path),
            pose_worker_record_sha256=tiles.hash_json(worker),pose_axes=geometry['axes'],pose_geometry_metadata=geometry['metadata'],
            pose_label_sha256={key:sha(geometry[key]) for key in ['owner_labels','proposed_labels','permission_labels','rejected_labels']})
        for filename in ['result.json','result.private.json']:
            saved=json.loads((self.output/filename).read_text());saved.pop('reject_reason');saved.update(report);write_json(self.output/filename,saved)
        _,p,l,reason,_=self.reconstruct('pose_v14',report)
        np.testing.assert_array_equal(l,labels);np.testing.assert_array_equal(p,geometry['proposed_labels']>0);self.assertIsNone(reason)
        damaged=geometry['permission_labels'].copy();damaged[8,22]=0;Image.fromarray(damaged).save(directory/'permission_labels.png')
        with self.assertRaisesRegex(ValueError,'saved_geometry_binding'):self.reconstruct('pose_v14',report)

    def test_nohand_requires_real_worker_binding_then_reproduced_empty_reason(self):
        _,report,_,_,_=self.fresh_engine(self.output,'pose_v14');before=copy.deepcopy(report)
        returned,p,l,reason,_=self.reconstruct('pose_v14',report)
        self.assertFalse(p.any());self.assertFalse(l.any());self.assertEqual(report,before)
        wire=validate_native_result(self.rgb,returned,p,l,report,source_sha256=self.source_sha,engine='pose_v14',orientation=1,
            verified_empty_permission_reason=reason).response('synthetic-nohand',0)
        self.assertEqual(wire['status'],'rejected');self.assertEqual(wire['candidate_components'],0)
        path=self.output/'private/hand-landmarks.private.json';worker=json.loads(path.read_text());worker['encoded_RGB_sha256']='b'*64;write_json(path,worker)
        report['hand_observation_file_sha256']=digest(path)
        for file in ['result.json','result.private.json']:
            data=json.loads((self.output/file).read_text());data['hand_observation_file_sha256']=digest(path);write_json(self.output/file,data)
        with self.assertRaisesRegex(ValueError,'pose_worker_binding_mismatch'):self.reconstruct('pose_v14',report)

    def test_nohand_reason_mismatch_is_not_silently_accepted(self):
        _,report,_,_,_=self.fresh_engine(self.output,'pose_v14');report['reject_reason']='some_other_failure'
        for file in ['result.json','result.private.json']:
            data=json.loads((self.output/file).read_text());data['reject_reason']=report['reject_reason'];write_json(self.output/file,data)
        with self.assertRaisesRegex(ValueError,'not_reproduced'):self.reconstruct('pose_v14',report)

    def test_single_selected_unified_call_and_exact_transport_file(self):
        def protect(source,out,**kwargs):
            self.assertEqual(kwargs['photo_engine'],'distal_v13');self.assertFalse(kwargs['detect_only'])
            rgb,report,*_=self.fresh_engine(out,'distal_v13');return rgb,report
        with patch.object(export,'route_input',return_value=dict(input_type='PHOTO')),patch.object(export,'protect_image',side_effect=protect) as invoke:
            path=export.run(self.source,self.output,photo_engine='distal_v13',consumed_registry=self.registry_path,request_id='test-id')
        invoke.assert_called_once();wire=json.loads(path.read_text());self.assertEqual(wire['request_id'],'test-id')
        self.assertNotIn(str(self.root),json.dumps(wire));self.assertEqual(wire['status'],'rejected')

    def test_fresh_output_and_unknown_engine_reject_before_call(self):
        self.output.mkdir()
        with patch.object(export,'protect_image') as invoke:
            with self.assertRaisesRegex(FileExistsError,'fresh_export'):export.run(self.source,self.output,photo_engine='distal_v13',consumed_registry=self.registry_path,request_id='x')
            with self.assertRaisesRegex(ValueError,'unsupported'):export.run(self.source,self.root/'other',photo_engine='unknown',consumed_registry=self.registry_path,request_id='x')
        invoke.assert_not_called()

    def test_scanner_input_rejects_without_silent_engine_fallback(self):
        with patch.object(export,'route_input',return_value=dict(input_type='SCANNER')),patch.object(export,'protect_image') as invoke:
            with self.assertRaisesRegex(ValueError,'PHOTO_input'):export.run(self.source,self.output,photo_engine='distal_v13',consumed_registry=self.registry_path,request_id='x')
        invoke.assert_not_called();self.assertFalse(self.output.exists())

    def test_source_race_during_unified_call_prevents_transport(self):
        def protect(source,out,**kwargs):
            rgb,report,*_=self.fresh_engine(out)
            changed=self.rgb.copy();changed[0,0]=0;Image.fromarray(changed).save(self.source)
            return rgb,report
        with patch.object(export,'route_input',return_value=dict(input_type='PHOTO')),patch.object(export,'protect_image',side_effect=protect):
            with self.assertRaisesRegex(ValueError,'source_changed'):export.run(self.source,self.output,photo_engine='distal_v13',consumed_registry=self.registry_path,request_id='x')
        self.assertFalse((self.output/'result.transport.json').exists())

    def test_CLI_stdout_is_small_JSON_only_and_failure_redacts_details(self):
        args=['--input',str(self.source),'--output',str(self.output),'--photo-engine','pose_v14',
            '--consumed-registry',str(self.registry_path),'--request-id','r1']
        stdout,stderr=io.StringIO(),io.StringIO()
        with (patch.object(export,'cli_progress_to_stderr',return_value=contextlib.nullcontext()),patch.object(export,'run',return_value=self.output/'result.transport.json') as call,
                contextlib.redirect_stdout(stdout),contextlib.redirect_stderr(stderr)):
            self.assertEqual(export.main(args),0)
        self.assertEqual(set(json.loads(stdout.getvalue())),{'status','transport_path'});self.assertEqual(call.call_args.kwargs['request_id'],'r1')
        stdout,stderr=io.StringIO(),io.StringIO()
        with (patch.object(export,'cli_progress_to_stderr',return_value=contextlib.nullcontext()),patch.object(export,'run',side_effect=ValueError('C:/PRIVATE/source.png')),
                contextlib.redirect_stdout(stdout),contextlib.redirect_stderr(stderr)):
            self.assertEqual(export.main(args),1)
        self.assertEqual(json.loads(stdout.getvalue()),dict(status='error'));self.assertNotIn('PRIVATE',stdout.getvalue()+stderr.getvalue())


if __name__=='__main__':unittest.main()
