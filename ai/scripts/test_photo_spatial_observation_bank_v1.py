import unittest
import numpy as np
from photo_body_observation_seed_v1 import seeds,MAX_SEEDS
from photo_spatial_observation_bank_v1 import observation_seeds


class SpatialObservationTests(unittest.TestCase):
    def test_contiguous_prediction_gets_spatial_coverage_with_original_seed_first(self):
        body=np.zeros((900,500),bool);body[20:880,50:450]=True
        mask=np.zeros_like(body);mask[50:850,80:420]=True;before=mask.copy();old=seeds(mask,body)
        rows=observation_seeds(mask,body);self.assertGreater(len(rows),len(old));self.assertLessEqual(len(rows),MAX_SEEDS)
        self.assertEqual(rows[:len(old)],old)
        for row in rows:
            y,x=row['center_yx'];self.assertTrue(mask[y,x]);a,b,c,d=row['box'];self.assertTrue(body[b:d,a:c].all())
        for earlier,later in zip(rows,rows[1:]):self.assertNotEqual(earlier['center_yx'],later['center_yx'])
        self.assertEqual(rows,observation_seeds(mask,body));np.testing.assert_array_equal(mask,before)

    def test_fixed_budget_and_disconnected_permission_pixels_are_all_preserved(self):
        body=np.zeros((900,900),bool);body[10:890,10:890]=True;mask=np.zeros_like(body)
        for y in range(100,801,100):
            for x in range(100,801,100):mask[y,x]=True
        before=mask.copy();rows=observation_seeds(mask,body);self.assertEqual(len(rows),MAX_SEEDS)
        np.testing.assert_array_equal(mask,before)

    def test_no_default_seed_or_body_evidence_is_invented(self):
        mask=np.zeros((100,100),bool);mask[50,50]=True
        with self.assertRaises(ValueError):observation_seeds(mask,np.zeros_like(mask))
        body=np.zeros_like(mask);body[10:90,45:55]=True
        self.assertEqual(observation_seeds(mask,body),seeds(mask,body))


if __name__=='__main__':unittest.main()
