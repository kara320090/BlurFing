import copy
import unittest
import numpy as np
from pad_refinement_data_contract_v2 import COORDINATES
from pad_refinement_experiment_plan_v2 import POLICY, POLICY_SHA256, plan_crops, group_splits


class CoverageTests(unittest.TestCase):
    def source(self,h,w):return dict(height=h,width=w,coordinate_system=COORDINATES,source_sha256='a'*64)

    def test_edges_noise_and_empty_coarse_all_accounted_for(self):
        body=np.zeros((1011,1203),bool);body[17:999,9:1188]=True;body[0,0]=body[-1,-1]=True
        plan=plan_crops(self.source(*body.shape),body,np.zeros_like(body))
        self.assertEqual(plan['status'],'planned');self.assertEqual(plan['uncovered_native_body_pixels'],0)
        self.assertEqual(plan['native_body_components'],3)
        self.assertEqual(plan,plan_crops(self.source(*body.shape),body,np.zeros_like(body)))
        self.assertEqual(plan['policy_sha256'],POLICY_SHA256)
        for a,b,c,d in plan['boxes']:
            self.assertTrue(0<=a<c<=1203 and 0<=b<d<=1011)
            self.assertLessEqual(max(c-a,d-b),POLICY['native_side'])

    def test_resource_reject_cannot_return_partial_plan(self):
        body=np.zeros((35,35),bool);body[::2,::2]=True
        plan=plan_crops(self.source(*body.shape),body,body.copy())
        self.assertEqual(plan['status'],'rejected');self.assertEqual(plan['boxes'],[])
        self.assertFalse(plan['coverage_verified'])

    def test_frozen_policy_and_GT_free_signature(self):
        with self.assertRaises(TypeError):POLICY['stride']=1
        body=np.ones((6,8),bool)
        with self.assertRaisesRegex(ValueError,'GT_fields'):
            plan_crops(dict(self.source(6,8),GT_folder='unused'),body,body)

    def test_mask_shape_dtype_and_permission_contract(self):
        body=np.zeros((6,8),bool)
        for coarse in [np.zeros((1,8),bool),body.astype(np.uint8),np.ones_like(body)]:
            with self.assertRaises(ValueError):plan_crops(self.source(6,8),body,coarse)
        plan=plan_crops(self.source(6,8),body,body)
        self.assertEqual(plan['status'],'empty');self.assertEqual(plan['boxes'],[])


class GroupTests(unittest.TestCase):
    def setUp(self):
        self.rows=[dict(source_id=f'SRC-{i}',source_sha256=f'{i:064x}',
                        encoded_RGB_sha256=f'{i+10:064x}',upright_RGB_sha256=f'{i+20:064x}') for i in range(1,5)]
        self.groups={r['source_id']:'group-A' if i<3 else 'group-B' for i,r in enumerate(self.rows)}

    def test_two_groups_development_folds_3_1_not_independent_test(self):
        plan=group_splits(self.rows,self.groups,[])
        self.assertEqual(plan['group_count'],2);self.assertFalse(plan['independent_final_test'])
        for fold in plan['folds']:
            self.assertFalse(set(fold['train'])&set(fold['validation']))
            self.assertNotIn(fold['validation_group'],fold['train_groups'])
        self.assertEqual([len(f['validation']) for f in plan['folds']],[3,1])

    def test_metadata_only_copy_or_reserved_test_rejected(self):
        rows=copy.deepcopy(self.rows);rows[-1]['upright_RGB_sha256']=rows[0]['upright_RGB_sha256']
        with self.assertRaisesRegex(ValueError,'decoded_pixels'):group_splits(rows,self.groups,[])
        with self.assertRaisesRegex(ValueError,'reserved_test'):group_splits(self.rows,self.groups,[self.rows[0]['source_sha256']])

    def test_cross_orientation_duplicate_and_padded_groups_rejected(self):
        rows=copy.deepcopy(self.rows)
        rows[-1]['encoded_RGB_sha256']=rows[0]['upright_RGB_sha256']
        rows[-1]['upright_RGB_sha256']=rows[0]['encoded_RGB_sha256']
        with self.assertRaisesRegex(ValueError,'decoded_pixels'):group_splits(rows,self.groups,[])
        groups=self.groups.copy();groups['SRC-4']='group-A '
        with self.assertRaisesRegex(ValueError,'provenance'):group_splits(self.rows,groups,[])

    def test_unknown_group_or_unverified_identity_rejected(self):
        groups=self.groups.copy();groups.pop('SRC-1')
        with self.assertRaisesRegex(ValueError,'provenance'):group_splits(self.rows,groups,[])
        rows=copy.deepcopy(self.rows);rows[0].pop('encoded_RGB_sha256')
        with self.assertRaisesRegex(ValueError,'hashes_required'):group_splits(rows,self.groups,[])


if __name__=='__main__':unittest.main()
