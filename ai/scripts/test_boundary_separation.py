"""Synthetic separation and tile-policy regressions; no photos or GT input."""
import unittest
from unittest.mock import patch
import numpy as np
import automatic_boundary_v1 as detector
from evaluate_detector_ground_truth import component_matching

class BoundaryTests(unittest.TestCase):
    def test_shared_palm_does_not_merge_distal_runs(self):
        fg=np.zeros((160,150),bool);fg[10:120,20:50]=True;fg[10:120,80:110]=True;fg[120:150,20:110]=True
        mask,q=detector.isolate_seed_scanlines(fg,35,40,10,30)
        self.assertIsNotNone(mask);self.assertTrue(mask[40,35]);self.assertFalse(mask[:,80:110].any());self.assertFalse(mask[120:].any());self.assertEqual(q['reference_width'],30)
    def test_width_outliers_do_not_replace_median(self):
        fg=np.zeros((160,150),bool);fg[10:130,20:50]=True;fg[25:28,20:100]=True
        mask,q=detector.isolate_seed_scanlines(fg,35,40,10,30)
        self.assertEqual(q['reference_width'],30);self.assertFalse(mask[25:28].any())
    def test_background_span_rejected(self):
        mask,q=detector.isolate_seed_scanlines(np.ones((100,160),bool),80,30,10,20)
        self.assertIsNone(mask);self.assertEqual(q['reject_reason'],'finger_width_unstable')
    def test_legacy_success_is_returned_exactly(self):
        m=np.zeros((20,20),bool);m[2:10,4:12]=True;q={'legacy':True}
        with patch.object(detector,'_local_pad_pass',return_value=(m,q)) as f:
            out,quality=detector._local_pad(np.zeros((20,20,3),np.uint8),{})
            self.assertIs(out,m);self.assertIs(quality,q);f.assert_called_once()
    def test_tiles_cover_without_authorizing_overlap(self):
        mask=np.zeros((400,300),bool);mask[20:380,40:260]=True
        plan=detector.square_tile_plan(mask);self.assertEqual(plan['uncovered_pixels'],0)
        self.assertEqual(len(plan['scopes']),2);self.assertEqual(plan['status'],'geometry_only_not_transform_approved');self.assertTrue(plan['internal_seam_validation_required'])
    def test_components_match_one_to_one(self):
        gt=np.zeros((20,40),bool);gt[2:10,2:10]=True;gt[2:10,25:33]=True
        pred=gt.copy();result=component_matching(pred,gt)
        self.assertEqual(result['matched_nonzero_overlap'],2);self.assertTrue(all(r['metrics']['iou']==1 for r in result['components']))
    def test_one_prediction_cannot_claim_two_fingers(self):
        gt=np.zeros((20,40),bool);gt[2:10,2:10]=True;gt[2:10,25:33]=True
        pred=gt.copy();pred[5,2:33]=True
        self.assertEqual(component_matching(pred,gt)['matched_nonzero_overlap'],1)

if __name__=='__main__':unittest.main()
