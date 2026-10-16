"""Native permission survives even when its working observation raster is empty."""
import unittest
from unittest.mock import Mock
import numpy as np
import photo_body_observation_seed_v1 as observer
import photo_learned_pad_pipeline_v10 as component_observer


class EmptyWorkingPermissionTests(unittest.TestCase):
    def fixture(self, orientation=1, survive=False):
        upright=np.zeros((32,40),bool)
        if survive:upright[2,2]=True
        else:upright[1,1]=upright[1,3]=upright[3,1]=True
        native=observer.shared.orient(upright,orientation,inverse=True).copy()
        rgb=np.full((*native.shape,3),127,np.uint8);gray=np.full(native.shape,127,np.uint8)
        return (rgb,gray,native,np.ones_like(native),orientation,'a'*64,
                dict(working_scale=.5,component=1),dict(axis_native_yx=[1.,0.]))

    def test_valid_fragment_lost_by_resize_rejects_without_observation_or_input_mutation(self):
        for orientation in range(1,9):
            with self.subTest(orientation=orientation):
                args=self.fixture(orientation);before=[x.copy() for x in args[:4]]
                proposals=Mock(side_effect=AssertionError('empty raster must not enter proposal selection'))
                pitch=Mock(side_effect=AssertionError('missing pixels must not produce pitch'))
                artifact,geometry=observer.prepare_region(*args,_proposals=proposals,_pitch_observer=pitch)
                self.assertIsNone(artifact);self.assertEqual(geometry['reject_reason'],'body_supported_seed_unavailable')
                self.assertTrue(geometry['working_permission_empty_after_resize'])
                self.assertEqual(geometry['native_permission_pixels'],3);self.assertEqual(geometry['working_permission_pixels'],0)
                self.assertEqual(geometry['working_shape'],[16,20]);self.assertEqual(geometry['observation_seed_attempts'],[])
                proposals.assert_not_called();pitch.assert_not_called()
                for actual,old in zip(args[:4],before):np.testing.assert_array_equal(actual,old)

    def test_component_observer_maps_to_existing_quality_rejection(self):
        artifact,geometry=component_observer.prepare_local(*self.fixture())
        self.assertIsNone(artifact);self.assertEqual(geometry['reject_reason'],'component_local_seed_unavailable')
        self.assertEqual(geometry['native_permission_pixels'],3)

    def test_nonempty_working_permission_still_enters_existing_proposals(self):
        proposals=Mock(return_value=[])
        artifact,geometry=observer.prepare_region(*self.fixture(survive=True),_proposals=proposals)
        self.assertIsNone(artifact);proposals.assert_called_once()
        self.assertTrue(proposals.call_args.args[0].any())
        self.assertNotIn('working_permission_empty_after_resize',geometry)

    def test_invalid_native_masks_remain_contract_errors(self):
        for kind in ['empty','integer','outside_owner']:
            with self.subTest(kind=kind):
                args=list(self.fixture())
                if kind=='empty':args[2][:]=False
                elif kind=='integer':args[2]=args[2].astype(np.uint8)
                else:args[3][args[2]]=False
                with self.assertRaisesRegex(ValueError,'body_observation_mask_contract'):
                    observer.prepare_region(*args)


if __name__=='__main__':unittest.main()
