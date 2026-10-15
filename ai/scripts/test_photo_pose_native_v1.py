"""Synthetic contracts only; never runs MediaPipe or protection renderers."""
import copy,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
import mediapipe_hand_worker_v1 as hand
import photo_pose_native_pipeline_v1 as pose
import protect_photo_pose_native_v1 as entry
from pad_refinement_data_contract_v2 import source_record,digest
from test_pad_refinement_tiles_v3 import TileFixture


class PoseContracts(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.rgb=np.indices((60,100)).sum(axis=0).astype(np.uint8)[...,None]*np.ones((1,1,3),np.uint8)
        path=self.root/'source.png';Image.fromarray(self.rgb).save(path)
        sem=self.root/'semantics';sem.mkdir();body=np.ones((60,100),bool)
        Image.fromarray(body.astype(np.uint8)*255).save(sem/'body.png');Image.fromarray(np.zeros(body.shape,np.uint8)).save(sem/'tip.png')
        (sem/'semantics.json').write_text(json.dumps(dict(source_sha256=digest(path),coordinate_system='encoded_original_pixels',
            body_sha256=digest(sem/'body.png'),tip_sha256=digest(sem/'tip.png'),body_classes=[1,2],tip_class=2,minimum_votes=2)),encoding='utf-8')
        self.source=source_record(path,'SYNTHETIC',sem,self.rgb)
        points=np.zeros((21,2),np.float64)
        for i,(tip,dip) in enumerate(pose.pose.PAIRS):points[tip]=[10+20*i,5];points[dip]=[10+20*i,20]
        self.normalized=(points+.5)/[100,60]

    def record(self,count=1):
        return dict(version=hand.VERSION,status='observed' if count else 'no_hand_observed',source_sha256=self.source['source_sha256'],
            encoded_RGB_sha256=self.source['source_RGB_sha256'],upright_RGB_sha256=self.source['source_RGB_sha256'],
            encoded_shape=list(self.rgb.shape),upright_shape=list(self.rgb.shape),source_exif_orientation=1,
            model_sha256=hand.MODEL_SHA256,worker_code_sha256=digest(hand.__file__),configuration=dict(hand.CONFIGURATION),
            runtime=dict(mediapipe_version=hand.MEDIAPIPE_VERSION),GT_used=False,hand_count=count,
            hands=[dict(normalized_xy=self.normalized.tolist()) for _ in range(count)])

    def test_no_hand_and_multiple_hands_are_original_rejected_without_base_gate(self):
        for count in [0,2]:
            with self.subTest(count=count),patch.object(pose.base,'evaluate_learned_mask',side_effect=AssertionError('gate must not run')):
                returned,report=pose.evaluate(self.source,self.record(count))
                np.testing.assert_array_equal(returned,self.rgb);self.assertEqual(report['status'],'rejected')
                self.assertEqual(report['changed_pixels'],0);self.assertIn('exactly_one',report['reject_reason'])
                self.assertFalse(report['approved_for_protection']);self.assertFalse(report['V6_learned_pad_model_used'])

    def test_source_model_runtime_shape_EXIF_worker_code_bindings_reject_cache_mixup(self):
        mutations=[('source_sha256','0'*64),('encoded_RGB_sha256','0'*64),('upright_RGB_sha256','0'*64),
                   ('encoded_shape',[60,99,3]),('upright_shape',[100,60,3]),('source_exif_orientation',6),
                   ('model_sha256','0'*64),('worker_code_sha256','0'*64),('configuration',{}),('runtime','invalid')]
        for key,value in mutations:
            with self.subTest(key=key),patch.object(pose.base,'evaluate_learned_mask',side_effect=AssertionError('unbound gate')):
                record=self.record();record[key]=value;returned,report=pose.evaluate(self.source,record)
                np.testing.assert_array_equal(returned,self.rgb);self.assertEqual(report['status'],'rejected')
                self.assertEqual(report['changed_pixels'],0)

    def test_invalid_axis_or_malformed_landmarks_returns_original_without_fallback(self):
        bad=self.record();bad['hands'][0]['normalized_xy'][4]=bad['hands'][0]['normalized_xy'][3]
        nan=self.record();nan['hands'][0]['normalized_xy'][4][0]=float('nan')
        malformed=self.record();malformed['hands'][0]=None
        for record in [bad,nan,malformed]:
            with patch.object(pose.base,'evaluate_learned_mask',side_effect=AssertionError('invalid pose rendered')):
                returned,report=pose.evaluate(self.source,record)
            np.testing.assert_array_equal(returned,self.rgb);self.assertEqual(report['status'],'rejected')

    def test_explicit_owner_axes_and_V12_adapter_are_used_and_estimator_contexts_ignored(self):
        def gate(source,mask,sha,**kwargs):
            self.assertTrue(kwargs['detect_only']);self.assertIs(kwargs['_scope_adapter'],pose.prepare_scoped_region)
            self.assertEqual(sha,pose.base.pixel_hash(mask))
            partition=kwargs['_candidate_builder'](mask,object())
            self.assertEqual(partition['labels'].dtype,np.uint16);np.testing.assert_array_equal(partition['labels']>0,mask)
            records=partition['records'];self.assertEqual(len(records),5)
            for r in records:
                self.assertEqual(r['association']['axis_native_yx'],[-1.,0.]);self.assertFalse(r['association']['anatomical_owner_verified'])
            return self.rgb.copy(),dict(regions=[],status='rejected',changed_pixels=0,returned_RGB_sha256=pose.base.pixel_hash(self.rgb))
        before=copy.deepcopy(self.record())
        with patch.object(pose.base,'evaluate_learned_mask',side_effect=gate):returned,report=pose.evaluate(self.source,before,detect_only=True)
        np.testing.assert_array_equal(returned,self.rgb);self.assertEqual(before,self.record())
        self.assertTrue(report['RGB_outside_accepted_permission_preserved']);self.assertFalse(report['legacy_estimator_contexts_used'])

    def test_base_return_cannot_change_pixels_without_accepted_permission(self):
        def wrong(*args,**kwargs):
            changed=self.rgb.copy();changed[50,50]^=255
            return changed,dict(regions=[],status='rejected')
        with patch.object(pose.base,'evaluate_learned_mask',side_effect=wrong):
            with self.assertRaisesRegex(ValueError,'outside_accepted'):pose.evaluate(self.source,self.record())

    def test_worker_fresh_source_bound_JSON_no_hand_and_model_pin(self):
        model=self.root/'synthetic.task';model.write_bytes(b'synthetic non-model fixture');out=self.root/'record.json'
        with patch.object(hand,'MODEL_SHA256',hand.digest(model)),patch.object(hand,'_detect',return_value=([],dict(mediapipe_version=hand.MEDIAPIPE_VERSION))) as detect:
            record=hand.run(self.source['source_path'],model,out)
            self.assertEqual(record['status'],'no_hand_observed');self.assertEqual(record['source_sha256'],self.source['source_sha256'])
            self.assertEqual(record['encoded_RGB_sha256'],self.source['source_RGB_sha256']);self.assertEqual(record['configuration'],hand.CONFIGURATION)
            with self.assertRaises(FileExistsError):hand.run(self.source['source_path'],model,out)
            self.assertEqual(detect.call_count,1)
        with patch.object(hand,'_detect',side_effect=AssertionError('bad model used')):
            with self.assertRaisesRegex(ValueError,'SHA256_mismatch'):hand.run(self.source['source_path'],model,self.root/'new.json')

    def test_worker_EXIF_upright_decode_and_L_support_do_not_edit_source(self):
        for exif in range(1,9):
            path=self.root/f'L-{exif}.png';image=Image.fromarray(self.rgb[:,:,0]);meta=Image.Exif();meta[274]=exif;image.save(path,exif=meta)
            before=path.read_bytes();encoded,upright,orientation=hand.decode(path)
            self.assertEqual(orientation,exif);np.testing.assert_array_equal(encoded,self.rgb)
            self.assertEqual(upright.shape,(100,60,3) if exif>=5 else (60,100,3));self.assertEqual(before,path.read_bytes())

    def test_flags_and_GT_rejected_before_gate(self):
        with self.assertRaisesRegex(ValueError,'boolean'):pose.evaluate({},None,detect_only='false')
        source=self.source|dict(GT_mask_sha256='0'*64)
        with self.assertRaisesRegex(ValueError,'GT_fields'):pose.evaluate(source,self.record())

    def test_rejected_geometry_cannot_hide_source_file_race(self):
        def change_then_reject(source,rgb,record):
            changed=rgb.copy();changed[0,0]^=255;Image.fromarray(changed).save(source['source_path'])
            raise ValueError('invalid_pose')
        with patch.object(pose,'geometry_from_worker',side_effect=change_then_reject):
            with self.assertRaisesRegex(ValueError,'asset_hash_mismatch'):pose.evaluate(self.source,self.record(0))

    def test_rejected_geometry_cannot_hide_decoded_RGB_mutation(self):
        def change_then_reject(source,rgb,record):
            rgb[0,0]^=255;raise ValueError('invalid_pose')
        with patch.object(pose,'geometry_from_worker',side_effect=change_then_reject):
            with self.assertRaisesRegex(ValueError,'decoded_source_changed'):pose.evaluate(self.source,self.record(0))


class PoseEntryContracts(TileFixture):
    def test_existing_output_and_bad_flags_stop_before_runtime(self):
        with self.assertRaises(FileExistsError):entry.run('unused','unused',self.root)
        for flag in ['false',1,None]:
            with self.assertRaisesRegex(ValueError,'boolean'):entry.run('unused','unused','unused',detect_only=flag)
            with self.assertRaisesRegex(ValueError,'boolean'):entry.run('unused','unused','unused',development_replay=flag)

    def test_strict_consumed_default_stops_before_hand_worker(self):
        source=Path(self.inputs[0]['source_path']);self.registry[0].update(entry.tiles.image_identity(source))
        registry=self.root/'registry.json';registry.write_text(json.dumps(self.registry),encoding='utf-8')
        with patch.object(entry.subprocess,'run') as worker:
            with self.assertRaisesRegex(ValueError,'decoded_pixels'):entry.run(source,registry,self.root/'result')
        worker.assert_not_called();self.assertFalse((self.root/'result').exists())

    def test_cached_semantics_explicit_replay_fresh_nohand_worker_retains_original_binding(self):
        source=Path(self.inputs[0]['source_path']);before=source.read_bytes();self.registry[0].update(entry.tiles.image_identity(source))
        semantic_path=Path(self.inputs[0]['semantics'])/'semantics.json'
        semantic=json.loads(semantic_path.read_text(encoding='utf-8'))
        with Image.open(source) as image:semantic.update(image_height=image.height,image_width=image.width)
        semantic_path.write_text(json.dumps(semantic),encoding='utf-8')
        registry=self.root/'registry.json';registry.write_text(json.dumps(self.registry),encoding='utf-8');reg_before=registry.read_bytes()
        model=self.root/'synthetic.task';model.write_bytes(b'synthetic worker fixture');output=self.root/'result';calls=[]
        def invoke(command,**kwargs):
            self.assertEqual(Path(command[1]).name,'mediapipe_hand_worker_v1.py');self.assertFalse(kwargs['shell'])
            inp=Path(command[command.index('--input')+1]);self.assertEqual(inp.resolve(),source.resolve())
            target=Path(command[command.index('--output')+1]);calls.append(target)
            hand.run(inp,model,target)
        env=dict(BLURFING_HAND_PYTHON=sys.executable,BLURFING_HAND_MODEL=str(model))
        with (patch.dict(entry.os.environ,env),patch.object(hand,'MODEL_SHA256',hand.digest(model)),
              patch.object(hand,'_detect',return_value=([],dict(mediapipe_version=hand.MEDIAPIPE_VERSION))),
              patch.object(entry.shared,'route_input',return_value=dict(input_type='PHOTO')),
              patch.object(entry.subprocess,'run',side_effect=invoke),
              patch.object(pose.base,'evaluate_learned_mask',side_effect=AssertionError('no hand rendered'))):
            returned,report=entry.run(source,registry,output,photo_semantics=self.inputs[0]['semantics'],development_replay=True)
        self.assertEqual(len(calls),1);self.assertEqual(before,source.read_bytes());self.assertEqual(reg_before,registry.read_bytes())
        np.testing.assert_array_equal(returned,np.asarray(Image.open(source).convert('RGB')))
        self.assertEqual(report['status'],'rejected');self.assertTrue(report['development_replay']);self.assertFalse(report['V6_learned_pad_model_used'])
        self.assertTrue(report['consumed_source_detected']);self.assertFalse(report['independent_final_test'])
        self.assertTrue(report['runtime_source_snapshot_verified']);self.assertTrue((output/'returned.png').is_file())
        worker=json.loads(calls[0].read_text(encoding='utf-8'));self.assertEqual(worker['source_sha256'],digest(source))


if __name__=='__main__':unittest.main()
