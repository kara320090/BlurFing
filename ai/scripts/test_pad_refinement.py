import unittest
import numpy as np
from prepare_pad_refinement_data import guided_bbox,letterbox

class RefinementDataTests(unittest.TestCase):
    def test_crop_uses_coarse_not_GT(self):
        coarse=np.zeros((100,120),bool);coarse[20:40,30:50]=True;bbox=guided_bbox(coarse);self.assertEqual(bbox,[23,13,57,47])
    def test_letterbox_mask_binary(self):
        rgb=np.ones((37,51,3),np.uint8)*100;mask=np.zeros((37,51),bool);mask[5:20,3:40]=True;x,c,g,meta=letterbox(rgb,mask,~mask);self.assertEqual(x.shape,(256,256,3));self.assertTrue(np.isin(c,[0,1]).all());self.assertTrue(np.isin(g,[0,1]).all());self.assertEqual(meta['width'],51)
    def test_empty_coarse_not_GT_fallback(self):
        with self.assertRaises(ValueError):guided_bbox(np.zeros((10,10),bool))

try:
    import torch
    import torchvision
    TORCH_AVAILABLE=True
except ImportError:TORCH_AVAILABLE=False

@unittest.skipUnless(TORCH_AVAILABLE,'isolated PyTorch environment required')
class RefinementArchitectureTests(unittest.TestCase):
    def test_folds_source_disjoint(self):
        from train_pad_refinement import ALLOWED,folds
        splits=folds(sorted(ALLOWED));self.assertEqual(len(splits),5);self.assertEqual({s for f in splits for s in f['validation']},ALLOWED)
        for f in splits:self.assertEqual(len(f['train']),8);self.assertEqual(len(f['validation']),2);self.assertFalse(set(f['train'])&set(f['validation']))
    def test_no_pretrained_random_fallback(self):
        from pad_refinement_model import build_pretrained
        with self.assertRaises(FileNotFoundError):build_pretrained('/nonexistent/pretrained_encoder.pt')
    def test_synthetic_only_architecture_and_fourth_channel(self):
        from pad_refinement_model import synthetic_test_model,bce_dice
        torch.set_num_threads(2);model=synthetic_test_model().eval();self.assertEqual(model.encoder[0][0].weight.shape[1],4);self.assertEqual(int(torch.count_nonzero(model.encoder[0][0].weight[:,3])),0)
        x=torch.zeros((1,4,256,256));output=model(x);self.assertEqual(output.shape,(1,1,256,256));self.assertTrue(torch.isfinite(bce_dice(output,torch.zeros_like(output))))

if __name__=='__main__':unittest.main()
