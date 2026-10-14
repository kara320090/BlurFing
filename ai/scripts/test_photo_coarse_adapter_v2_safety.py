import unittest,tempfile,json,hashlib
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
import photo_coarse_adapter_v2 as adapter
class AdapterSafetyIntegration(unittest.TestCase):
    def test_reject_before_resize_without_mask_change(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder);source=p/'synthetic.png';Image.fromarray(np.zeros((64,64,3),np.uint8)).save(source)
            (p/'semantics.json').write_text(json.dumps(dict(source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),image_height=64,image_width=64,body_sha256='unused',tip_sha256='unused')))
            mask=np.zeros((64,64),bool);mask[10,10]=True;mask[20,20]=True
            with patch.object(adapter,'read_binary',side_effect=[mask.copy(),mask.copy()]),patch.object(adapter,'estimate',return_value=dict(mask=mask.copy())),patch.object(adapter.cv2,'resize',side_effect=AssertionError('resize must not run')):
                rgb,result=adapter.adapt(source,p)
            self.assertEqual(result['detected_pad_count'],2);self.assertIsNone(result['working_shape']);self.assertTrue(np.array_equal(mask,result['coarse_mask']))
            self.assertEqual([r['reject_reason'] for r in result['rejected']],['adapter_memory_limit_exceeded']*2)
            self.assertFalse(rgb.any())
if __name__=='__main__':unittest.main()
