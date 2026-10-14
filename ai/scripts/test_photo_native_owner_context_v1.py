import unittest
import numpy as np
from test_photo_owner_observation_v1 import context
from photo_native_owner_context_v1 import restore_contexts
from photo_owner_partition_v1 import partition


class NativeOwnerTests(unittest.TestCase):
    def test_single_owner_recovers_only_original_native_body_pixels(self):
        body=np.zeros((80,80),bool);body[10:70,20:60]=True;old=body.copy();old[10:12]=False
        row=context(old);result=restore_contexts([row],body)
        np.testing.assert_array_equal(result[0]['body'],body);np.testing.assert_array_equal(row['body'],old)
        self.assertEqual(result[0]['native_body_edge_pixels_restored'],80)
        mask=np.zeros_like(body);mask[10:30,30:50]=True
        grouped=partition(mask,result);self.assertEqual(len(grouped['records']),1)
        self.assertIsNone(grouped['records'][0]['reason']);np.testing.assert_array_equal(grouped['labels']>0,mask)

    def test_two_watershed_owners_remain_ambiguous_at_unobserved_seam(self):
        body=np.zeros((40,60),bool);body[5:35,5:55]=True;left=body.copy();left[:,30:]=False
        right=body.copy();right[:,:31]=False;rows=[context(left),context(right,2)]
        result=restore_contexts(rows,body)
        for before,after in zip(rows,result):self.assertIs(before,after)
        self.assertFalse(any(r['body'][:,30].any() for r in result))

    def test_merge_split_missing_and_invalid_contexts_are_not_assigned(self):
        body=np.zeros((60,80),bool);body[10:30,10:30]=True;body[10:30,50:70]=True
        both=context(body);self.assertIs(restore_contexts([both],body)[0],both)
        invalid=context(body,reason='axis_unavailable');self.assertIs(restore_contexts([invalid],body)[0],invalid)
        self.assertEqual(restore_contexts([],body),[])
        outside=np.ones_like(body)
        with self.assertRaisesRegex(ValueError,'subset'):restore_contexts([context(outside)],body)

    def test_many_native_fragments_still_count_multi_body_owner_conflicts(self):
        y,x=np.indices((200,200));body=(y%2==0)&(x%2==0)
        merged=context(body);single=np.zeros_like(body);single[20,20]=True;row=context(single,2)
        result=restore_contexts([merged,row],body)
        self.assertIs(result[0],merged);self.assertIs(result[1],row)
        with self.assertRaisesRegex(ValueError,'context_contract'):restore_contexts([row]*257,body)


if __name__=='__main__':unittest.main()
