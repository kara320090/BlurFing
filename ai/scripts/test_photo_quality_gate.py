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
if __name__=='__main__':unittest.main()
