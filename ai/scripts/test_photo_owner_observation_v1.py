import unittest
import numpy as np
from photo_owner_partition_v1 import partition
from photo_body_observation_seed_v1 import seeds


def context(body,index=1,reason=None):
    parent=dict(mask=body.copy(),reject_reason=None,metadata_coordinate_system='working_image_pixels',
        working_scale=1.,major_axis_yx=[1.,0.],component=index,watershed_part=1)
    return dict(body=body,parent=parent,reject_reason=reason,estimator_region_index=index,candidate_id=f'body-{index:04d}-part-0001')


class OwnerObservationTests(unittest.TestCase):
    def test_disconnected_predictions_keep_one_owner_and_every_pixel(self):
        body=np.zeros((80,80),bool);body[5:75,5:75]=True;mask=np.zeros_like(body)
        mask[20:25,20:25]=True;mask[40:43,50:55]=True;mask[60,40]=True
        result=partition(mask,[context(body)])
        self.assertEqual(len(result['records']),1);np.testing.assert_array_equal(result['labels']>0,mask)
        self.assertEqual(result['records'][0]['plan']['mask_pixels'],int(mask.sum()))

    def test_crossing_prediction_uses_exact_body_territories_and_rejects_unowned(self):
        left=np.zeros((20,40),bool);left[:,1:18]=True;right=np.zeros_like(left);right[:,23:39]=True
        mask=np.zeros_like(left);mask[10,5:35]=True
        result=partition(mask,[context(left),context(right,2)])
        self.assertEqual(len(result['records']),3);np.testing.assert_array_equal(result['labels']>0,mask)
        self.assertEqual(result['records'][2]['reason'],'learned_body_owner_unavailable')
        self.assertTrue(np.all(result['labels'][mask&left]==1));self.assertTrue(np.all(result['labels'][mask&right]==2))

    def test_overlap_never_uses_first_last_or_largest_owner(self):
        body=np.ones((30,30),bool);mask=np.zeros_like(body);mask[10:20,10:20]=True
        result=partition(mask,[context(body),context(body,2)])
        self.assertEqual(len(result['records']),1);self.assertEqual(result['records'][0]['reason'],'learned_body_owner_ambiguous')
        self.assertIsNone(result['records'][0]['association'])

    def test_bad_axis_or_rejected_context_is_not_rescued_by_grouping(self):
        body=np.ones((20,20),bool);mask=np.zeros_like(body);mask[10,10]=True
        result=partition(mask,[context(body,reason='axis_unavailable')])
        self.assertIn('axis_unavailable',result['records'][0]['reason'])
        row=context(body);del row['parent']['major_axis_yx']
        result=partition(mask,[row]);self.assertIn('metadata_unavailable',result['records'][0]['reason'])

    def test_body_observation_can_exceed_permission_but_output_mask_is_unchanged(self):
        body=np.zeros((400,400),bool);body[30:370,100:300]=True;mask=np.zeros_like(body);mask[195:205,195:205]=True
        before=mask.copy();rows=seeds(mask,body)
        self.assertTrue(rows);self.assertGreater(rows[0]['side'],10)
        for row in rows:
            a,b,c,d=row['box'];self.assertTrue(body[b:d,a:c].all());y,x=row['center_yx'];self.assertTrue(mask[y,x])
        np.testing.assert_array_equal(mask,before)

    def test_observation_budget_and_repeatability_are_deterministic(self):
        body=np.zeros((500,500),bool);body[10:490,10:490]=True;mask=np.zeros_like(body)
        for y in range(100,401,50):
            for x in range(100,401,50):mask[y,x]=True
        first=seeds(mask,body);self.assertEqual(first,seeds(mask,body));self.assertLessEqual(len(first),8)
        self.assertTrue(all(row['fully_inside_observed_body'] for row in first))


if __name__=='__main__':unittest.main()
