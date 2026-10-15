import unittest
from unittest.mock import patch
import cv2,numpy as np
import photo_orientation_separated_pitch_v1 as observer
import photo_learned_pad_pipeline_v11 as pipeline

class RawOrientationTests(unittest.TestCase):
    def signal(self,period=12,angle=0,noise=0):
        y,x=np.indices((512,512));theta=np.radians(angle)
        raw=128+30*np.cos(2*np.pi*(x*np.cos(theta)+y*np.sin(theta))/period)
        raw+=np.random.default_rng(20261016).normal(0,noise,raw.shape)
        return np.clip(np.rint(raw),0,255).astype(np.uint8)

    def test_known_period_and_direction_survive_on_original_raw_profiles(self):
        mask=np.ones((512,512),bool)
        for angle in [0,30,45,90,135]:
            raw=self.signal(angle=angle);before=raw.copy()
            pitch,report=observer.observe(raw,mask,mask)
            self.assertIsNotNone(pitch);self.assertLess(abs(pitch-12),.15)
            self.assertTrue(report['profile_from_original_raw']);np.testing.assert_array_equal(raw,before)

    def test_fixed_noisy_signal_has_ground_truth_pitch_without_blurring_profile(self):
        raw=self.signal(period=16,angle=30,noise=40);mask=np.ones(raw.shape,bool)
        pitch,report=observer.observe(raw,mask,mask)
        self.assertIsNotNone(pitch);self.assertLess(abs(pitch-16),.25)
        for ref in report['references']:
            self.assertGreaterEqual(ref['credible_patches'],3)
            self.assertTrue(all(r['correlation']>=.6 for r in ref['rows']))

    def test_nonperiodic_sources_reject_and_no_default_pitch_exists(self):
        y,x=np.indices((512,512));mask=np.ones(x.shape,bool)
        for raw in [np.full(x.shape,128,np.uint8),np.clip(x/2,0,255).astype(np.uint8),np.where(x>256,190,60).astype(np.uint8),
                    np.random.default_rng(908).integers(0,256,x.shape,dtype=np.uint8)]:
            self.assertIsNone(observer.observe(raw,mask,mask)[0])

    def test_external_ridges_cannot_supply_raw_periodicity_inside_uniform_permission(self):
        raw=self.signal();permission=np.zeros(raw.shape,bool);permission[120:392,120:392]=True;raw[permission]=128
        self.assertIsNone(observer.observe(raw,permission,permission)[0])

    def test_two_references_are_required_and_must_agree(self):
        mask=np.ones((512,512),bool);raw=self.signal()
        with patch.object(observer,'measure',side_effect=[dict(pitch=10),dict(pitch=None)]):
            self.assertIsNone(observer.observe(raw,mask,mask)[0])
        with patch.object(observer,'measure',side_effect=[dict(pitch=10),dict(pitch=14)]):
            self.assertEqual(observer.observe(raw,mask,mask)[1]['status'],'reference_disagreement')

    def test_input_and_permission_contracts_reject_before_sampling(self):
        raw=self.signal();mask=np.ones(raw.shape,bool)
        for image in [raw.astype(np.float32),raw[:100],np.repeat(raw[:,:,None],3,2)]:
            with self.assertRaises(ValueError):observer.observe(image,mask,mask)
        with self.assertRaisesRegex(ValueError,'outside_permission'):observer.observe(raw,mask,~mask)
        with self.assertRaisesRegex(ValueError,'reference_sigma'):observer.measure(raw,mask,mask,1.)

    def test_original_window_units_and_permission_roundtrip(self):
        raw=self.signal();rgb=np.repeat(cv2.resize(raw,(256,256),interpolation=cv2.INTER_AREA)[:,:,None],3,2)
        permission=np.ones((256,256),bool)
        with patch('fingerprint_poc_core.prepare_fingerprint',return_value=({'roi':np.ones((512,512),bool)},None,None)):
            pitch,report,_=observer.observed_component_pitch(rgb,[0,0,256,256],permission)
        self.assertIsNotNone(pitch);self.assertLess(abs(pitch-6),.15)
        self.assertFalse(report['frozen_gate_equivalence']);self.assertFalse(report['numeric_thresholds_relaxed'])
        for bad in [[True,0,256,256],[0.,0,256,256],[0,0,256,200]]:
            with self.assertRaisesRegex(ValueError,'square_contract'):observer.observed_component_pitch(rgb,bad,permission)

class LegacyPreferenceTests(unittest.TestCase):
    def args(self):
        rgb=np.full((100,100,3),120,np.uint8);mask=np.ones((100,100),bool)
        return rgb,rgb[:,:,0],mask,mask,1,'sha',{},{}

    def test_complete_legacy_acceptance_retains_original_artifact_and_renderer(self):
        original=({'valid':True},{'observed_pitch_working':8.},{},object())
        with patch.object(pipeline.legacy,'prepare_scoped_region',return_value=original),patch.object(pipeline,'prepare_body_scale') as new:
            result=pipeline.prepare_scoped_region(*self.args())
        self.assertIs(result,original);new.assert_not_called()

    def test_non_pitch_failure_is_never_retried(self):
        for reason in ['original_width_unavailable','adapter_memory_limit_exceeded','component_local_seed_unavailable']:
            original=(None,{'reject_reason':reason},{},None)
            with patch.object(pipeline.legacy,'prepare_scoped_region',return_value=original),patch.object(pipeline,'prepare_body_scale') as new:
                self.assertIs(pipeline.prepare_scoped_region(*self.args()),original)
            new.assert_not_called()

    def test_feature_gate_failure_cannot_trigger_new_observation_or_renderer_retry(self):
        def render(axis):return 'unchanged',dict(reason='insufficient_features')
        original=({'valid':True},{'reject_reason':None},{},render)
        with patch.object(pipeline.legacy,'prepare_scoped_region',return_value=original),patch.object(pipeline,'prepare_body_scale') as new:
            result=pipeline.prepare_scoped_region(*self.args());self.assertEqual(result[3]([1,0])[1]['reason'],'insufficient_features')
        new.assert_not_called()

    def test_only_exhausted_legacy_pitch_failure_reaches_fallback(self):
        old=(None,dict(reject_reason='component_local_pitch_unobserved',observation_seed_attempts=[{'old':True}]),{},None)
        with patch.object(pipeline.legacy,'prepare_scoped_region',return_value=old),patch.object(pipeline,'prepare_body_scale',return_value=(None,{'reject_reason':'component_local_pitch_unobserved'},{},None)) as new:
            result=pipeline.prepare_scoped_region(*self.args())
        self.assertEqual(new.call_args.kwargs['_preparer'],pipeline.prepare_local)
        self.assertEqual(result[1]['legacy_V10_pitch_attempts'],[{'old':True}]);self.assertTrue(result[1]['orientation_filtered_fallback_attempted'])

class RendererBindingTests(unittest.TestCase):
    def scoped(self):
        rgb=np.full((100,100,3),120,np.uint8);mask=np.zeros((100,100),bool);mask[30:70,30:70]=True
        artifact=dict(working_shape=[100,100],working_scale=1.,exif_orientation=1,body=np.ones_like(mask),coarse_mask=mask,
            regions=[dict(working_seed=[30,30,70,70],working_scope=[20,20,80,80],padding=dict(bottom=0,right=0),pitch_measurement={'scope':'local'})])
        geometry=dict(scope=dict(bbox_encoded_original=[0,0,100,100]),observed_pitch_working=8.)
        old=(None,dict(reject_reason='component_local_pitch_unobserved'),{},None)
        with patch.object(pipeline.legacy,'prepare_scoped_region',return_value=old),patch.object(pipeline,'prepare_body_scale',return_value=(artifact,geometry,{},None)):
            result=pipeline.prepare_scoped_region(rgb,rgb[:,:,0],mask,mask,1,'sha',{}, {})
        return rgb,mask,result[3]

    def test_renderer_exception_restores_frozen_alias(self):
        import transform_automatic_fingerprint_poc_v4 as frozen
        rgb,mask,render=self.scoped();before=frozen.observed_seed_pitch
        def observe(image,box,permission):
            np.testing.assert_array_equal(permission,mask);return 8.,{'scope':'local'},None
        def fail(image,*args):
            frozen.observed_seed_pitch(image,[30,30,70,70]);raise RuntimeError('injected renderer failure')
        with patch.object(pipeline,'observed_component_pitch',side_effect=observe),patch.object(pipeline,'render',side_effect=fail):
            with self.assertRaisesRegex(RuntimeError,'injected'):render([1.,0.])
        self.assertIs(frozen.observed_seed_pitch,before)

    def test_renderer_requires_same_raw_frame_and_observation_window(self):
        import transform_automatic_fingerprint_poc_v4 as frozen
        rgb,mask,render=self.scoped()
        for change in ['frame','box']:
            def fail(image,*args):
                frame=image.copy();box=[30,30,70,70]
                if change=='frame':frame[0,0,0]+=1
                else:box=[31,30,71,70]
                frozen.observed_seed_pitch(frame,box);return frame,{}
            with patch.object(pipeline,'render',side_effect=fail),patch.object(pipeline,'observed_component_pitch') as observe:
                with self.assertRaisesRegex(ValueError,'scope_mismatch'):render([1.,0.])
            observe.assert_not_called()

    def test_observer_cannot_be_bypassed_or_change_preflight_measurements(self):
        import transform_automatic_fingerprint_poc_v4 as frozen
        rgb,mask,render=self.scoped()
        with patch.object(pipeline,'render',return_value=(rgb.copy(),{})):
            with self.assertRaisesRegex(ValueError,'not_called'):render([1.,0.])
        def call(image,*args):frozen.observed_seed_pitch(image,[30,30,70,70]);return image.copy(),{}
        for observation in [(9.,{'scope':'local'},None),(8.,{'scope':'changed'},None)]:
            with patch.object(pipeline,'render',side_effect=call),patch.object(pipeline,'observed_component_pitch',return_value=observation):
                with self.assertRaisesRegex(ValueError,'remeasurement_mismatch'):render([1.,0.])

    def test_returned_RGB_changes_only_its_component_and_source_is_preserved(self):
        import transform_automatic_fingerprint_poc_v4 as frozen
        rgb,mask,render=self.scoped();original=rgb.copy();before=frozen.observed_seed_pitch
        def call(image,*args):frozen.observed_seed_pitch(image,[30,30,70,70]);return np.full_like(image,220),{}
        with patch.object(pipeline,'render',side_effect=call),patch.object(pipeline,'observed_component_pitch',return_value=(8.,{'scope':'local'},None)):
            returned,report=render([1.,0.])
        np.testing.assert_array_equal(rgb,original);np.testing.assert_array_equal(returned[~mask],original[~mask])
        self.assertTrue(np.all(returned[mask]==220));self.assertIs(frozen.observed_seed_pitch,before)
        self.assertFalse(report['frozen_gate_equivalence'])

if __name__=='__main__':unittest.main()
