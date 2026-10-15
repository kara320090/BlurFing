"""Source-set mutation tests only; synthetic pipeline IO never renders a fingerprint."""
from contextlib import ExitStack
import hashlib,json,os,shutil,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
import protection_runtime_sources_v1 as sources


class SourceFixture(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory(prefix='runtime source set ');self.addCleanup(self.folder.cleanup)
        self.root=Path(self.folder.name);self.ai=self.root/'ai'
        (self.ai/'scripts/java').mkdir(parents=True);(self.ai/'platform/windows').mkdir(parents=True)
        self.omitted=['scripts/photo_candidate_context_v1.py','scripts/fingerprint_input_router.py',
            'scripts/canonical_fingerprint_roi.py','scripts/java/BlurFingMatcher.java',
            'platform/windows/sourceafis_matcher_windows.py','platform/windows/run_unified.ps1']
        for index,name in enumerate(self.omitted):(self.ai/name).write_text('source '+str(index)+'\n',encoding='utf-8')


class RuntimeSourceInventoryTests(SourceFixture):
    def test_formerly_omitted_dependencies_each_invalidate_snapshot(self):
        expected=sources.capture_runtime_sources(self.ai)
        for name in self.omitted:
            with self.subTest(name=name):
                path=self.ai/name;before=path.read_bytes();path.write_bytes(before+b'# changed\n')
                with self.assertRaisesRegex(RuntimeError,'source_set_changed'):sources.assert_runtime_sources_unchanged(expected)
                path.write_bytes(before)
        self.assertEqual(sources.assert_runtime_sources_unchanged(expected),expected.provenance())

    def test_added_and_deleted_code_are_not_hidden_by_static_filename_list(self):
        before=sources.capture_runtime_sources(self.ai);added=self.ai/'scripts/new_dependency.py';added.write_text('new')
        with self.assertRaisesRegex(RuntimeError,'added'):sources.assert_runtime_sources_unchanged(before)
        after=sources.capture_runtime_sources(self.ai);added.unlink()
        with self.assertRaisesRegex(RuntimeError,'deleted'):sources.assert_runtime_sources_unchanged(after)

    def test_same_size_source_edit_with_restored_timestamp_is_detected(self):
        before=sources.capture_runtime_sources(self.ai);path=self.ai/self.omitted[0];info=path.stat()
        data=path.read_bytes();path.write_bytes(data.replace(b'source',b'change'))
        os.utime(path,ns=(info.st_atime_ns,info.st_mtime_ns))
        with self.assertRaisesRegex(RuntimeError,'source_set_changed'):sources.assert_runtime_sources_unchanged(before)

    def test_noncode_outputs_and_private_environment_assets_are_ignored(self):
        expected=sources.capture_runtime_sources(self.ai)
        for name in ['scripts/private/photo.py','scripts/.venv/site-packages/dependency.py','scripts/cache/cache.py',
            'scripts/__pycache__/cache.py','platform/vendor/external.java','platform/weights/not_public.py',
            'scripts/photo.png','scripts/model.pt','scripts/result.private.json','scripts/java/BlurFingMatcher.class']:
            path=self.ai/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'not public source')
        self.assertEqual(sources.assert_runtime_sources_unchanged(expected),expected.provenance())

    def test_relative_keys_order_and_digest_do_not_depend_on_absolute_root(self):
        expected=sources.capture_runtime_sources(self.ai);other=self.root/'other location';shutil.copytree(self.ai,other)
        second=sources.capture_runtime_sources(other);one,two=expected.provenance(),second.provenance()
        self.assertEqual(one,two);self.assertEqual(list(one['files']),sorted(one['files']))
        self.assertTrue(all('\\' not in name and not Path(name).is_absolute() for name in one['files']))
        self.assertNotIn(str(self.root),json.dumps(one));self.assertEqual(one['file_count'],len(self.omitted))

    def test_snapshot_files_immutable_and_provenance_is_a_copy(self):
        expected=sources.capture_runtime_sources(self.ai)
        with self.assertRaises(TypeError):expected.files['scripts/new.py']='0'*64
        data=expected.provenance();data['files']['scripts/new.py']='0'*64
        self.assertNotIn('scripts/new.py',expected.provenance()['files'])

    def test_selected_cpp_source_is_included_and_changed_bytes_rejected(self):
        path=self.ai/'platform/windows/local.cpp';path.write_text('int main(){}')
        expected=sources.capture_runtime_sources(self.ai);self.assertIn('platform/windows/local.cpp',expected.files)
        path.write_text('int changed(){}')
        with self.assertRaisesRegex(RuntimeError,'source_set_changed'):sources.assert_runtime_sources_unchanged(expected)

    def directory_link(self,path,target):
        try:path.symlink_to(target,target_is_directory=True)
        except OSError:
            if os.name!='nt':raise
            subprocess.run(['cmd.exe','/c','mklink','/J',str(path),str(target)],check=True,capture_output=True)

    def test_real_directory_symlink_or_windows_junction_cannot_escape_scope(self):
        outside=self.root/'outside';outside.mkdir();(outside/'secret.py').write_text('not source')
        self.directory_link(self.ai/'scripts/linked',outside)
        with self.assertRaisesRegex(RuntimeError,'directory_link'):sources.capture_runtime_sources(self.ai)

    def test_selected_source_reparse_is_rejected_before_file_read(self):
        path=self.ai/self.omitted[0];original=sources._reparse
        with patch.object(sources,'_reparse',side_effect=lambda p:p==path or original(p)):
            with self.assertRaisesRegex(RuntimeError,'link_or_nonregular'):sources.capture_runtime_sources(self.ai)

    def test_missing_selected_root_cannot_silently_shrink_inventory(self):
        (self.ai/'platform').rename(self.ai/'platform_moved')
        with self.assertRaises((RuntimeError,FileNotFoundError)):sources.capture_runtime_sources(self.ai)

    def test_runtime_snapshot_does_not_extend_or_change_frozen_V6_training_hashes(self):
        from train_whole_pad_context_v6 import code_hashes
        before=code_hashes();self.assertEqual(len(before),16)
        self.assertNotIn('protection_runtime_sources_v1.py',before)
        expected=sources.capture_runtime_sources(self.ai);sources.assert_runtime_sources_unchanged(expected)
        self.assertEqual(code_hashes(),before)


class RuntimeSourcePipelineContracts(SourceFixture):
    def capture(self):return sources.capture_runtime_sources(self.ai)

    def test_native_bundle_rejects_public_dependency_edit_not_in_curated_hashes(self):
        import protect_photo_whole_pad_context_native_v1 as pipeline
        output=self.root/'output';mask=np.ones((16,16),bool);rgb=np.full((16,16,3),120,np.uint8)
        source=dict(source_id='INPUT',source_path='unused')
        def infer(folder,inputs,out):
            out.mkdir(parents=True);Image.fromarray(mask.astype(np.uint8)*255).save(out/'INPUT.png')
            return dict(input_manifest_sha256='manifest',model_sha256='model',rows=[dict(source_id='INPUT',prediction_sha256='png')])
        def evaluate(*args,**kwargs):
            (self.ai/self.omitted[0]).write_text('edited dependency')
            return rgb,dict(status='rejected',fingerprints_transformed=0)
        with (patch.object(pipeline,'capture_runtime_sources',side_effect=self.capture),patch.object(pipeline,'infer',side_effect=infer),
              patch.object(pipeline,'json_snapshot',return_value=({'sources':[source]},'manifest')),
              patch.object(pipeline,'read_mask',return_value=mask),patch.object(pipeline,'native_shape',return_value=(16,16)),
              patch.object(pipeline,'evaluate_learned_mask',side_effect=evaluate),patch.object(pipeline,'save_result'),
              patch.object(pipeline,'unchanged'),patch.object(pipeline,'check_tiles')):
            with self.assertRaisesRegex(RuntimeError,'source_set_changed'):pipeline.protect_bundle(self.root,self.root,output,True)
        self.assertFalse((output/'protection.private.json').exists())

    def test_distal_prepared_rejects_added_java_source(self):
        import protect_photo_distal_native_v1 as pipeline
        source=dict(source_id='INPUT',coarse_path='unused',coarse_sha256='sha');output=self.root/'result'
        mask=np.ones((16,16),bool);rgb=np.full((16,16,3),120,np.uint8)
        def evaluate(*args,**kwargs):
            (self.ai/'scripts/java/NewMatcher.java').write_text('added worker')
            return rgb,dict(status='rejected',fingerprints_transformed=0)
        with (patch.object(pipeline,'capture_runtime_sources',side_effect=self.capture),
              patch.object(pipeline.tiles,'json_snapshot',return_value=({'sources':[source]},'manifest')),
              patch.object(pipeline.tiles,'check_tiles'),patch.object(pipeline.tiles,'unchanged'),
              patch.object(pipeline,'read_mask',return_value=mask),patch.object(pipeline,'native_shape',return_value=(16,16)),
              patch.object(pipeline,'evaluate_learned_mask',side_effect=evaluate),patch.object(pipeline,'save_result')):
            with self.assertRaisesRegex(RuntimeError,'source_set_changed'):pipeline.protect_prepared(self.root,output,detect_only=True)
        self.assertFalse((output/'protection.private.json').exists())

    def run_single(self,pipeline,engine,*,mutate):
        from test_pad_refinement_tiles_v3 import TileFixture
        fixture=TileFixture();fixture.setUp();self.addCleanup(fixture.doCleanups)
        source=Path(fixture.inputs[0]['source_path']);registry=fixture.root/'registry.json'
        registry.write_text(json.dumps(fixture.registry),encoding='utf-8');output=fixture.root/'result'
        rgb=np.asarray(Image.open(source).convert('RGB')).copy()
        def prepare(inputs,registry,folder,*,purpose):folder.mkdir(parents=True);return dict(sources=[])
        def protected(*args,**kwargs):
            target=Path(args[2] if engine=='native_v12' else args[1]);(target/'INPUT').mkdir(parents=True)
            Image.fromarray(rgb).save(target/'INPUT/returned.png')
            if mutate:(self.ai/self.omitted[0]).unlink()
            return dict(rows=[dict(returned_RGB_sha256=hashlib.sha256(rgb.tobytes()).hexdigest(),fingerprints_rejected=0,
                status='rejected',fingerprints_detected=0,fingerprints_transformed=0)],model_sha256='model')
        with ExitStack() as stack:
            stack.enter_context(patch.object(pipeline,'capture_runtime_sources',side_effect=self.capture))
            stack.enter_context(patch.object(pipeline.shared,'route_input',return_value=dict(input_type='PHOTO')))
            stack.enter_context(patch.object(pipeline.shared,'load_semantics'))
            if engine=='native_v12':
                stack.enter_context(patch.object(pipeline,'load_model',return_value=(object(),dict(consumed_registry_sha256=pipeline.hash_json(fixture.registry)))))
                stack.enter_context(patch.object(pipeline,'prepare',side_effect=prepare))
                stack.enter_context(patch.object(pipeline,'protect_bundle',side_effect=protected))
                invoke=lambda:pipeline.run(source,fixture.root/'model',registry,output,photo_semantics=fixture.inputs[0]['semantics'])
            else:
                stack.enter_context(patch.object(pipeline.tiles,'prepare',side_effect=prepare))
                stack.enter_context(patch.object(pipeline,'protect_prepared',side_effect=protected))
                invoke=lambda:pipeline.run(source,registry,output,photo_semantics=fixture.inputs[0]['semantics'])
            if mutate:
                with self.assertRaisesRegex(RuntimeError,'source_set_changed'):invoke()
                self.assertFalse((output/'result.private.json').exists())
                return
            returned,report=invoke()
        np.testing.assert_array_equal(returned,rgb)
        self.assertTrue(report['runtime_source_snapshot_verified']);self.assertFalse(report['runtime_source_snapshot']['training_hash_contract_modified'])
        self.assertIn('scripts/photo_candidate_context_v1.py',report['runtime_source_snapshot']['files'])
        self.assertEqual(json.loads((output/'result.private.json').read_text(encoding='utf-8'))['runtime_source_snapshot'],report['runtime_source_snapshot'])

    def test_native_single_rejects_deleted_dependency_after_nested_work(self):
        import protect_photo_whole_pad_context_native_v1 as pipeline
        self.run_single(pipeline,'native_v12',mutate=True)

    def test_distal_single_rejects_deleted_dependency_after_nested_work(self):
        import protect_photo_distal_native_v1 as pipeline
        self.run_single(pipeline,'distal_v13',mutate=True)

    def test_single_metadata_and_RGB_preserved_for_each_explicit_engine(self):
        import protect_photo_whole_pad_context_native_v1 as native
        import protect_photo_distal_native_v1 as distal
        for pipeline,engine in [(native,'native_v12'),(distal,'distal_v13')]:
            with self.subTest(engine=engine):self.run_single(pipeline,engine,mutate=False)


if __name__=='__main__':unittest.main()
