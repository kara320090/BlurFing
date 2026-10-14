import unittest,tempfile,json,hashlib
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
import photo_coarse_adapter_v2 as adapter
class AdapterSafetyIntegration(unittest.TestCase):
    def test_incompatible_policy_rejected_before_masks_or_estimator(self):
        policy=dict(coordinate_system='encoded_original_pixels',body_classes=[1,2],tip_class=2,minimum_votes=2)
        bad=[{},None,policy|dict(coordinate_system='upright_pixels'),policy|dict(body_classes=[99]),policy|dict(body_classes=[True,2]),policy|dict(tip_class=1),policy|dict(minimum_votes=0),policy|dict(minimum_votes=2.0)]
        for identity in bad:
            with self.subTest(identity=identity),self.assertRaises(ValueError):adapter.validate_semantic_policy(identity)
        adapter.validate_semantic_policy(policy)
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder);source=p/'synthetic.png';Image.new('RGB',(32,32)).save(source)
            (p/'semantics.json').write_text(json.dumps(policy|dict(coordinate_system='wrong')))
            with patch.object(adapter,'read_binary',side_effect=AssertionError('mask loading must not run')):
                with self.assertRaisesRegex(ValueError,'semantic_coordinate_contract_mismatch'):adapter.adapt(source,p)
    def test_reject_before_resize_without_mask_change(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder);source=p/'synthetic.png';Image.fromarray(np.zeros((64,64,3),np.uint8)).save(source)
            (p/'semantics.json').write_text(json.dumps(dict(source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),image_height=64,image_width=64,body_sha256='unused',tip_sha256='unused',coordinate_system='encoded_original_pixels',body_classes=[1,2],tip_class=2,minimum_votes=2)))
            mask=np.zeros((64,64),bool);mask[10,10]=True;mask[20,20]=True
            with patch.object(adapter,'read_binary',side_effect=[mask.copy(),mask.copy()]),patch.object(adapter,'estimate',return_value=dict(mask=mask.copy())),patch.object(adapter.cv2,'resize',side_effect=AssertionError('resize must not run')):
                rgb,result=adapter.adapt(source,p)
            self.assertEqual(result['detected_pad_count'],2);self.assertIsNone(result['working_shape']);self.assertTrue(np.array_equal(mask,result['coarse_mask']))
            self.assertEqual([r['reject_reason'] for r in result['rejected']],['adapter_memory_limit_exceeded']*2)
            self.assertFalse(rgb.any())
    def test_invalid_policy_returns_original_with_explicit_failure(self):
        from protect_fingerprint import protect_image
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder);source=p/'synthetic.png';pixels=np.full((32,32,3),[160,100,80],np.uint8);Image.fromarray(pixels).save(source)
            (p/'semantics.json').write_text(json.dumps(dict(coordinate_system='wrong')))
            returned,result=protect_image(source,p/'output',photo_semantics=p)
            self.assertEqual(result['status'],'rejected');self.assertEqual(result['reject_reason'],'photo_runtime_or_contract_failure')
            self.assertEqual(result['error'],'ValueError');np.testing.assert_array_equal(returned,pixels)
if __name__=='__main__':unittest.main()
