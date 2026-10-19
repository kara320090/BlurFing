import copy
import unittest
from photo_visibility_data_readiness_v1 import audit,DEVELOPMENT,HISTORICAL


def fixture():
    sources=[];records=[]
    for i,(group,label) in enumerate([('A','not_observed'),('A','visible'),('B','visible'),('C','visible')]):
        s=dict(source_id=str(i),source_sha256=f'file{i}',upright_RGB_sha256=f'rgb{i}',mask_sha256=f'mask{i}',split_role=DEVELOPMENT,acquisition_group=group)
        sources.append(s);records.append(dict(**s,human_GT=True,status='reviewed',groups=[dict(component_ids=[1],label=label)]))
    return dict(records=records),dict(sources=sources)


class DataReadinessTests(unittest.TestCase):
    def test_one_negative_capture_cannot_supply_three_roles(self):
        labels,roster=fixture();r=audit(labels,roster)
        self.assertFalse(r['necessary_three_role_class_group_coverage_met'])
        self.assertEqual(r['additional_negative_capture_groups_needed_for_necessary_condition'],2)
        self.assertFalse(r['leave_one_capture_group_out'][0]['both_classes_in_train'])

    def test_uncertain_is_never_silently_negative(self):
        labels,roster=fixture();labels['records'][0]['groups'][0]['label']='uncertain'
        r=audit(labels,roster);self.assertEqual(r['development']['not_observed']['regions'],0)
        self.assertEqual(r['development']['uncertain']['regions'],1)

    def test_historical_and_unknown_groups_do_not_rescue_readiness(self):
        labels,roster=fixture()
        for obj in (labels['records'][0],roster['sources'][0]):obj['split_role']=HISTORICAL
        for obj in (labels['records'][1],roster['sources'][1]):obj['acquisition_group']=None
        r=audit(labels,roster)
        self.assertEqual(r['historical_photos_excluded_from_training'],1)
        self.assertEqual(r['development']['not_observed']['regions'],0)
        self.assertIn('capture_group_unknown',r['blockers'])

    def test_duplicate_pixels_source_binding_and_unreviewed_rejected(self):
        labels,roster=fixture()
        dup=copy.deepcopy(roster);dup['sources'][1]['upright_RGB_sha256']=dup['sources'][0]['upright_RGB_sha256']
        with self.assertRaises(ValueError):audit(labels,dup)
        wrong=copy.deepcopy(labels);wrong['records'][0]['mask_sha256']='changed'
        with self.assertRaises(ValueError):audit(wrong,roster)
        wrong=copy.deepcopy(labels);wrong['records'][0]['human_GT']=False
        with self.assertRaises(ValueError):audit(wrong,roster)

    def test_necessary_coverage_does_not_claim_independent_performance(self):
        labels,roster=fixture()
        for r in labels['records'][2:]:r['groups'].append(dict(component_ids=[2],label='not_observed'))
        r=audit(labels,roster)
        self.assertTrue(r['necessary_three_role_class_group_coverage_met'])
        self.assertFalse(r['independent_validation_established'])
        self.assertFalse(r['automatic_training_performed'])


if __name__=='__main__':unittest.main()
