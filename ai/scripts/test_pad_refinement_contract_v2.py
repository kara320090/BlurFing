import copy
import io
import json
import tempfile
import unittest
import zipfile
import struct
import zlib
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image
from prepare_pad_refinement_data import letterbox
from pad_refinement_data_contract_v2 import (VERSION,COORDINATES,check_dataset,crop_path,
    digest,load_crop,read_body,read_gt,source_record,validate_source_id)


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.dataset=self.root/'dataset';self.dataset.mkdir()
        self.source,self.crop,self.arrays=self.asset('TEST-01',0)
        self.manifest=dict(version=VERSION,purpose='inference',coordinate_system=COORDINATES,
            input_size=256,context_padding=.35,crop_policy='coarse_guided_v1',GT_present=False,
            sources=[self.source],crops=[self.crop])

    def asset(self,sid,offset):
        folder=self.root/sid;folder.mkdir();semantic=folder/'semantic';semantic.mkdir()
        rgb=(np.arange(6*8*3).reshape(6,8,3)+offset).astype(np.uint8)
        original=folder/'source.png';Image.fromarray(rgb).save(original)
        Image.fromarray(np.full((6,8),255,np.uint8)).save(semantic/'body.png')
        Image.fromarray(np.zeros((6,8),np.uint8)).save(semantic/'tip.png')
        identity=dict(source_sha256=digest(original),coordinate_system=COORDINATES,body_classes=[1,2],
            tip_class=2,minimum_votes=2,body_sha256=digest(semantic/'body.png'),tip_sha256=digest(semantic/'tip.png'))
        (semantic/'semantics.json').write_text(json.dumps(identity))
        source=source_record(original,sid,semantic,rgb)
        image,coarse,label,geometry=letterbox(rgb,np.ones((6,8),bool),np.zeros((6,8),bool))
        arrays=dict(rgb=image,coarse=coarse,label=label);name=sid+'_crop_000.npz'
        np.savez_compressed(self.dataset/name,**arrays)
        crop=dict(source_id=sid,source_sha256=source['source_sha256'],path=name,
            file_sha256=digest(self.dataset/name),bbox=[0,0,8,6],geometry=geometry)
        return source,crop,arrays

    def rewrite(self,arrays):
        np.savez_compressed(self.dataset/self.crop['path'],**arrays)
        self.crop['file_sha256']=digest(self.dataset/self.crop['path'])

    def GT(self,status='valid_positive',present=True):
        folder=self.root/'annotation';folder.mkdir(exist_ok=True)
        mask=np.zeros((6,8),np.uint8);mask[1:4,2:5]=255
        Image.fromarray(mask).save(folder/'ground_truth_mask.png')
        meta=dict(source_sha256=self.source['source_sha256'],human_annotation=True,
            annotation_type='human_reviewed_fingerprint_pad',coordinate_system=COORDINATES,
            image_width=8,image_height=6,exif_orientation=1,
            mask_sha256=digest(folder/'ground_truth_mask.png'),annotation_status=status)
        (folder/'source.json').write_text(json.dumps(meta))
        self.source.update(GT_folder=str(folder),GT_metadata_sha256=digest(folder/'source.json'),
            GT_mask_sha256=digest(folder/'ground_truth_mask.png'))
        if not present:(folder/'ground_truth_mask.png').unlink()
        return folder,mask


class ContractTests(Fixture):
    def test_valid_nonsquare_arrays_exact_and_no_GT_access(self):
        check_dataset(self.dataset,self.manifest,'inference')
        actual=load_crop(self.dataset,self.crop,self.source,'inference')
        for key in self.arrays:np.testing.assert_array_equal(actual[key],self.arrays[key])
        self.assertEqual(self.crop['geometry']['scaled_height'],192)

    def test_wrong_native_body_shape_rejected_even_with_matching_hash(self):
        Image.fromarray(np.full((1,8),255,np.uint8)).save(self.source['body_path'])
        self.source['body_sha256']=digest(self.source['body_path'])
        with self.assertRaisesRegex(ValueError,'shape'):read_body(self.source)

    def test_body_nonbinary_and_source_EXIF_mismatch_rejected(self):
        Image.fromarray(np.full((6,8),128,np.uint8)).save(self.source['body_path'])
        self.source['body_sha256']=digest(self.source['body_path'])
        with self.assertRaisesRegex(ValueError,'nonbinary'):read_body(self.source)
        self.source['source_exif_orientation']=6
        with self.assertRaisesRegex(ValueError,'image_contract'):check_dataset(self.dataset,self.manifest,'inference')

    def test_crop_changed_after_preflight_detected(self):
        check_dataset(self.dataset,self.manifest,'inference')
        arrays=copy.deepcopy(self.arrays);arrays['coarse'][:]=0
        np.savez_compressed(self.dataset/self.crop['path'],**arrays)
        with self.assertRaisesRegex(ValueError,'hash_mismatch'):load_crop(self.dataset,self.crop,self.source,'inference')

    def test_unbound_legacy_manifest_and_duplicate_source_hash_rejected(self):
        broken=copy.deepcopy(self.manifest);broken['version']='pad_refinement_data_v1'
        with self.assertRaisesRegex(ValueError,'V2_dataset_required'):check_dataset(self.dataset,broken,'inference')
        self.manifest['sources'].append(dict(self.source,source_id='ALIAS'))
        with self.assertRaisesRegex(ValueError,'duplicate_source'):check_dataset(self.dataset,self.manifest,'inference')

    def test_casefold_source_collision_and_incorrect_crop_count_rejected(self):
        self.manifest['sources'].append(dict(self.source,source_id='test-01'))
        with self.assertRaisesRegex(ValueError,'duplicate_source'):check_dataset(self.dataset,self.manifest,'inference')
        self.manifest['sources'].pop();self.source['crop_count']=0
        with self.assertRaisesRegex(ValueError,'crop_count'):check_dataset(self.dataset,self.manifest,'inference')

    def test_prepare_rejects_asset_change_during_estimate(self):
        from prepare_pad_refinement_inference import prepare
        original=self.source['source_path'];semantic=Path(self.source['body_path']).parent
        class SemanticRoot:
            def __truediv__(self,sid):return semantic
        def replace(body,tip):
            Image.fromarray(np.zeros((6,8),np.uint8)).save(semantic/'body.png')
            identity=json.loads((semantic/'semantics.json').read_text())
            identity['body_sha256']=digest(semantic/'body.png')
            (semantic/'semantics.json').write_text(json.dumps(identity))
            return dict(regions=[dict(mask=body,reject_reason=None)],mask=body)
        output=self.root/'new_dataset'
        with patch('prepare_pad_refinement_inference.estimate',side_effect=replace):
            with self.assertRaisesRegex(ValueError,'hash_mismatch'):
                prepare([dict(sample_id='TEST-01',source=original,source_sha256=self.source['source_sha256'])],SemanticRoot(),output)
        self.assertFalse((output/'manifest.private.json').exists())

    def test_crop_paths_and_geometry_reject_outside_or_rounded_mismatch(self):
        for name in ['../bad.npz','a/b.npz','a\\b.npz','C:a.npz','/a.npz','\\a.npz','a:stream.npz','NUL.npz','a.npz ']:
            with self.subTest(name=name),self.assertRaises(ValueError):crop_path(self.dataset,name)
        self.crop['geometry']['top']+=1
        with self.assertRaisesRegex(ValueError,'geometry'):load_crop(self.dataset,self.crop,self.source,'inference')

    def test_windows_reserved_source_ids_rejected_without_IO(self):
        for sid in ['CON','nul','PrN','AUX','COM1','LPT9']:
            with self.subTest(sid=sid),self.assertRaisesRegex(ValueError,'source_id'):validate_source_id(sid)
        validate_source_id('CON-01')

    def test_forged_zip_size_cannot_expand_unbounded(self):
        payloads={}
        for key,array in self.arrays.items():
            buffer=io.BytesIO();np.save(buffer,array,allow_pickle=False);payloads[key]=buffer.getvalue()
        buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,'w',compression=zipfile.ZIP_DEFLATED) as archive:
            for name,payload in payloads.items():archive.writestr(name+'.npy',payload+(b'Z'*2*1024**2 if name=='rgb' else b''))
        forged=bytearray(buffer.getvalue());central=forged.index(b'PK\x01\x02');crc=zlib.crc32(payloads['rgb'])&0xffffffff
        for offset,value in [(14,crc),(22,len(payloads['rgb'])),(central+16,crc),(central+24,len(payloads['rgb']))]:struct.pack_into('<I',forged,offset,value)
        (self.dataset/self.crop['path']).write_bytes(forged);self.crop['file_sha256']=digest(self.dataset/self.crop['path'])
        original=zipfile._get_decompressor;lengths=[]
        class Observe:
            def __init__(self,inner):self.inner=inner
            def decompress(self,data,max_length):
                lengths.append(max_length);return self.inner.decompress(data,max_length)
            def __getattr__(self,name):return getattr(self.inner,name)
        with patch.object(zipfile,'_get_decompressor',side_effect=lambda method:Observe(original(method))):
            actual=load_crop(self.dataset,self.crop,self.source,'inference')
        self.assertTrue(lengths);self.assertLessEqual(max(lengths),256*256*3+2048+13)
        for key in self.arrays:np.testing.assert_array_equal(actual[key],self.arrays[key])

    def test_unsupported_zip_codec_and_floating_NPY_shape_rejected(self):
        from numpy.lib.format import write_array_header_1_0
        for codec,floating in [(zipfile.ZIP_BZIP2,False),(zipfile.ZIP_DEFLATED,True)]:
            buffer=io.BytesIO()
            with zipfile.ZipFile(buffer,'w',compression=codec) as archive:
                for name,array in self.arrays.items():
                    payload=io.BytesIO()
                    if name=='rgb' and floating:
                        write_array_header_1_0(payload,dict(descr='|u1',fortran_order=False,shape=(256.0,256.0,3.0)))
                        payload.write(array.tobytes())
                    else:np.save(payload,array,allow_pickle=False)
                    archive.writestr(name+'.npy',payload.getvalue())
            (self.dataset/self.crop['path']).write_bytes(buffer.getvalue());self.crop['file_sha256']=digest(self.dataset/self.crop['path'])
            with self.assertRaises(ValueError):load_crop(self.dataset,self.crop,self.source,'inference')

    def test_NPZ_binary_dtype_shape_members_and_inference_label_rejected(self):
        for key,value in [('coarse',np.full((256,256),2,np.uint8)),('rgb',np.zeros((256,256,3),np.float32)),
                          ('label',np.zeros((1,256),np.uint8))]:
            arrays=copy.deepcopy(self.arrays);arrays[key]=value;self.rewrite(arrays)
            with self.subTest(key=key),self.assertRaises(ValueError):load_crop(self.dataset,self.crop,self.source,'inference')
        arrays=copy.deepcopy(self.arrays);arrays['label'][100,100]=1;self.rewrite(arrays)
        with self.assertRaisesRegex(ValueError,'GT_label'):load_crop(self.dataset,self.crop,self.source,'inference')
        self.rewrite(dict(self.arrays,extra=np.zeros(1,np.uint8)))
        with self.assertRaisesRegex(ValueError,'members'):load_crop(self.dataset,self.crop,self.source,'inference')

    def test_NPY_huge_header_rejected_before_array_allocation(self):
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as archive:
            for name in ['rgb','coarse','label']:
                array=io.BytesIO();np.save(array,self.arrays[name],allow_pickle=False)
                payload=array.getvalue()
                # A declared 65535-byte v1 header exceeds the bounded contract.
                if name=='rgb':payload=payload[:8]+b'\xff\xff'+payload[10:]
                archive.writestr(name+'.npy',payload)
        (self.dataset/self.crop['path']).write_bytes(stream.getvalue());self.crop['file_sha256']=digest(self.dataset/self.crop['path'])
        with patch('numpy.frombuffer',side_effect=AssertionError('allocation reached')):
            with self.assertRaisesRegex(ValueError,'payload'):load_crop(self.dataset,self.crop,self.source,'inference')

    def test_training_GT_mutation_detected_and_empty_crop_label_allowed(self):
        self.GT();self.manifest.update(purpose='training',GT_present=True)
        check_dataset(self.dataset,self.manifest,'training')
        self.assertFalse(load_crop(self.dataset,self.crop,self.source,'training')['label'].any())
        Image.fromarray(np.zeros((6,8),np.uint8)).save(Path(self.source['GT_folder'])/'ground_truth_mask.png')
        with self.assertRaisesRegex(ValueError,'hash_mismatch'):read_gt(self.source)

    def test_ambiguous_or_missing_GT_not_in_metric_denominator(self):
        from evaluate_pad_refinement_final import evaluate
        for index,present in enumerate([True,False]):
            folder,gt=self.GT('ambiguous_unusable',present)
            output=self.root/('predictions_'+str(index));output.mkdir()
            pred=np.zeros((6,8),np.uint8);pred[1:4,5:8]=255;Image.fromarray(pred).save(output/'TEST-01.png')
            import hashlib
            record=dict(sample_id='TEST-01',source_sha256=self.source['source_sha256'],
                mask_pixel_sha256=hashlib.sha256((pred>0).tobytes()).hexdigest(),body_exterior_pixels=0,deterministic=True)
            (output/'inference.private.json').write_text(json.dumps(dict(model_sha256='synthetic',rows=[record])))
            report=evaluate([dict(sample_id='TEST-01',GT_folder=str(folder),source=self.source['source_path'])],output,self.root/('eval_'+str(index)))
            self.assertIsNone(report['rows'][0]['raw_metrics']);self.assertEqual(report['aggregate']['false_positive_components'],0)


try:
    import torch
    import torchvision
    TORCH=True
except ImportError:TORCH=False


@unittest.skipUnless(TORCH,'isolated PyTorch runtime required')
class ConsumerTests(Fixture):
    def test_actual_native_prediction_keeps_valid_pixels(self):
        from train_pad_refinement import native_prediction
        class Model(torch.nn.Module):
            def forward(self,x):return x[:,3:4]*40-20
        actual=native_prediction(Model(),self.dataset,self.manifest,'TEST-01','cpu')
        np.testing.assert_array_equal(actual,np.ones((6,8),bool))

    def test_later_bad_source_preflight_before_model_ledger_and_output(self):
        import infer_pad_refinement as inference
        source,crop,_=self.asset('TEST-02',1);self.manifest['sources'].append(source);self.manifest['crops'].append(crop)
        Image.fromarray(np.full((1,8),255,np.uint8)).save(source['body_path'])
        (self.dataset/'manifest.private.json').write_text(json.dumps(self.manifest))
        output=self.root/'output';model=self.root/'model';model.mkdir()
        with patch.object(inference,'load_final',side_effect=AssertionError('model loaded')) as loader:
            with self.assertRaises(ValueError):inference.run(model,self.dataset,output,True)
            loader.assert_not_called()
        self.assertFalse(output.exists());self.assertFalse((model/'GT7_one_shot_started.json').exists())

    def test_invalid_one_shot_scope_before_model_or_ledger(self):
        import infer_pad_refinement as inference
        (self.dataset/'manifest.private.json').write_text(json.dumps(self.manifest))
        model=self.root/'model';model.mkdir();(model/'final_config.json').write_text('{}')
        with patch.object(inference,'load_final',side_effect=AssertionError('model loaded')) as loader:
            with self.assertRaisesRegex(ValueError,'exact_GT7'):inference.run(model,self.dataset,self.root/'output',True)
            loader.assert_not_called()
        self.assertFalse((model/'GT7_one_shot_started.json').exists())

    def test_crop_mutation_after_preflight_blocks_real_torch_forward(self):
        from train_pad_refinement import native_prediction
        check_dataset(self.dataset,self.manifest,'inference')
        arrays=copy.deepcopy(self.arrays);arrays['coarse'][:]=0
        np.savez_compressed(self.dataset/self.crop['path'],**arrays)
        model=torch.nn.Identity()
        with patch.object(model,'forward',side_effect=AssertionError('forward reached')) as forward:
            with self.assertRaisesRegex(ValueError,'hash_mismatch'):native_prediction(model,self.dataset,self.manifest,'TEST-01','cpu')
            forward.assert_not_called()

    def test_nonfinite_or_wrong_shape_logits_rejected(self):
        from train_pad_refinement import native_prediction
        for output in [torch.full((1,1,256,256),float('nan')),torch.zeros((1,1,1,256))]:
            class Model(torch.nn.Module):
                def forward(self,x):return output
            with self.assertRaisesRegex(ValueError,'logits_contract'):
                native_prediction(Model(),self.dataset,self.manifest,'TEST-01','cpu')

    def test_training_preflight_blocks_missing_reserved_hashes_before_model(self):
        import train_pad_refinement as training
        self.GT();self.manifest.update(purpose='training',GT_present=True,GT7_source_hashes=[])
        (self.dataset/'manifest.private.json').write_text(json.dumps(self.manifest))
        with patch.object(training,'folds',return_value=[]),patch.object(training,'build_pretrained',side_effect=AssertionError('model built')) as builder:
            with self.assertRaisesRegex(ValueError,'seven_reserved_test'):
                training.train(self.dataset,self.root/'weights.pth',self.root/'training')
            builder.assert_not_called()
        self.assertFalse((self.root/'training').exists())

    def test_synthetic_backward_keeps_frozen_encoder_and_BN(self):
        from pad_refinement_model import synthetic_test_model,bce_dice
        from train_pad_refinement import optimizer
        torch.set_num_threads(2);torch.manual_seed(9);model=synthetic_test_model().train()
        frozen={name:p.detach().clone() for name,p in model.encoder.named_parameters() if not p.requires_grad}
        buffers={name:b.detach().clone() for name,b in model.encoder.named_buffers()}
        old=model.head[-1].weight.detach().clone();opt=optimizer(model)
        x=torch.randn((1,4,256,256));target=torch.zeros((1,1,256,256));target[:,:,90:180,70:150]=1
        loss=bce_dice(model(x),target);loss.backward()
        self.assertTrue(torch.isfinite(loss));self.assertTrue(torch.isfinite(model.encoder[0][0].weight.grad).all())
        opt.step()
        self.assertFalse(torch.equal(old,model.head[-1].weight))
        for name,p in model.encoder.named_parameters():
            if name in frozen:self.assertTrue(torch.equal(frozen[name],p));self.assertIsNone(p.grad)
        for name,b in model.encoder.named_buffers():self.assertTrue(torch.equal(buffers[name],b))


if __name__=='__main__':unittest.main()
