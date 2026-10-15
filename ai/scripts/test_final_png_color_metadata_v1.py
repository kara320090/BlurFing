"""Synthetic ICC/final-file contracts; no detector, model or renderer execution."""
import hashlib,json,tempfile,unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image,ImageCms
import final_png_color_metadata_v1 as color
from pad_refinement_data_contract_v2 import digest,read_source_rgb


def synthetic_profile():return ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()


class FinalPNGContracts(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.rgb=np.arange(12*16*3,dtype=np.uint8).reshape(12,16,3);self.profile=synthetic_profile()

    def source(self,mode='RGB',icc=None,orientation=1):
        data=self.rgb if mode=='RGB' else self.rgb[:,:,0] if mode=='L' else np.dstack([self.rgb,np.full((12,16),127,np.uint8)])
        image=Image.fromarray(data);exif=Image.Exif();exif[274]=orientation
        source=self.root/('source-'+mode+'.png');image.save(source,exif=exif,**({'icc_profile':icc}if icc is not None else {}))
        return source

    def test_profile_free_final_is_byte_identical_to_old_encoder(self):
        for mode in ['RGB','L','RGBA']:
            for orientation in range(1,9):
                source=self.source(mode,orientation=orientation)
                from protect_photo_whole_pad_context_native_v1 import canonical_rgb
                rgb,_=canonical_rgb(source);before=source.read_bytes();exif=Image.Exif();exif[274]=orientation
                old=self.root/'old.png';Image.fromarray(rgb).save(old,exif=exif)
                final=self.root/f'final-{mode}-{orientation}.png'
                metadata=color.save_final_rgb_png(source,digest(source),rgb,final,orientation)
                self.assertEqual(final.read_bytes(),old.read_bytes());self.assertEqual(source.read_bytes(),before)
                self.assertFalse(metadata['source_ICC_present']);self.assertIsNone(metadata['returned_ICC_profile_sha256'])

    def test_RGB_profile_bytes_pixels_and_EXIF_are_preserved_without_transform(self):
        for orientation in range(1,9):
            source=self.source(icc=self.profile,orientation=orientation);before=source.read_bytes();rgb=self.rgb.copy();expected=rgb.copy()
            with patch.object(color.ImageCms,'profileToProfile',side_effect=AssertionError('final RGB converted')):
                metadata=color.save_final_rgb_png(source,digest(source),rgb,self.root/f'final-{orientation}.png',orientation)
            with Image.open(self.root/f'final-{orientation}.png')as image:
                self.assertEqual(image.info['icc_profile'],self.profile);self.assertEqual(image.getexif()[274],orientation)
                np.testing.assert_array_equal(np.asarray(image),expected)
            np.testing.assert_array_equal(rgb,expected);self.assertEqual(source.read_bytes(),before)
            self.assertEqual(metadata['source_ICC_profile_sha256'],hashlib.sha256(self.profile).hexdigest())
            self.assertFalse(metadata['returned_RGB_color_samples_converted'])

    def test_RGBA_uses_existing_white_composite_then_preserves_RGB_profile(self):
        source=self.source('RGBA',self.profile);before=source.read_bytes()
        from protect_photo_whole_pad_context_native_v1 import canonical_rgb
        rgb,identity=canonical_rgb(source);expected=((self.rgb.astype(np.uint32)*127+255*128+127)//255).astype(np.uint8)
        np.testing.assert_array_equal(rgb,expected)
        final=self.root/'final.png';color.save_final_rgb_png(source,identity['original_source_sha256'],rgb,final,1)
        with Image.open(final)as image:
            self.assertEqual(image.mode,'RGB');self.assertEqual(image.info['icc_profile'],self.profile);np.testing.assert_array_equal(np.asarray(image),expected)
        self.assertEqual(source.read_bytes(),before)

    def test_invalid_and_nonRGB_profiles_are_never_copied(self):
        gray_header=bytearray(self.profile);gray_header[16:20]=b'GRAY'
        for profile,reason in [(b'fake ICC','invalid_source'),(bytes(gray_header),'colorspace_not_supported')]:
            source=self.source(icc=profile);target=self.root/'bad-final.png'
            with self.assertRaisesRegex(ValueError,reason):color.save_final_rgb_png(source,digest(source),self.rgb,target,1)
            self.assertFalse(target.exists())
        source=self.source('L',self.profile)
        with self.assertRaisesRegex(ValueError,'mode_not_supported'):color.save_final_rgb_png(source,digest(source),self.rgb,self.root/'gray-final.png',1)
        self.assertFalse((self.root/'gray-final.png').exists())

    def test_source_hash_includes_profile_and_stale_binding_rejects(self):
        source=self.source(icc=self.profile);old=digest(source);self.source(icc=None)
        with self.assertRaisesRegex(ValueError,'source_hash'):color.save_final_rgb_png(source,old,self.rgb,self.root/'final.png',1)
        self.assertFalse((self.root/'final.png').exists())

    def test_source_race_after_write_removes_unverified_fresh_final(self):
        source=self.source(icc=self.profile);target=self.root/'final.png';expected=digest(source);original=Image.Image.save
        def save(image,fp,*args,**kwargs):
            result=original(image,fp,*args,**kwargs)
            if getattr(fp,'name',None)==str(target):original(Image.fromarray(self.rgb^1),source)
            return result
        with patch.object(Image.Image,'save',new=save),self.assertRaisesRegex(ValueError,'source_hash'):
            color.save_final_rgb_png(source,expected,self.rgb,target,1)
        self.assertFalse(target.exists())

    def test_encoder_profile_loss_is_detected_and_cleaned(self):
        source=self.source(icc=self.profile);target=self.root/'final.png';original=Image.Image.save
        def drop(image,fp,*args,**kwargs):
            kwargs.pop('icc_profile',None);return original(image,fp,*args,**kwargs)
        with patch.object(Image.Image,'save',new=drop),self.assertRaisesRegex(ValueError,'roundtrip'):
            color.save_final_rgb_png(source,digest(source),self.rgb,target,1)
        self.assertFalse(target.exists())

    def test_existing_file_and_invalid_array_or_geometry_never_overwrite(self):
        source=self.source();target=self.root/'final.png';target.write_bytes(b'keep')
        with self.assertRaises(FileExistsError):color.save_final_rgb_png(source,digest(source),self.rgb,target,1)
        self.assertEqual(target.read_bytes(),b'keep')
        for bad,orientation,reason in [(self.rgb.astype(np.float32),1,'uint8'),(self.rgb[:2],1,'shape_or_EXIF'),(self.rgb,6,'shape_or_EXIF')]:
            with self.assertRaisesRegex(ValueError,reason):color.save_final_rgb_png(source,digest(source),bad,self.root/'bad.png',orientation)
        self.assertFalse((self.root/'bad.png').exists())

    def test_profile_free_final_retains_strict_HTTP_RGB_contract(self):
        from photo_experimental_transport_v1 import decode_request_png
        source=self.source();target=self.root/'final.png';color.save_final_rgb_png(source,digest(source),self.rgb,target,1)
        np.testing.assert_array_equal(decode_request_png(target.read_bytes()),self.rgb)


class FinalEntryContracts(unittest.TestCase):
    def test_all_three_entries_change_only_final_metadata(self):
        from test_pad_refinement_tiles_v3 import TileFixture
        import protect_photo_whole_pad_context_native_v1 as native
        import protect_photo_distal_native_v1 as distal
        import protect_photo_pose_native_v1 as pose_entry
        import photo_pose_native_pipeline_v1 as pose
        import mediapipe_hand_worker_v1 as hand
        for engine,pipeline in [('native_v12',native),('distal_v13',distal),('pose_v14',pose_entry)]:
            with self.subTest(engine=engine):
                fixture=TileFixture();fixture.setUp();self.addCleanup(fixture.doCleanups)
                source=Path(fixture.inputs[0]['source_path']);profile=synthetic_profile()
                with Image.open(source)as image:rgb=np.asarray(image).copy()
                Image.fromarray(rgb).save(source,icc_profile=profile);original_source=source.read_bytes()
                semantics=Path(fixture.inputs[0]['semantics']);meta=json.loads((semantics/'semantics.json').read_text())
                meta.update(source_sha256=digest(source),image_height=6,image_width=8);(semantics/'semantics.json').write_text(json.dumps(meta))
                registry=fixture.root/'registry.json';registry.write_text(json.dumps(fixture.registry));outputs=[]
                def protected(*args,**kwargs):
                    folder=Path(args[2]if engine=='native_v12'else args[1]);(folder/'INPUT').mkdir(parents=True)
                    Image.fromarray(rgb).save(folder/'INPUT/returned.png')
                    return dict(rows=[dict(returned_RGB_sha256=hashlib.sha256(rgb.tobytes()).hexdigest(),fingerprints_rejected=0,
                        status='rejected',fingerprints_detected=0,fingerprints_transformed=0,changed_pixels=0,regions=[])],model_sha256='synthetic')
                def legacy(source,sha,returned,target,orientation):
                    exif=Image.Exif();exif[274]=orientation;Image.fromarray(returned).save(target,exif=exif);return {}
                task=fixture.root/'synthetic.task';task.write_bytes(b'synthetic no hand model')
                def worker(command,**kwargs):
                    inp=Path(command[command.index('--input')+1]);out=Path(command[command.index('--output')+1]);hand.run(inp,task,out)
                for name,writer in [('old',legacy),('new',color.save_final_rgb_png)]:
                    output=fixture.root/name
                    with ExitStack()as stack:
                        stack.enter_context(patch.object(pipeline,'save_final_rgb_png',side_effect=writer))
                        stack.enter_context(patch.object(pipeline.shared,'route_input',return_value=dict(input_type='PHOTO')))
                        if engine=='native_v12':
                            stack.enter_context(patch.object(pipeline,'load_model',return_value=(object(),dict(consumed_registry_sha256=pipeline.hash_json(fixture.registry)))))
                            stack.enter_context(patch.object(pipeline,'protect_bundle',side_effect=protected))
                            returned,report=pipeline.run(source,fixture.root/'unused-model',registry,output,photo_semantics=semantics)
                        elif engine=='distal_v13':
                            stack.enter_context(patch.object(pipeline,'protect_prepared',side_effect=protected))
                            returned,report=pipeline.run(source,registry,output,photo_semantics=semantics)
                        else:
                            stack.enter_context(patch.object(pipeline,'hand_configuration',return_value=['unused',str(task)]))
                            stack.enter_context(patch.object(hand,'MODEL_SHA256',hand.digest(task)))
                            stack.enter_context(patch.object(hand,'_detect',return_value=([],dict(mediapipe_version=hand.MEDIAPIPE_VERSION))))
                            stack.enter_context(patch.object(pipeline.subprocess,'run',side_effect=worker))
                            stack.enter_context(patch.object(pose.base,'evaluate_learned_mask',side_effect=AssertionError('renderer used')))
                            returned,report=pipeline.run(source,registry,output,photo_semantics=semantics)
                    np.testing.assert_array_equal(returned,rgb);self.assertEqual(source.read_bytes(),original_source)
                    with Image.open(output/'returned.png')as image:self.assertEqual(image.info.get('icc_profile'),profile if name=='new'else None)
                    with Image.open(output/'private/canonical_input.png')as image:self.assertNotIn('icc_profile',image.info)
                    artifacts={}
                    for path in (output/'private').rglob('*'):
                        if path.is_file():
                            data=path.read_bytes()
                            if path.suffix=='.json':data=data.replace(str(output).encode(),b'RUN').replace(str(output).replace('\\','\\\\').encode(),b'RUN')
                            artifacts[str(path.relative_to(output/'private'))]=hashlib.sha256(data).hexdigest()
                    outputs.append((artifacts,report))
                self.assertEqual(outputs[0][0],outputs[1][0])
                for field in ['status','fingerprints_detected','fingerprints_transformed','fingerprints_rejected','changed_pixels','returned_RGB_sha256']:
                    self.assertEqual(outputs[0][1][field],outputs[1][1][field])


if __name__=='__main__':unittest.main()
