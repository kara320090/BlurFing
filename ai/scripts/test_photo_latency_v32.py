"""Synthetic appearance parity and final source sealing, without private data."""
from pathlib import Path
from contextlib import contextmanager
import json,os,tempfile,unittest
from unittest.mock import patch
import cv2
import numpy as np
from scipy import ndimage
import protection_runtime_sources_v1 as sources
from photo_parallel_regions_v32 import region_workers


class SourceSealTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        for name in sources.SOURCE_DIRECTORIES:(self.root/name).mkdir()
        self.path=self.root/'scripts/code.py';self.path.write_text('before')
        (self.root/'platform/stable.py').write_text('stable')

    def test_nested_guards_are_coalesced_but_exit_rehashes(self):
        expected=sources.capture_runtime_sources(self.root)
        with patch.object(sources,'_hash_source',wraps=sources._hash_source) as hashed:
            with sources.sealed_source_transaction(expected):
                for _ in range(4):
                    self.assertEqual(sources.capture_runtime_sources(self.root).files,expected.files)
                    sources.assert_runtime_sources_unchanged(expected)
                self.assertEqual(hashed.call_count,2)
            self.assertEqual(hashed.call_count,4)

    def test_changed_added_deleted_files_cannot_publish(self):
        for action in ('change','add','delete'):
            with self.subTest(action=action):
                self.path.write_text('before');extra=self.root/'platform/extra.py'
                extra.unlink(missing_ok=True);expected=sources.capture_runtime_sources(self.root)
                published=[]
                with self.assertRaisesRegex(RuntimeError,'source_set_changed'):
                    with sources.sealed_source_transaction(expected):
                        if action=='change':self.path.write_text('edited')
                        if action=='add':extra.write_text('extra')
                        if action=='delete':self.path.unlink()
                        sources.assert_runtime_sources_unchanged(expected)
                    published.append(True)
                self.assertEqual(published,[])
                self.assertIsNone(sources._transaction.get())

    def test_earlier_mismatch_and_nested_transaction_remain_fatal(self):
        expected=sources.capture_runtime_sources(self.root);self.path.write_text('edited')
        with self.assertRaisesRegex(RuntimeError,'source_set_changed'):
            with sources.sealed_source_transaction(expected):self.fail('entered')
        expected=sources.capture_runtime_sources(self.root)
        with sources.sealed_source_transaction(expected):
            with self.assertRaisesRegex(RuntimeError,'nested'):
                with sources.sealed_source_transaction(expected):pass

    def test_exception_restores_immediate_default_guards(self):
        expected=sources.capture_runtime_sources(self.root)
        with self.assertRaisesRegex(ValueError,'abort'):
            with sources.sealed_source_transaction(expected):raise ValueError('abort')
        self.path.write_text('edited')
        with self.assertRaisesRegex(RuntimeError,'source_set_changed'):sources.assert_runtime_sources_unchanged(expected)


class NativeAppearanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cv2.setNumThreads(1)

    def arrays(self):
        y,x=np.mgrid[:128,:176]
        rgb=np.stack((90+x*.5,80+y*.7,65+x*.12+y*.2),axis=-1).astype(np.uint8)
        labels=np.zeros((128,176),np.uint16)
        labels[((x-55)/24)**2+((y-65)/45)**2<1]=3
        labels[((x-115)/23)**2+((y-64)/43)**2<1]=7
        rgb[x<32]=[25,35,45]
        return rgb,labels

    def test_parallel_PNG_is_one_canonical_stream_and_exact_on_all_row_boundaries(self):
        import io
        from PIL import Image
        from photo_parallel_png_v32 import encode
        from photo_experimental_transport_v1 import _png_preflight
        for h,w in ((1,1),(3,17),(61,43),(127,137)):
            rgb=np.random.default_rng(h).integers(0,256,(h,w,3),dtype=np.uint8)
            for workers in (1,2,3,4):
                with self.subTest(shape=rgb.shape,workers=workers):
                    content=encode(rgb,workers=workers)
                    self.assertEqual(_png_preflight(content,2),(w,h))
                    np.testing.assert_array_equal(np.array(Image.open(io.BytesIO(content))),rgb)

    def test_V27_parallel_material_has_identical_pixels_and_complete_metadata(self):
        from photo_generated_detail_v27 import render
        from photo_parallel_material_v32 import render as parallel
        rgb,labels=self.arrays();mask=labels>0
        for detail in ((3,7),(7,)):
            from functools import partial
            engine=partial(render,detail_regions=detail)
            expected,report=engine(rgb,mask,labels,seed=321)
            with region_workers():actual,metadata=parallel(engine,rgb,mask,labels,seed=321)
            np.testing.assert_array_equal(actual,expected)
            self.assertEqual(metadata,report)
            np.testing.assert_array_equal(actual[~mask],rgb[~mask])

    def test_all_boundary_stages_parallel_and_serial_are_identical(self):
        from photo_synthetic_replacement_v19 import render
        from photo_junction_appearance_v23 import refine_complete
        rgb,labels=self.arrays();mask=labels>0
        generated,_=render(rgb,mask,labels,seed=12)
        expected,report=refine_complete(rgb,generated,mask,labels)
        with region_workers():actual,metadata=refine_complete(rgb,generated,mask,labels)
        np.testing.assert_array_equal(actual,expected)
        self.assertEqual(metadata,report)

    def test_component_reuse_is_job_scoped_and_preserve_flag_independent(self):
        import photo_coarse_cache_v31 as cache
        import finger_body_distal_estimator as estimator
        from photo_lossless_io_v29 import lossless_io
        y,x=np.mgrid[:96,:64];body=((x-32)/17)**2+((y-48)/40)**2<1;tip=body&(y<35)
        baseline=cache.original(body,tip,preserve_candidates=True)
        with patch.object(cache,'original_component',wraps=cache.original_component) as calculate:
            with lossless_io() as state:
                estimator.estimate(body,tip)
                actual=estimator.estimate(body,tip,preserve_candidates=True)
                self.assertGreater(state.component_hits,0)
                self.assertEqual(calculate.call_count,1)
                np.testing.assert_array_equal(actual['mask'],baseline['mask'])
                np.testing.assert_array_equal(actual['regions'][0]['body_mask'],baseline['regions'][0]['body_mask'])
                actual['mask'][:]=False
                np.testing.assert_array_equal(estimator.estimate(body,tip)['mask'],baseline['mask'])
            self.assertFalse(state.components)
            with lossless_io():estimator.estimate(body,tip)
            self.assertEqual(calculate.call_count,2)

    def test_profile_is_explicit_and_rejects_unknown_names(self):
        from photo_analysis_profile_v32 import profile,SEMANTIC_INPUT_SIDE
        self.assertEqual(profile('native'),'native');self.assertEqual(profile('fast_v32'),'fast_v32')
        self.assertEqual(SEMANTIC_INPUT_SIDE,1536)
        for name in ('',None,'fast',False):
            with self.assertRaises(ValueError):profile(name)

    def test_hand_decode_keeps_independent_identical_arrays_for_EXIF_one(self):
        import hashlib
        import mediapipe_hand_worker_v1 as hand
        from PIL import Image
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source.png';model=root/'model.task';output=root/'hand.json'
            rgb=np.zeros((1280,960,3),np.uint8);rgb[:,:,0]=150
            Image.fromarray(rgb).save(source);model.write_bytes(b'synthetic fixture')
            sha=hashlib.sha256(model.read_bytes()).hexdigest()
            encoded,upright,orientation=hand.decode(source)
            self.assertEqual(orientation,1);np.testing.assert_array_equal(encoded,rgb)
            np.testing.assert_array_equal(upright,rgb);upright[:]=0
            np.testing.assert_array_equal(encoded,rgb)

    def test_fast_partition_retains_every_pixel_and_groups_rejected_fragments(self):
        from photo_semantic_pose_proposal_v32 import partition
        mask=np.zeros((32,48),bool);owners=np.zeros(mask.shape,np.uint8)
        mask[2:8,2:8]=True;owners[2:8,2:8]=1
        mask[12:18,2:8]=True;owners[12:18,2:8]=1
        mask[2:8,22:28]=True;owners[2:8,22:28]=2
        mask[25,35]=True;mask[29,40]=True
        labels,count=partition(mask,owners,[1,2])
        self.assertEqual(count,3);self.assertEqual(labels[3,3],labels[13,3])
        self.assertEqual(labels[25,35],labels[29,40])
        np.testing.assert_array_equal(labels>0,mask)

    def test_overwide_pose_cap_is_rejected_without_modifying_other_digit(self):
        from photo_pose_extent_guard_v32 import bounded_caps
        owners=np.zeros((20,30),np.uint8);owners[:,:15]=1;owners[:,15:]=2
        mask=owners>0
        pose=dict(owner_labels=owners,axes=[dict(digit='thumb',label=1),dict(digit='index',label=2)])
        def row(digit,width):return dict(candidate_id='pose-'+digit,status='rounded_cap_applied',
            geometry=dict(reference_width=width,joint_xy=[0.,0.],tip_xy=[0.,10.]))
        result,metadata=bounded_caps(mask,dict(candidates=[row('thumb',30.),row('index',12.)]),pose)
        self.assertFalse(result[owners==1].any());self.assertTrue(result[owners==2].all())
        self.assertTrue(mask.all());self.assertTrue(metadata['candidates'][0]['unanchored_candidate_excluded'])
        self.assertEqual(metadata['applied_caps'],1)

    def test_pose_only_cannot_claim_semantic_only_while_using_learned_support(self):
        from photo_crease_native_adapter_v1 import prepare
        for options in (dict(pose_only=True),dict(pose_only=True,partial_observed_pose=True,learned_support=np.ones((1,1),bool)),
                        dict(search_crease=False)):
            with self.assertRaises(ValueError):prepare(None,None,None,None,{},None,**options)

    def test_no_semantic_pose_is_non_application_without_V6_or_GT_fallback(self):
        import shutil
        from test_pad_refinement_tiles_v3 import TileFixture
        from photo_semantic_pose_proposal_v32 import propose
        fixture=TileFixture();fixture.setUp();self.addCleanup(fixture.doCleanups)
        item=fixture.inputs[0];source=Path(item['source_path']);sem=Path(item['semantics'])
        record=json.loads((sem/'semantics.json').read_text());record.update(image_height=6,image_width=8)
        (sem/'semantics.json').write_text(json.dumps(record))
        registry=fixture.root/'registry.json';registry.write_text(json.dumps(fixture.registry))
        out=fixture.root/'proposal';out.mkdir();calls=[]
        class FakeResources:
            @contextmanager
            def semantic_job(self,source,output):
                shutil.copytree(sem,output)
                class Job:
                    def finish(self):calls.append('semantic')
                yield Job()
            @contextmanager
            def hand_job(self,source,output):
                output.write_text('{}')
                class Job:
                    def finish(self):calls.append('hand')
                yield Job()
        with (patch('photo_pose_native_pipeline_v1.verify_worker'),
              patch('photo_partial_pose_v25.geometry_from_worker',return_value=(None,dict(reason='not_observed'))) as geometry,
              patch('photo_crease_native_adapter_v1.prepare',side_effect=AssertionError('unobserved pose used'))):
            propose(source,fixture.root/'NO_V6_MODEL',registry,out,execution_context=FakeResources())
        self.assertEqual(calls,['semantic','hand']);self.assertIsNone(geometry.call_args.kwargs['learned_support'])
        binding=json.loads((out/'proposal.private.json').read_text())
        self.assertFalse(binding['V6_learned_pad_model_used']);self.assertIsNone(binding['partial_pose'])
        from PIL import Image
        self.assertFalse(np.array(Image.open(out/'proposal.png')).any())


if __name__=='__main__':unittest.main()
