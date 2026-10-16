import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
import photo_rounded_native_pipeline_v1 as pipeline
import protect_photo_rounded_native_v1 as entry
from test_photo_pose_native_v1 import PoseContracts


class RoundedNativePartitionTests(unittest.TestCase):
    def context(self,owner,identity='one'):
        return dict(body=owner,candidate_id=identity,axis_native_yx=[-1.,0.],reason=None)

    def test_disconnected_parts_cannot_share_evidence_and_all_pixels_retained(self):
        mask=np.zeros((30,40),bool);mask[2:6,3:8]=True;mask[20:25,4:9]=True
        result=pipeline.connected_partition(mask,[self.context(np.ones_like(mask))])
        self.assertEqual(len(result['records']),2);np.testing.assert_array_equal(result['labels']>0,mask)
        self.assertNotEqual(result['records'][0]['candidate_id'],result['records'][1]['candidate_id'])
        for row in result['records']:self.assertIn('connected_permission',row['association']['association_policy'])

    def test_overlapping_owners_and_unassigned_pixels_are_explicit_rejections(self):
        mask=np.ones((15,20),bool);a=mask.copy();a[:,12:]=False;b=mask.copy();b[:,:8]=False
        result=pipeline.connected_partition(mask,[self.context(a),self.context(b,'two')])
        overlap=result['records'][-1];self.assertEqual(overlap['reason'],'rounded_protection_owner_ambiguous')
        self.assertIsNone(overlap['association']);self.assertEqual(overlap['plan']['mask_pixels'],60)
        none=pipeline.connected_partition(mask,[])
        self.assertEqual(none['records'][0]['reason'],'rounded_protection_owner_unavailable')
        np.testing.assert_array_equal(none['labels']>0,mask)

    def test_component_limit_and_invalid_axes_are_not_silently_dropped(self):
        mask=np.zeros((40,40),bool);mask[::2,::2]=True
        with self.assertRaisesRegex(ValueError,'component_limit'):pipeline.connected_partition(mask,[self.context(np.ones_like(mask))])
        for axis in [[0.,0.],[np.nan,0.],[1.,2.,3.]]:
            context=self.context(mask);context['axis_native_yx']=axis
            with self.assertRaisesRegex(ValueError,'axis_contract'):pipeline.connected_partition(mask,[context])

    def test_unresolved_rounding_does_not_enter_renderer(self):
        mask=np.ones((10,10),bool);context=self.context(mask);context['reason']='rounded_geometry_unresolved';context['axis_native_yx']=None
        row=pipeline.connected_partition(mask,[context])['records'][0]
        self.assertEqual(row['plan']['status'],'rejected');self.assertIsNone(row['association'])


class RoundedNativeEvaluationTests(PoseContracts):
    # Reuse the fixture, not the inherited pose test methods.
    def geometry(self):
        geometry=pipeline.np.zeros((60,100),np.uint8)
        for i in range(5):geometry[:,i*20:(i+1)*20]=i+1
        pose=dict(owner_labels=geometry,axes=[dict(label=i+1,digit=str(i)) for i in range(5)])
        rounding=dict(version='synthetic_geometry_fixture',candidates=[dict(candidate_id='pose-'+str(i),status='rounded_cap_applied',geometry=dict(axis_xy=[0.,-1.])) for i in range(5)])
        mask=np.zeros_like(geometry,bool);mask[2:15,:]=True
        return pose,rounding,mask

    def test_real_adapter_uses_rounded_axes_and_cannot_count_preview_as_protection(self):
        pose,rounding,mask=self.geometry()
        def gate(source,actual,sha,**kwargs):
            self.assertIs(kwargs['_scope_adapter'],pipeline.prepare_scoped_region)
            partition=kwargs['_candidate_builder'](actual,object());np.testing.assert_array_equal(partition['labels']>0,mask)
            self.assertEqual(len(partition['records']),5)
            out=self.rgb.copy();out[partition['labels']==1]^=127
            return out,dict(regions=[dict(region_id=1,status='transformed')],status='partial_success')
        with patch.object(pipeline.base,'evaluate_learned_mask',side_effect=gate):
            returned,report,accepted,labels=pipeline.evaluate(self.source,mask,pipeline.base.pixel_hash(mask),rounding,pose_geometry=pose)
        np.testing.assert_array_equal(accepted,labels==1);np.testing.assert_array_equal(returned[~accepted],self.rgb[~accepted])
        self.assertFalse(report['black_redaction_used_as_protection']);self.assertFalse(report['privacy_validated'])

    def test_actual_return_outside_accepted_scope_is_rejected(self):
        pose,rounding,mask=self.geometry()
        def wrong(*args,**kwargs):
            out=self.rgb.copy();out[55,55]^=255
            return out,dict(regions=[],status='rejected')
        with patch.object(pipeline.base,'evaluate_learned_mask',side_effect=wrong):
            with self.assertRaisesRegex(ValueError,'outside_accepted'):
                pipeline.evaluate(self.source,mask,pipeline.base.pixel_hash(mask),rounding,pose_geometry=pose)

    def test_mask_and_owner_tampering_rejected_before_gate(self):
        pose,rounding,mask=self.geometry()
        with patch.object(pipeline.base,'evaluate_learned_mask',side_effect=AssertionError('invalid input used')):
            with self.assertRaisesRegex(ValueError,'binding_mismatch'):pipeline.evaluate(self.source,mask,'0'*64,rounding,pose_geometry=pose)
            rounding['candidates'][0]['candidate_id']='wrong'
            with self.assertRaisesRegex(ValueError,'identity_mismatch'):pipeline.evaluate(self.source,mask,pipeline.base.pixel_hash(mask),rounding,pose_geometry=pose)


class RoundedNativeEntryTests(unittest.TestCase):
    def test_replay_scope_covers_tile_validation_and_strict_guard_is_restored(self):
        import json
        from test_pad_refinement_tiles_v3 import TileFixture
        fixture=TileFixture();fixture.setUp();self.addCleanup(fixture.doCleanups)
        source=Path(fixture.inputs[0]['source_path']);identity=entry.tiles.image_identity(source)
        fixture.registry[0].update(identity)
        registry=fixture.root/'registry.json';registry.write_text(json.dumps(fixture.registry))
        detection=fixture.root/'detection';dataset=detection/'private/dataset';dataset.mkdir(parents=True)
        (dataset/'manifest.input.private.json').write_text(json.dumps(dict(sources=[dict(source_path=str(source))])))
        def verify(*args,**kwargs):
            entry.tiles.exclude_consumed(identity,fixture.registry)
            return 'scope-verified'
        with patch.object(entry,'_protect_detection',side_effect=verify) as inner:
            with self.assertRaisesRegex(ValueError,'consumed_source_or_decoded_pixels'):
                entry.protect_detection(source,detection,registry,fixture.root/'strict')
            inner.assert_not_called()
            self.assertEqual(entry.protect_detection(source,detection,registry,fixture.root/'replay',development_replay=True),'scope-verified')
        with self.assertRaisesRegex(ValueError,'consumed_source_or_decoded_pixels'):
            entry.tiles.exclude_consumed(identity,fixture.registry)

    def test_bad_flags_and_existing_output_stop_before_runtime(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(FileExistsError):entry.run('unused','unused','unused',folder)
            for value in [1,'false',None]:
                with self.assertRaisesRegex(ValueError,'boolean'):entry.run('unused','unused','unused','unused',development_replay=value)
                with self.assertRaisesRegex(ValueError,'boolean'):entry.protect_detection('unused','unused','unused','unused',detect_only=value)

    def test_saved_actual_transform_not_black_preview_and_EXIF_preserved(self):
        from photo_source_rgb_v1 import canonical_rgb
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source.png';rgb=np.full((40,60,3),140,np.uint8)
            exif=Image.Exif();exif[274]=6;Image.fromarray(rgb).save(source,exif=exif)
            rgb,identity=canonical_rgb(source);mask=np.zeros((40,60),bool);mask[5:20,6:25]=True
            returned=rgb.copy();returned[mask]=[100,135,160]
            output=root/'result';output.mkdir();entry.save_artifacts(source,identity,rgb,mask,returned,mask,output)
            with Image.open(output/'protected.png') as im:
                np.testing.assert_array_equal(np.asarray(im),returned);self.assertEqual(im.getexif()[274],6)
            self.assertTrue((output/'comparison.png').exists());self.assertTrue((output/'rejected_mask.png').exists())


# The imported fixture class has its own complete suite. This module's suite
# selects only new tests so current verification counts remain transparent.
def load_tests(loader, tests, pattern):
    suite=unittest.TestSuite()
    for cls in [RoundedNativePartitionTests,RoundedNativeEntryTests]:suite.addTests(loader.loadTestsFromTestCase(cls))
    for name in ['test_real_adapter_uses_rounded_axes_and_cannot_count_preview_as_protection','test_actual_return_outside_accepted_scope_is_rejected','test_mask_and_owner_tampering_rejected_before_gate']:
        suite.addTest(RoundedNativeEvaluationTests(name))
    return suite


if __name__=='__main__':unittest.main()
