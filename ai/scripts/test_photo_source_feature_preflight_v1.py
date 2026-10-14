import unittest
from unittest.mock import patch
import numpy as np
import photo_source_feature_preflight_v1 as source
import photo_learned_pad_pipeline_v6 as pipeline


class OriginalFeatureTests(unittest.TestCase):
    def test_availability_matches_frozen_predicate_and_never_checks_generated_RGB(self):
        rgb=np.full((200,200,3),120,np.uint8);before=rgb.copy()
        for count in [0,5,10,20]:
            template=dict(width=128,height=128,positionsX=list(range(count)),positionsY=list(range(count)),types=['E']*count)
            result=dict(images=[dict(key='Original',status='ok' if count else 'no_minutiae',template=template)])
            with patch.object(source,'run_matcher_job',return_value=result) as extractor:
                measured=source.observe(rgb,[50,50,150,150],dict(status='estimated',width=400.))
            self.assertEqual(measured['eligible'],count>=10);self.assertEqual(measured['before_feature_count'],count)
            self.assertEqual(extractor.call_args.args[1],[]);self.assertFalse(measured['generated_features_inspected'])
            np.testing.assert_array_equal(rgb,before)

    def test_bad_extractor_and_template_are_errors_not_empty_success(self):
        rgb=np.full((200,200,3),120,np.uint8)
        for result in [dict(images=[]),dict(images=[dict(key='Original',status='failed')]),
            dict(images=[dict(key='Original',status='ok',template=dict(width=128,height=128,positionsX=[0],positionsY=[],types=[]))])]:
            with patch.object(source,'run_matcher_job',return_value=result):
                with self.assertRaises(RuntimeError):source.observe(rgb,[50,50,150,150],dict(status='estimated',width=400.))


class SourceSelectionTests(unittest.TestCase):
    def test_first_available_original_seed_selected_without_render_search(self):
        rgb=np.full((400,400,3),120,np.uint8);mask=np.ones((400,400),bool)
        proposals=[dict(box=[20,20,120,120],side=100),dict(box=[150,150,250,250],side=100),dict(box=[260,260,360,360],side=100)]
        seen=[]
        def available(frame,box,width):
            seen.append(box);return dict(eligible=len(seen)==2,reason=None if len(seen)==2 else 'insufficient_features')
        def prepare(*args,**kwargs):
            chosen=kwargs['_proposals'](mask,mask,None,None,None,None)
            self.assertEqual(chosen[0]['box'],proposals[1]['box'])
            return dict(regions=[]),dict(reject_reason=None)
        with (patch.object(pipeline,'seeds',return_value=proposals),
              patch.object(pipeline,'estimate_finger_width_body',return_value=dict(status='estimated',width=400.)),
              patch.object(pipeline.shared,'observed_seed_pitch',return_value=(8.,{},None)),
              patch.object(pipeline,'observe_original_features',side_effect=available),
              patch.object(pipeline,'prepare_observed_region',side_effect=prepare)):
            artifact,geometry=pipeline.prepare_region(rgb,np.zeros((400,400),np.uint8),mask,mask,1,'0'*64,
                dict(working_scale=1.,component=1),dict(axis_native_yx=[1.,0.]))
        self.assertEqual(len(seen),2);self.assertTrue(artifact);self.assertFalse(geometry['seed_selection_uses_generated_features'])


if __name__=='__main__':unittest.main()
