"""Synthetic objective/lifecycle checks, never real fingerprint metrics."""
import io,math,unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
import numpy as np
import torch
import torch.nn.functional as F
import whole_pad_balanced_loss_v1 as loss
import train_whole_pad_target_v5 as trainer
from train_pad_refinement_tiles_v3 import per_example_loss as previous_loss
import test_pad_whole_target_training_v4 as whole_fixture


def stats(p):return dict(positive_fraction=p,positive_weight=1/(2*p),negative_weight=1/(2*(1-p)))


class BalancedLossTests(unittest.TestCase):
    def setUp(self):
        self.threads=torch.get_num_threads();torch.set_num_threads(1);self.addCleanup(torch.set_num_threads,self.threads)

    def test_source_balance_differs_from_tile_average_and_never_reads_validation(self):
        manifest=dict(sources=[dict(source_id=s) for s in ['A','B','VAL']],
            crops=[dict(source_id=s,path=str(i),file_sha256=str(i)) for i,s in enumerate(['A','A','B','VAL'])])
        values=[0,1,1,0];read=[]
        def load(root,r,source,purpose):
            self.assertNotEqual(source['source_id'],'VAL');read.append(source['source_id'])
            return dict(label=np.full((256,256),values[int(r['path'])],np.uint8))
        with patch.object(loss,'load_crop',side_effect=load):
            first=loss.class_balance('.',manifest,['A','B']);values[3]=1;second=loss.class_balance('.',manifest,['A','B'])
        self.assertEqual(first,second);self.assertEqual(first['positive_fraction'],.75);self.assertNotEqual(first['positive_fraction'],2/3)
        self.assertEqual(set(read),{'A','B'})

    def test_half_balance_positive_loss_and_gradient_equal_previous(self):
        target=torch.zeros((2,1,256,256),dtype=torch.float64);target[:,:,40:90,30:80]=1
        x=torch.full_like(target,.3,requires_grad=True);y=x.detach().clone().requires_grad_()
        a=loss.per_example_loss(x,target,stats(.5));b=previous_loss(y,target)
        torch.testing.assert_close(a,b,rtol=0,atol=0);a.sum().backward();b.sum().backward()
        torch.testing.assert_close(x.grad,y.grad,rtol=0,atol=0)

    def test_empty_Dice_zero_but_background_BCE_gradient_remains(self):
        target=torch.zeros((2,1,256,256),dtype=torch.float64);target[1,:,80:120,80:120]=1
        x=torch.zeros_like(target,requires_grad=True);result=loss.per_example_loss(x,target,stats(.5))
        bce=F.binary_cross_entropy_with_logits(x,target,reduction='none').mean((1,2,3))
        self.assertEqual(float(result[0].detach()),float(bce[0].detach()));self.assertGreater(float(result[1].detach()),float(bce[1].detach()))
        result[0].backward();self.assertTrue((x.grad[0]>0).all());self.assertTrue((x.grad[1]==0).all())
        torch.testing.assert_close(x.grad[0],torch.full_like(x.grad[0],.5/(256*256)),rtol=0,atol=0)

    def test_weighted_BCE_value_and_gradient_follow_both_class_weights(self):
        target=torch.zeros((1,1,256,256),dtype=torch.float64);target[:,:,:128]=1
        x=torch.full_like(target,.2,requires_grad=True);y=x.detach().clone().requires_grad_();p=.1
        actual=loss.per_example_loss(x,target,stats(p))
        prob=y.sigmoid();dice=1-(2*(prob*target).sum()+1)/(prob.sum()+target.sum()+1)
        weights=target/(2*p)+(1-target)/(2*(1-p))
        expected=(F.binary_cross_entropy_with_logits(y,target,reduction='none')*weights).mean()+dice
        torch.testing.assert_close(actual[0],expected,rtol=1e-14,atol=1e-14);actual.sum().backward();expected.backward()
        torch.testing.assert_close(x.grad,y.grad,rtol=1e-14,atol=1e-14)

    def test_invalid_classes_nonbinary_and_weights_fail(self):
        x=torch.zeros((1,1,256,256));target=torch.zeros_like(x)
        for p in [0,1,float('nan'),float('inf')]:
            with self.assertRaises(ValueError):loss.per_example_loss(x,target,dict(positive_fraction=p))
        bad=stats(.1);bad['positive_weight']=1
        with self.assertRaisesRegex(ValueError,'weight_contract'):loss.per_example_loss(x,target,bad)
        with self.assertRaisesRegex(ValueError,'binary'):loss.per_example_loss(x,target+.1,stats(.1))
        manifest=dict(sources=[dict(source_id='A')],crops=[dict(source_id='A',path='0',file_sha256='0')])
        for value in [0,1]:
            with patch.object(loss,'load_crop',return_value=dict(label=np.full((256,256),value,np.uint8))):
                with self.assertRaisesRegex(ValueError,'both_finite'):loss.class_balance('.',manifest,['A'])

    def test_partial_batch_keeps_configured_divisor_and_V5_objective(self):
        class Model(torch.nn.Module):
            def __init__(self):super().__init__();self.logit=torch.nn.Parameter(torch.tensor(0.))
            def forward(self,x):return self.logit.expand(len(x),1,256,256)
        model=Model();opt=torch.optim.SGD(model.parameters(),lr=0.)
        loader=[(torch.zeros(n,1),torch.zeros(n,1,256,256),torch.tensor(w,dtype=torch.float32)) for n,w in [(4,[1,2,3,4]),(2,[5,6])]]
        with patch.object(trainer.common,'train_epoch',side_effect=AssertionError('V3 loss cannot be used')):
            measured=trainer.train_epoch(model,loader,opt,stats(.5))
        self.assertAlmostEqual(measured,math.log(2)*21/6,places=6);self.assertAlmostEqual(float(model.logit.grad),.5*11/4,places=6)


class BalancedLifecycleTests(unittest.TestCase):
    def test_late_GT_change_prevents_completed_V5_config(self):
        fixture=whole_fixture.WholePadDataTests('test_three_groups_and_EXIF6_native_whole_targets');fixture.setUp();self.addCleanup(fixture.doCleanups)
        manifest=fixture.data();weights=fixture.root/'encoder.pt';weights.write_bytes(b'synthetic test only')
        out=fixture.root/'balanced';target=Path(manifest['sources'][-1]['GT_folder'])/'ground_truth_mask.png'
        class Model(torch.nn.Module):
            def __init__(self):super().__init__();self.weight=torch.nn.Parameter(torch.tensor(1.))
        def validate(model,root,m,view,ids,*args,**kwargs):
            return dict(source_macro_iou=.2,rows=[dict(source_id=s,policy='unit',iou=.2,dice=.3) for s in sorted(ids)])
        original=trainer.common.save_checkpoint
        def save(model,path):
            digest=original(model,path)
            if path.name=='final_balanced_whole_pad.pt':target.write_bytes(b'late mutation')
            return digest
        with redirect_stdout(io.StringIO()),patch.object(trainer,'build_pretrained',side_effect=lambda w:(Model(),'unit')),patch.object(trainer,'optimizer',side_effect=lambda m:torch.optim.SGD(m.parameters(),lr=.1)),patch.object(trainer,'train_epoch',return_value=1.),patch.object(trainer,'validation',side_effect=validate),patch.object(trainer.common,'make_loader',return_value=[]),patch.object(trainer.common,'load_checkpoint',side_effect=lambda *a:Model()),patch.object(trainer.common,'save_checkpoint',side_effect=save):
            with self.assertRaisesRegex(ValueError,'frozen_run_inputs'):trainer.train(fixture.whole,weights,out)
        self.assertFalse((out/'final_config.private.json').exists())


if __name__=='__main__':unittest.main()
