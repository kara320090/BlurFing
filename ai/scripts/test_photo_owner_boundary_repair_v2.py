import copy,unittest
import numpy as np
from photo_owner_boundary_repair_v2 import repair_contexts
from test_photo_owner_observation_v1 import context


class BoundaryRepairTests(unittest.TestCase):
    def setup_masks(self):
        body=np.zeros((17,25),bool);body[2:15,2:23]=True
        owner=body.copy();owner[2:4,5:12]=False
        permission=np.zeros_like(body);permission[2:9,5:12]=True
        return body,owner,permission

    def test_one_adjacent_owner_links_only_prediction_gap_and_preserves_inputs(self):
        body,owner,mask=self.setup_masks();row=context(owner);before=owner.copy();pred=mask.copy()
        result,audit=repair_contexts([row],body,mask)
        np.testing.assert_array_equal(result[0]['body'],owner|(mask&~owner))
        np.testing.assert_array_equal(row['body'],before);np.testing.assert_array_equal(mask,pred)
        self.assertEqual(audit['restored_pixels'],14);self.assertEqual(audit['unassigned_after'],0)
        self.assertFalse(audit['anatomical_owner_verified'])

    def test_two_owners_adjacent_to_gap_stay_unassigned_in_either_order(self):
        body=np.ones((17,25),bool);left=body.copy();left[:,12:]=False
        right=body.copy();right[:,:13]=False;mask=body.copy()
        for rows in [[context(left),context(right,2)],[context(right,2),context(left)]]:
            result,audit=repair_contexts(rows,body,mask)
            self.assertEqual(audit['restored_pixels'],0)
            self.assertEqual(audit['pieces'][0]['reason'],'adjacent_owner_ambiguous')
            for a,b in zip(rows,result):self.assertIs(a,b)

    def test_invalid_owner_and_overlapping_neighbor_never_supply_authority(self):
        body,owner,mask=self.setup_masks()
        _,report=repair_contexts([context(owner,reason='invalid_axis')],body,mask)
        self.assertEqual(report['restored_pixels'],0)
        _,report=repair_contexts([context(owner),context(owner,2)],body,mask)
        self.assertEqual(report['restored_pixels'],0)

    def test_no_owned_permission_contact_is_not_enough(self):
        body,owner,mask=self.setup_masks();mask[4:]=False
        _,audit=repair_contexts([context(owner)],body,mask)
        self.assertEqual(audit['restored_pixels'],0)
        self.assertEqual(audit['pieces'][0]['reason'],'no_adjacent_owned_permission')

    def test_isolated_gap_stays_unassigned(self):
        body=np.ones((17,25),bool);owner=np.zeros_like(body);owner[2:5,2:5]=True
        mask=owner.copy();mask[10:12,15:17]=True
        _,audit=repair_contexts([context(owner)],body,mask)
        self.assertEqual(audit['restored_pixels'],0)

    def test_integer_rotations_reflections_and_context_permutation_are_equivariant(self):
        body,owner,mask=self.setup_masks();extra=np.zeros_like(body);extra[10:14,18:22]=True
        owner&=~extra;rows=[context(owner),context(extra,2)]
        expected,_=repair_contexts(rows,body,mask)
        for k in range(4):
            for flip in [False,True]:
                def turn(x):
                    y=np.rot90(x,k);return np.fliplr(y).copy() if flip else y.copy()
                moved=[r|dict(body=turn(r['body'])) for r in rows[::-1]]
                result,_=repair_contexts(moved,turn(body),turn(mask))
                byid={r['candidate_id']:r['body'] for r in result}
                for r in expected:np.testing.assert_array_equal(byid[r['candidate_id']],turn(r['body']))

    def test_resource_limit_never_drops_or_assigns_unowned_pieces(self):
        body=np.ones((50,50),bool);mask=np.zeros_like(body);mask[::2,::2]=True
        result,audit=repair_contexts([],body,mask)
        self.assertEqual(result,[]);self.assertEqual(audit['reason'],'boundary_gap_resource_limit')
        self.assertEqual(audit['restored_pixels'],0);self.assertEqual(audit['unassigned_after'],625)

    def test_shape_dtype_subset_duplicate_contracts(self):
        body,owner,mask=self.setup_masks()
        for b,m in [(body.astype(np.uint8),mask),(body,mask.astype(float)),(body,mask[:2])]:
            with self.assertRaises(ValueError):repair_contexts([],b,m)
        outside=mask.copy();outside[0,0]=True
        with self.assertRaises(ValueError):repair_contexts([],body,outside)
        row=context(owner)
        with self.assertRaises(ValueError):repair_contexts([row,row],body,mask)


if __name__=='__main__':unittest.main()
