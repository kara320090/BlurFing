import unittest,hashlib
import numpy as np
from external_ridge_pitch_observer import observe

class EvidenceTests(unittest.TestCase):
    def setUp(self):
        y,x=np.indices((512,512));self.image=(128+60*np.sin(2*np.pi*x/8)).astype(np.uint8);self.mask=np.ones((512,512),bool);self.sha='0'*64;self.e=observe(self.image,self.mask,self.sha)
    def validate(self,e=None,**kw):
        args=dict(source_sha=self.sha,mask_sha=hashlib.sha256(self.mask.tobytes()).hexdigest(),shape=self.mask.shape,coordinate_space='native_source_pixels',image_scale=1.);args.update(kw);return (e or self.e).validate(**args)
    def test_synthetic_observed_schema(self):self.assertEqual(self.e.evidence_status,'accepted');self.assertAlmostEqual(self.validate()['pitch_native'],8,delta=.2)
    def test_missing_patch_evidence(self):
        self.e.cue_results['patches']=[];self.e.seal()
        with self.assertRaises(ValueError):self.validate()
    def test_source_mismatch(self):
        with self.assertRaises(ValueError):self.validate(source_sha='1'*64)
    def test_observed_pixel_mismatch(self):
        with self.assertRaises(ValueError):self.validate(observed_image_pixel_sha256='1'*64)
    def test_spread_reject(self):
        self.e.agreement_result['relative_IQR']=.5;self.e.seal()
        with self.assertRaises(ValueError):self.validate()
    def test_space_mismatch(self):
        with self.assertRaises(ValueError):self.validate(coordinate_space='normalized_working_pixels')
    def test_mask_mismatch(self):
        with self.assertRaises(ValueError):self.validate(mask_sha='1'*64)
    def test_cue_disagreement(self):
        self.e.cue_results['fft']['pitch']=20;self.e.seal()
        with self.assertRaises(ValueError):self.validate()
    def test_insufficient_patches(self):
        self.e.accepted_patch_count=2;self.e.seal()
        with self.assertRaises(ValueError):self.validate()
    def test_no_silent_clamp(self):
        self.e.pitch_value=51;self.e.seal()
        with self.assertRaises(ValueError):self.validate()
    def test_conversion_deterministic(self):
        self.e.coordinate_space='normalized_working_pixels';self.e.image_scale=.5;self.e.seal();a=self.validate(coordinate_space=self.e.coordinate_space,image_scale=.5);b=self.validate(coordinate_space=self.e.coordinate_space,image_scale=.5);self.assertEqual(a,b);self.assertAlmostEqual(a['pitch_native'],16,delta=.4);self.assertFalse(a['silent_clamp'])
    def test_no_frozen_observer_patch_or_gate_bypass(self):
        from unittest.mock import patch
        import whole_pad_skin_relief as renderer
        import transform_automatic_fingerprint_poc_v4 as frozen
        from photo_external_pitch_v1 import render
        old=(renderer.propose_visible_pad,frozen.observed_seed_pitch)
        rgb=np.repeat(self.image[:,:,None],3,axis=2)
        with patch('contactless_finger_width.estimate_finger_width',return_value={'status':'estimated','width':400}),patch('fingerprint_structure_check.check_structure_change',return_value={'structure_change_passed':False,'reason':'insufficient_features'}) as gate,patch('protect_visible_pad_checked_v2.observed_seed_pitch',side_effect=AssertionError('external path must not call internal observer')):
            out,audit=render(rgb,self.mask,[128,128,384,384],[0,0,512,512],self.e,self.sha)
            self.assertFalse(audit['applied']);self.assertEqual(audit['reject_reason'],'insufficient_features');gate.assert_called_once();np.testing.assert_array_equal(out,rgb)
        self.assertEqual(old,(renderer.propose_visible_pad,frozen.observed_seed_pitch))
    def test_nonperiodic_reject(self):self.assertNotEqual(observe(np.full((512,512),128,np.uint8),self.mask,self.sha).evidence_status,'accepted')
    def test_repeat_same_hash(self):self.assertEqual(self.e.evidence_hash,observe(self.image,self.mask,self.sha).evidence_hash)
if __name__=='__main__':unittest.main()
