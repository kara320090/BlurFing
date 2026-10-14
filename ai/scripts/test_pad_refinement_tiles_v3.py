import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
from pad_refinement_data_contract_v2 import source_record,digest,COORDINATES,check_dataset
from pad_refinement_tiles_v3 import prepare,check_tiles,input_view,image_identity,exclude_consumed,hash_json
from prepare_pad_refinement_data import letterbox


class TileFixture(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.registry=[dict(source_sha256=f'{i:064x}',encoded_RGB_sha256=f'{i+100:064x}',
                            upright_RGB_sha256=f'{i+200:064x}',role='consumed_GT7' if i<8 else 'consumed_holdout') for i in range(1,16)]
        self.inputs=[]
        for i in range(2):
            sid=f'SYNTH-{i}';folder=self.root/sid;folder.mkdir();sem=folder/'semantics';sem.mkdir();GT=folder/'GT';GT.mkdir()
            rgb=(np.arange(6*8*3).reshape(6,8,3)+i).astype(np.uint8);path=folder/'original.png';Image.fromarray(rgb).save(path)
            Image.fromarray(np.full((6,8),255,np.uint8)).save(sem/'body.png');Image.fromarray(np.zeros((6,8),np.uint8)).save(sem/'tip.png')
            identity=dict(source_sha256=digest(path),body_sha256=digest(sem/'body.png'),tip_sha256=digest(sem/'tip.png'),
                          coordinate_system=COORDINATES,body_classes=[1,2],tip_class=2,minimum_votes=2)
            (sem/'semantics.json').write_text(json.dumps(identity),encoding='utf-8')
            gt=np.zeros((6,8),np.uint8);gt[1:4,2:5]=255;Image.fromarray(gt).save(GT/'ground_truth_mask.png')
            metadata=dict(source_sha256=digest(path),mask_sha256=digest(GT/'ground_truth_mask.png'),
                          human_annotation=True,annotation_type='human_reviewed_fingerprint_pad',coordinate_system=COORDINATES,
                          image_height=6,image_width=8,exif_orientation=1)
            (GT/'source.json').write_text(json.dumps(metadata),encoding='utf-8')
            self.inputs.append(dict(source_id=sid,source_path=str(path),source_sha256=digest(path),semantics=str(sem),GT_folder=str(GT),
                                    acquisition_group=f'group-{i}',group_provenance='acquisition_folder_and_filename_date'))
        self.output=self.root/'tiles'

    def data(self):return prepare(self.inputs,self.registry,self.output)


class TileDataTests(TileFixture):
    def test_complete_native_bound_tiles_and_legacy_rejection(self):
        data=self.data();check_tiles(self.output,data,'training');self.assertEqual(len(data['crops']),2)
        self.assertEqual(len(data['group_split_plan']['folds']),2)
        with self.assertRaisesRegex(ValueError,'V2_dataset'):check_dataset(self.output,data,'training')

    def test_prediction_view_does_not_read_deleted_targets(self):
        data=self.data();view=input_view(data)
        for row in self.inputs:
            for file in Path(row['GT_folder']).iterdir():file.unlink()
        with (patch('pad_refinement_data_contract_v2.read_gt',side_effect=AssertionError('GT touched')),
              patch('pad_refinement_tiles_v3.read_gt',side_effect=AssertionError('GT touched'))):
            check_tiles(self.output,view,'inference')
        self.assertFalse(any(k.startswith('GT') for s in view['sources'] for k in s))

    def test_stale_rehashed_RGB_cannot_pass_native_content_check(self):
        data=self.data();view=input_view(data);r=view['crops'][0]
        with np.load(self.output/r['path']) as z:arrays={k:z[k].copy() for k in z.files}
        arrays['rgb'][100,100]=255;np.savez_compressed(self.output/r['path'],**arrays);r['file_sha256']=digest(self.output/r['path'])
        with self.assertRaisesRegex(ValueError,'crop_content'):check_tiles(self.output,view,'inference')

    def test_consumed_reencoding_and_missing_holdouts_rejected_before_output(self):
        identity=image_identity(self.inputs[0]['source_path']);registry=copy.deepcopy(self.registry)
        registry[0]['encoded_RGB_sha256']=identity['upright_RGB_sha256']
        with self.assertRaisesRegex(ValueError,'decoded_pixels'):prepare(self.inputs,registry,self.output)
        self.assertFalse(self.output.exists())
        with self.assertRaisesRegex(ValueError,'holdout'):prepare(self.inputs,self.registry[:7],self.output)

    def test_single_source_GT_free_preparation_and_missing_tile_rejection(self):
        rows=[{k:v for k,v in self.inputs[0].items() if k!='GT_folder'}]
        rows[0].update(acquisition_group='unknown',group_provenance='inference_only_unknown')
        view=prepare(rows,self.registry,self.output,'inference');check_tiles(self.output,view,'inference')
        view['crops']=[];view['sources'][0]['crop_count']=0
        with self.assertRaisesRegex(ValueError,'tile_plan'):check_tiles(self.output,view,'inference')


try:
    import torch
    import torchvision
    TORCH=True
except ImportError:TORCH=False


@unittest.skipUnless(TORCH,'isolated Torch runtime required')
class TileTrainingTests(TileFixture):
    def test_replaced_manifest_cannot_publish_successful_prediction_report(self):
        import infer_pad_refinement_tiles_v3 as infer
        from train_pad_refinement_tiles_v3 import code_hashes
        data=self.data();target=self.root/'predictions'
        cfg=dict(model_sha256='0'*64,consumed_registry_sha256=data['consumed_registry_sha256'],source_code_sha256=code_hashes())
        def predict(*args):
            (self.output/'manifest.input.private.json').write_text('{}',encoding='utf-8')
            return np.zeros((6,8),bool)
        with (patch.object(infer,'load_model',return_value=(torch.nn.Identity(),cfg)),
              patch.object(infer,'predict_source',side_effect=predict)):
            with self.assertRaisesRegex(ValueError,'frozen_run_inputs'):infer.run(self.root,self.output,target)
        self.assertFalse((target/'inference.private.json').exists())

    def test_training_replaced_snapshot_rejected_before_model_initialization(self):
        import train_pad_refinement_tiles_v3 as trainer
        self.data();check=trainer.check_tiles
        def replace(root,manifest,purpose):
            result=check(root,manifest,purpose)
            if purpose=='training':(root/'manifest.private.json').write_text('{}',encoding='utf-8')
            return result
        with (patch.object(trainer,'check_tiles',side_effect=replace),patch.object(trainer,'build_pretrained') as build):
            with self.assertRaisesRegex(ValueError,'frozen_run_inputs'):trainer.train(self.output,self.root/'missing.pt',self.root/'trained')
        build.assert_not_called();self.assertFalse((self.root/'trained').exists())

    def test_unpaired_published_input_rejected_before_model_initialization(self):
        import train_pad_refinement_tiles_v3 as trainer
        data=self.data();view=input_view(data);view['unexpected']='changed'
        (self.output/'manifest.input.private.json').write_text(json.dumps(view),encoding='utf-8')
        with patch.object(trainer,'build_pretrained') as build:
            with self.assertRaisesRegex(ValueError,'published_input_manifest'):trainer.train(self.output,self.root/'missing.pt',self.root/'trained')
        build.assert_not_called();self.assertFalse((self.root/'trained').exists())

    def test_modified_checkpoint_policy_rejected_before_torch_load(self):
        import infer_pad_refinement_tiles_v3 as infer
        (self.root/'final_config.private.json').write_text(json.dumps(dict(training_complete=True)),encoding='utf-8')
        with patch.object(infer,'load_checkpoint') as load:
            with self.assertRaisesRegex(ValueError,'checkpoint_contract'):infer.load_model(self.root)
        load.assert_not_called()

    def test_actual_model_prediction_uses_only_input_bundle(self):
        from train_pad_refinement_tiles_v3 import predict_source
        data=self.data()
        class Model(torch.nn.Module):
            def forward(self,x):return torch.full((len(x),1,256,256),2.,dtype=torch.float32)
        for row in self.inputs:
            for file in Path(row['GT_folder']).iterdir():file.unlink()
        with (patch('pad_refinement_data_contract_v2.read_gt',side_effect=AssertionError('GT touched')),
              patch('pad_refinement_tiles_v3.read_gt',side_effect=AssertionError('GT touched'))):
            pred=predict_source(Model(),self.output,data,'SYNTH-0')
        self.assertTrue(pred.all());self.assertEqual(pred.shape,(6,8))

    def test_source_mass_equal_without_batch_renormalization(self):
        from train_pad_refinement_tiles_v3 import source_weights
        records=[dict(source_id='A')]+[dict(source_id='B') for _ in range(9)]
        weights=source_weights(records)
        self.assertAlmostEqual(weights[0]/10,.5)
        self.assertAlmostEqual(sum(weights[1:])/10,.5)

    def test_merge_probabilities_before_threshold_with_actual_overlap(self):
        from train_pad_refinement_tiles_v3 import restore_probability_mean
        body=np.ones((6,8),bool);g=letterbox(np.zeros((6,8,3),np.uint8),body,body)[3]
        row=dict(bbox=[0,0,8,6],geometry=g)
        for values,expected in [([.2,.6],.4),([.4,.55],.475),([.01,.9,.9],1.81/3)]:
            p=restore_probability_mean(body,[row]*len(values),[np.full((256,256),v,np.float32) for v in values])
            np.testing.assert_allclose(p,expected,rtol=1e-6)

    def test_last_optimizer_step_nonfinite_state_rejected(self):
        from train_pad_refinement_tiles_v3 import train_epoch
        model=torch.nn.Conv2d(4,1,1);opt=torch.optim.SGD(model.parameters(),lr=.1)
        step=opt.step
        def corrupt():
            step()
            with torch.no_grad():model.weight.fill_(float('inf'))
        opt.step=corrupt
        loader=[(torch.zeros((1,4,256,256)),torch.zeros((1,1,256,256)),torch.ones(1))]
        with self.assertRaisesRegex(ValueError,'model_state'):train_epoch(model,loader,opt)


if __name__=='__main__':unittest.main()
