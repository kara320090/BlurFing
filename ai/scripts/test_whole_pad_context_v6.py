import random,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
import torch
from torchvision.models import mobilenet_v3_small
import train_pad_refinement as historical
from train_pad_refinement import seed_all,optimizer
from pad_refinement_data_contract_v2 import digest
from prepare_pad_refinement_data import letterbox
from whole_pad_context_model_v6 import WholePadContext,align_stage,encoder_identity,load_checkpoint
from whole_pad_context_inputs_v6 import context_image,local_grid,augment,ContextTiles,ContextInputs,grid_key,pixel_hash
import whole_pad_context_inputs_v6 as inputs


class ContextGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): torch.set_num_threads(2)

    def test_body_union_only_and_encoded_array_unchanged(self):
        rgb=np.arange(41*73*3,dtype=np.uint8).reshape(41,73,3);body=np.zeros((41,73),bool)
        body[2:13,4:30]=True;body[30:39,55:70]=True;before=rgb.copy()
        image,info=context_image(rgb,body)
        self.assertEqual(info['bbox'],[4,2,70,39]);self.assertTrue(np.array_equal(rgb,before))
        expected=letterbox(rgb[2:39,4:70],body[2:39,4:70],np.zeros((37,66),bool))[0]
        self.assertTrue(np.array_equal(image,expected))
        with self.assertRaisesRegex(ValueError,'nonempty'): context_image(rgb,np.zeros_like(body))

    def test_axis_rounding_and_half_pixel_mapping(self):
        g=dict(width=513,height=80,scaled_width=256,scaled_height=40,left=0,top=108)
        h=dict(width=800,height=525,scaled_width=256,scaled_height=168,left=0,top=44)
        grid,valid=local_grid(dict(bbox=[150,100,663,180],geometry=g),dict(bbox=[100,20,900,545],geometry=h))
        self.assertEqual(int(valid.sum()),256*40);self.assertTrue((grid[~valid]==0).all())
        yy,xx=np.mgrid[:256,:256]
        px=.5+8*((grid[:,:,0]+1)*16-.5);py=.5+8*((grid[:,:,1]+1)*16-.5)
        source_x=100+(px-h['left'])*800/256;source_y=20+(py-h['top'])*525/168
        np.testing.assert_allclose(source_x[valid],(150+(xx+.5)*513/256)[valid],atol=.00012,rtol=0)
        np.testing.assert_allclose(source_y[valid],(100+(yy+.5-108)*80/40)[valid],atol=.00012,rtol=0)

    def test_feature_stages_share_declared_anchor_not_interpolate_centers(self):
        for stride in [8,16,32]:
            n=256//stride;pos=.5+stride*torch.arange(n).float();yy,xx=torch.meshgrid(pos,pos,indexing='ij')
            value=torch.stack([xx,yy])[None];aligned=align_stage(value,stride)
            target=(.5+8*torch.arange(32).float()).clamp(max=float(pos[-1]))
            y,x=torch.meshgrid(target,target,indexing='ij')
            torch.testing.assert_close(aligned,torch.stack([x,y])[None],rtol=0,atol=.00002)

    def test_augmented_coordinate_ramp_all_rotations_flips_affine_extremes(self):
        yy,xx=torch.meshgrid(torch.arange(256).float(),torch.arange(256).float(),indexing='ij')
        grid=torch.stack([(xx-128)/256,(yy-128)/256],-1)
        rgb=torch.stack([(grid[:,:,0]+1)/2,(grid[:,:,1]+1)/2,torch.full_like(xx,.3)])
        mask=torch.ones((1,256,256));valid=torch.ones_like(mask,dtype=torch.bool)
        for k in range(4):
            for flip_x,flip_y in [(False,False),(True,False),(False,True),(True,True)]:
                for angle,scale in [(-15,.9),(15,1.1)]:
                    with patch.object(inputs.random,'randrange',return_value=k),patch.object(inputs.random,'random',side_effect=[.1 if flip_x else .9,.1 if flip_y else .9,.9,.9]),patch.object(inputs.random,'uniform',side_effect=[angle,scale,1.,1.,1.]):
                        out,_,_,mapped,support=augment(rgb,mask,mask,grid,valid)
                    expected=out[:2].permute(1,2,0)*2-1
                    torch.testing.assert_close(mapped[support[0]],expected[support[0]],rtol=0,atol=.000002)
                    self.assertTrue((mapped[~support[0]]==0).all())
                    self.assertGreater(int(support.sum()),30000)

    def test_local_RGB_label_and_rng_are_exact_historical_augmentation(self):
        rng=np.random.default_rng(45);data=dict(rgb=rng.integers(0,256,(256,256,3),dtype=np.uint8),
            coarse=(rng.random((256,256))>.6).astype(np.uint8),label=(rng.random((256,256))>.7).astype(np.uint8))
        record=dict(source_id='S',bbox=[0,0,512,512],geometry=dict(width=512,height=512,scaled_width=256,scaled_height=256,left=0,top=0))
        manifest=dict(sources=[dict(source_id='S')],crops=[record],purpose='training')
        fake=SimpleNamespace(grids={grid_key(record):(np.zeros((256,256,2),np.float32),np.ones((256,256),bool))},context={'S':np.zeros((648,32,32),np.float32)})
        old=historical.Crops('.',manifest,['S'],True);new=ContextTiles('.',manifest,['S'],fake)
        with patch.object(historical,'load_crop',return_value=data),patch.object(inputs,'load_crop',return_value=data):
            for seed in range(8):
                seed_all(seed);x,y=old[0];state=random.getstate();torch_state=torch.get_rng_state()
                seed_all(seed);local,_,_,_,label,weight=new[0]
                self.assertTrue(torch.equal(local,x));self.assertTrue(torch.equal(label,y));self.assertEqual(float(weight),1.)
                self.assertEqual(random.getstate(),state);self.assertTrue(torch.equal(torch.get_rng_state(),torch_state))

    def test_GT_view_and_large_cache_reject_before_loading_source(self):
        fake=SimpleNamespace(context_encoder=None)
        with self.assertRaisesRegex(ValueError,'GT_free'):
            ContextInputs('.',dict(purpose='training',GT_present=True,sources=[dict(height=2,width=2)],crops=[]),fake)
        with self.assertRaisesRegex(ValueError,'combined_cache_resource_limit'):
            ContextInputs('.',dict(sources=[dict(height=60000,width=60000)],crops=[]),fake)

    def test_cache_tampering_is_detected(self):
        obj=ContextInputs.__new__(ContextInputs);features=np.zeros((648,32,32),np.float32)
        grid=np.zeros((256,256,2),np.float32);valid=np.ones((256,256),bool)
        obj.context={'S':features};obj.bindings={'S':dict(feature_sha256=pixel_hash(features))}
        obj.grids={('S',(0,0,1,1)):(grid,valid)};obj.grid_bindings={('S',(0,0,1,1)):(pixel_hash(grid),pixel_hash(valid))}
        obj.assert_unchanged();grid[0,0]=1
        with self.assertRaisesRegex(ValueError,'grid_cache_changed'): obj.assert_unchanged()
        grid[:]=0;features[0,0,0]=1
        with self.assertRaisesRegex(ValueError,'feature_cache_changed'): obj.assert_unchanged()
        obj.encoder_sha256='0'*64
        with self.assertRaisesRegex(ValueError,'encoder_cache_mismatch'):
            obj.assert_unchanged(SimpleNamespace(context_encoder=torch.nn.Identity()))


class ContextModelTests(unittest.TestCase):
    def test_frozen_context_optimizer_gradients_invalid_sampling_and_roundtrip(self):
        seed_all(51);model=WholePadContext(mobilenet_v3_small(weights=None));before=encoder_identity(model.context_encoder)
        self.assertEqual(model.encoder[0][0].in_channels,4);self.assertEqual(model.context_encoder[0][0].in_channels,3)
        c=model.context_features(torch.randn(1,3,256,256));x=torch.randn(1,4,256,256)
        grid=torch.zeros((1,256,256,2));valid=torch.ones((1,1,256,256),dtype=torch.bool)
        opt=optimizer(model);ids=[id(p) for group in opt.param_groups for p in group['params']]
        self.assertEqual(len(ids),len(set(ids)));self.assertEqual(set(ids),{id(p) for p in model.parameters() if p.requires_grad})
        model.train();opt.zero_grad();out=model(x,c,grid,valid);self.assertEqual(tuple(out.shape),(1,1,256,256))
        out.square().mean().backward();self.assertGreater(float(model.context_projection[0].weight.grad.abs().sum()),0.)
        self.assertTrue(all(p.grad is None for p in model.context_encoder.parameters()));opt.step()
        self.assertEqual(encoder_identity(model.context_encoder),before)
        self.assertFalse(any(m.training for m in model.context_encoder.modules()))
        sampled=model.sample_context(c,grid,torch.zeros_like(valid));self.assertTrue(torch.equal(sampled,torch.zeros_like(sampled)))
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'model.pt';torch.save(model.state_dict(),path);loaded=load_checkpoint(path,digest(path))
            model.eval()
            with torch.no_grad(): torch.testing.assert_close(model(x,c,grid,valid),loaded(x,c,grid,valid),rtol=0,atol=0)
            self.assertEqual(encoder_identity(loaded.context_encoder),before)
            with torch.no_grad(): model.head[-1].weight.fill_(float('nan'))
            torch.save(model.state_dict(),path)
            with self.assertRaisesRegex(ValueError,'nonfinite_model_state'): load_checkpoint(path,digest(path))


if __name__=='__main__': unittest.main()
