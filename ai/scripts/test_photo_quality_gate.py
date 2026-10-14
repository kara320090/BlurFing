import unittest,json
from photo_quality_gate import state,summarize,pitch_failure_reason
class GateTests(unittest.TestCase):
    def region(self,value):return dict(region_id=1,quality_status=value)
    def test_success(self):self.assertEqual(summarize([self.region('TRANSFORMED')])['status'],'success')
    def test_partial(self):
        r=summarize([self.region('TRANSFORMED'),self.region('REJECT_PITCH_UNOBSERVED')]);self.assertEqual(r['status'],'partial_success');self.assertEqual(r['fingerprints_rejected'],1)
    def test_all_rejected(self):self.assertEqual(summarize([self.region('REJECT_WIDTH_UNAVAILABLE')])['status'],'rejected')
    def test_empty(self):self.assertEqual(summarize([])['status'],'rejected')
    def test_reasons(self):
        for reason,expected in [('pitch_unobserved','REJECT_PITCH_UNOBSERVED'),('cue_disagreement','REJECT_PITCH_UNSTABLE'),('original_width_unavailable','REJECT_WIDTH_UNAVAILABLE'),('insufficient_features','REJECT_INSUFFICIENT_FEATURES'),('renderer_pitch_out_of_range','REJECT_RENDERER_CONTRACT')]:self.assertEqual(state(reason),expected)
    def test_unstable_existing_evidence(self):
        self.assertEqual(pitch_failure_reason({'attempts':[{'measurement':{'status':'scale_disagreement'}}]}),'pitch_unstable')
        self.assertEqual(pitch_failure_reason({'attempts':[{'measurement':{'status':'unavailable','scales':[{'status':'inconsistent'}]}}]}),'pitch_unstable')
        self.assertEqual(pitch_failure_reason({'attempts':[{'measurement':{'count':0}}]}),'pitch_unobserved')
    def test_deterministic_JSON(self):
        a=summarize([self.region('TRANSFORMED'),self.region('REJECT_INSUFFICIENT_FEATURES')]);self.assertEqual(json.dumps(a,sort_keys=True),json.dumps(summarize([self.region('TRANSFORMED'),self.region('REJECT_INSUFFICIENT_FEATURES')]),sort_keys=True))
    def test_actual_two_scale_producer_schema(self):
        from unittest.mock import patch
        import numpy as np
        from diagnose_ridge_measurement_noise import two_scale_measurement
        patches=[dict(pitch=p,correlation=.9,coherence=.9,profile_contrast=10) for p in [6,8,20,22]]
        with patch('diagnose_ridge_measurement_noise.estimate_ridge_pitch',return_value=dict(status='estimated',pitch=12,count=4,measurements=patches)):
            measurement=two_scale_measurement(np.zeros((512,512),np.uint8),np.ones((512,512),bool))
        self.assertEqual(measurement['scales'][0]['selection']['status'],'inconsistent')
        self.assertEqual(pitch_failure_reason(dict(attempts=[dict(measurement=measurement)])),'pitch_unstable')
    def test_insufficient_nested_patches_remain_unobserved(self):
        self.assertEqual(pitch_failure_reason(dict(attempts=[dict(measurement=dict(status='unavailable',scales=[dict(selection=dict(status='insufficient'))]))])),'pitch_unobserved')
if __name__=='__main__':unittest.main()
