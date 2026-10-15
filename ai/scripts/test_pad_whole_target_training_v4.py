import copy,json,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
from test_pad_refinement_tiles_v3 import TileFixture
from pad_refinement_data_contract_v2 import digest,read_gt
from pad_refinement_tiles_v3 import prepare as old_prepare,check_tiles,json_snapshot
from pad_whole_target_training_v4 import prepare,check,WHOLE


class WholePadDataTests(TileFixture):
    def setUp(self):
        super().setUp();self.legacy=old_prepare(self.inputs,self.registry,self.output)
        folder=self.root/'NEW';folder.mkdir();sem=folder/'semantics';sem.mkdir();gt=folder/'GT';gt.mkdir()
        source=folder/'source.png';exif=Image.Exif();exif[274]=6
        rgb=(np.arange(6*8*3).reshape(6,8,3)+31).astype(np.uint8);Image.fromarray(rgb).save(source,exif=exif)
        for name in ['body.png','tip.png']:(sem/name).write_bytes((Path(self.inputs[0]['semantics'])/name).read_bytes())
        meta=json.loads((Path(self.inputs[0]['semantics'])/'semantics.json').read_text());meta['source_sha256']=digest(source)
        (sem/'semantics.json').write_text(json.dumps(meta),encoding='utf-8')
        (gt/'ground_truth_mask.png').write_bytes((Path(self.inputs[0]['GT_folder'])/'ground_truth_mask.png').read_bytes())
        meta=json.loads((Path(self.inputs[0]['GT_folder'])/'source.json').read_text());meta.update(source_sha256=digest(source),
            exif_orientation=6,mask_semantics=WHOLE,human_review_attestation=True)
        (gt/'source.json').write_text(json.dumps(meta),encoding='utf-8')
        archive_sha='a'*64;group='conservative-bundle-'+archive_sha[:16]
        self.inputs.append(dict(source_id='NEW',source_path=str(source),source_sha256=digest(source),semantics=str(sem),GT_folder=str(gt),
            acquisition_group=group,group_provenance='conservative_reviewed_archive_cluster'))
        report=dict(version='reviewed_whole_pad_import_v1',human_reviewed=True,polygon_mask_exact=True,independent_final_test=False,
            policy=WHOLE,archive_sha256=archive_sha,sources=[dict(source_id='NEW',source_sha256=digest(source),annotation_status='valid_positive',
                GT_metadata_sha256=digest(gt/'source.json'),GT_mask_sha256=digest(gt/'ground_truth_mask.png'))])
        report_path=self.root/'import.json';report_path.write_text(json.dumps(report),encoding='utf-8')
        self.evidence=dict(legacy_manifest_path=str(self.output/'manifest.private.json'),legacy_manifest_sha256=digest(self.output/'manifest.private.json'),
            import_report_path=str(report_path),import_report_sha256=digest(report_path))
        self.whole=self.root/'whole'

    def data(self):return prepare(self.inputs,self.registry,self.evidence,self.whole)

    def test_three_groups_and_EXIF6_native_whole_targets(self):
        data=self.data();view=check(self.whole,data)
        self.assertEqual(data['group_split_plan']['group_count'],3)
        source=data['sources'][-1];self.assertEqual(source['source_exif_orientation'],6)
        self.assertEqual(read_gt(source).shape,(6,8));self.assertEqual(source['GT_policy'],WHOLE)
        self.assertFalse(any(k.startswith('GT') for s in view['sources'] for k in s))

    def test_inference_does_not_need_targets(self):
        data=self.data();view,_=json_snapshot(self.whole/'manifest.input.private.json')
        for row in self.inputs:
            for p in Path(row['GT_folder']).iterdir():p.unlink()
        check_tiles(self.whole,view,'inference')

    def test_split_new_bundle_into_different_group_is_rejected(self):
        self.inputs[-1]['acquisition_group']='invented-separate-group'
        with self.assertRaisesRegex(ValueError,'group_evidence'):self.data()
        self.assertFalse(self.whole.exists())

    def test_rehashed_training_label_corruption_is_rejected(self):
        data=self.data();r=data['crops'][-1]
        with np.load(self.whole/r['path']) as z:arrays={k:z[k].copy() for k in z.files}
        arrays['label'][100,100]=1-arrays['label'][100,100];np.savez_compressed(self.whole/r['path'],**arrays)
        r['file_sha256']=digest(self.whole/r['path'])
        with self.assertRaisesRegex(ValueError,'tile_label'):check(self.whole,data)

    def test_training_RGB_cannot_be_replaced_even_with_valid_hash(self):
        data=self.data();r=data['crops'][0]
        with np.load(self.whole/r['path']) as z:arrays={k:z[k].copy() for k in z.files}
        arrays['rgb'][100,100]=255;np.savez_compressed(self.whole/r['path'],**arrays);r['file_sha256']=digest(self.whole/r['path'])
        with self.assertRaisesRegex(ValueError,'input_content'):check(self.whole,data)

    def test_independence_claim_and_tampered_fold_rejected(self):
        data=self.data();bad=copy.deepcopy(data);bad['person_independence_verified']=True
        with self.assertRaisesRegex(ValueError,'header_contract'):check(self.whole,bad)
        data['group_split_plan']['folds'][0]['train'].append(data['group_split_plan']['folds'][0]['validation'][0])
        with self.assertRaisesRegex(ValueError,'group_split'):check(self.whole,data)

    def test_changed_manifest_is_rejected_before_model_initialization(self):
        import train_whole_pad_target_v4 as trainer
        self.data();original=trainer.check
        def mutate(root,manifest):
            result=original(root,manifest);(root/'manifest.whole.private.json').write_text('{}');return result
        with patch.object(trainer,'check',side_effect=mutate),patch.object(trainer,'build_pretrained') as build:
            with self.assertRaisesRegex(ValueError,'frozen_run_inputs'):trainer.train(self.whole,self.root/'missing.pt',self.root/'training')
        build.assert_not_called()

    def test_complete_input_GT_and_evidence_bindings_detect_late_mutation(self):
        from train_whole_pad_target_v4 import asset_bindings,assert_assets
        data=self.data();view=check(self.whole,data);weights=self.root/'encoder.pt';weights.write_bytes(b'unit fixture')
        bindings=asset_bindings(self.whole,data,view,weights);assert_assets(bindings)
        target=Path(data['sources'][-1]['GT_folder'])/'ground_truth_mask.png';before=target.read_bytes();target.write_bytes(b'late replacement')
        with self.assertRaisesRegex(ValueError,'frozen_run_inputs'):assert_assets(bindings)
        target.write_bytes(before);assert_assets(bindings)
        Path(self.evidence['import_report_path']).write_text('{}')
        with self.assertRaisesRegex(ValueError,'frozen_run_inputs'):assert_assets(bindings)

    def test_cached_GT_free_forward_is_exactly_the_V3_prediction(self):
        import torch
        from train_whole_pad_target_v4 import PreparedInputs
        from train_pad_refinement_tiles_v3 import predict_source
        data=self.data();view,_=json_snapshot(self.whole/'manifest.input.private.json');cache=PreparedInputs(self.whole,view)
        class Model(torch.nn.Module):
            def forward(self,x):return x[:,:1]*2+.3
        model=Model()
        for source in view['sources']:
            sid=source['source_id'];np.testing.assert_array_equal(cache.predict(model,sid),predict_source(model,self.whole,view,sid))


if __name__=='__main__':unittest.main()
