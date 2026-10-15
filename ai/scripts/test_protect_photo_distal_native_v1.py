import json,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
import protect_photo_distal_native_v1 as pipeline
import protect_photo_whole_pad_context_native_v1 as learned
from test_pad_refinement_tiles_v3 import TileFixture
from pad_refinement_data_contract_v2 import read_source_rgb
import pad_refinement_tiles_v3 as tiles


class DistalNativeContracts(TileFixture):
    def rows(self):
        row={k:v for k,v in self.inputs[0].items() if k!='GT_folder'}
        row.update(acquisition_group='unknown',group_provenance='user_input_unverified')
        return [row]

    def reject(self,source,mask,sha,*,detect_only):
        self.assertEqual(sha,pipeline.pixel_hash(mask))
        expected=pipeline.read_mask(source['coarse_path'],source['coarse_sha256'],pipeline.native_shape(source))
        np.testing.assert_array_equal(mask,expected)
        rgb=read_source_rgb(source['source_path'],source['source_sha256'])
        return rgb,dict(status='rejected',source_id=source['source_id'],source_exif_orientation=source['source_exif_orientation'],
            returned_RGB_sha256=pipeline.pixel_hash(rgb),fingerprints_detected=0,fingerprints_transformed=0,fingerprints_rejected=0,regions=[])

    def test_existing_coarse_is_bound_without_loading_or_inferring_V6(self):
        tiles.prepare(self.rows(),self.registry,self.output,'inference')
        with (patch.object(pipeline,'evaluate_learned_mask',side_effect=self.reject) as evaluate,
              patch.object(learned,'load_model',side_effect=AssertionError('V6 model loaded')),
              patch.object(learned,'infer',side_effect=AssertionError('V6 inference run'))):
            report=pipeline.protect_prepared(self.output,self.root/'result',detect_only=True)
        self.assertEqual(evaluate.call_count,1)
        self.assertFalse(report['V6_learned_pad_model_used']);self.assertFalse(report['GT_used'])
        self.assertEqual(report['permission_source'],pipeline.PERMISSION)
        self.assertFalse(report['independent_final_test']);self.assertFalse(report['approved_for_protection'])

    def test_bad_flags_and_existing_output_stop_before_IO(self):
        for flag in ['false',1,None]:
            with self.assertRaisesRegex(ValueError,'boolean'):pipeline.run('unused','unused','unused',development_replay=flag)
            with self.assertRaisesRegex(ValueError,'boolean'):pipeline.run('unused','unused','unused',detect_only=flag)
        with self.assertRaises(FileExistsError):pipeline.protect_prepared('unused',self.root)

    def test_GT_or_coarse_tamper_rejected_before_gate(self):
        view=tiles.prepare(self.rows(),self.registry,self.output,'inference')
        coarse=Path(view['sources'][0]['coarse_path']);coarse.write_bytes(b'not a mask')
        with patch.object(pipeline,'evaluate_learned_mask') as evaluate:
            with self.assertRaises(ValueError):pipeline.protect_prepared(self.output,self.root/'result')
        evaluate.assert_not_called();self.assertFalse((self.root/'result').exists())

    def test_consumed_default_strict_and_explicit_cached_replay_labels_all_outputs(self):
        source=Path(self.inputs[0]['source_path']);identity=tiles.image_identity(source)
        self.registry[0].update(identity);registry=self.root/'registry.json'
        registry.write_text(json.dumps(self.registry),encoding='utf-8')
        output=self.root/'result'
        with patch.object(pipeline,'protect_prepared') as protect:
            with self.assertRaisesRegex(ValueError,'decoded_pixels'):pipeline.run(source,registry,output)
        protect.assert_not_called();self.assertFalse(output.exists())
        before=source.read_bytes();reg_before=registry.read_bytes()
        semantic_path=Path(self.inputs[0]['semantics'])/'semantics.json'
        semantic=json.loads(semantic_path.read_text(encoding='utf-8'))
        semantic.update(image_height=6,image_width=8)
        semantic_path.write_text(json.dumps(semantic),encoding='utf-8')
        with (patch.object(pipeline.shared,'route_input',return_value=dict(input_type='PHOTO')),
              patch.object(pipeline,'evaluate_learned_mask',side_effect=self.reject),
              patch.object(learned,'load_model',side_effect=AssertionError('V6 loaded'))):
            returned,report=pipeline.run(source,registry,output,photo_semantics=self.inputs[0]['semantics'],development_replay=True)
        self.assertEqual(source.read_bytes(),before);self.assertEqual(registry.read_bytes(),reg_before)
        np.testing.assert_array_equal(returned,np.asarray(Image.open(source)))
        self.assertTrue(report['development_replay']);self.assertTrue(report['consumed_source_detected'])
        self.assertFalse(report['privacy_validated']);self.assertFalse(report['V6_learned_pad_model_used'])
        for path in [output/'result.private.json',output/'private/protection/protection.private.json',output/'private/protection/INPUT/result.private.json']:
            value=json.loads(path.read_text(encoding='utf-8'))
            self.assertTrue(value['development_replay']);self.assertFalse(value['independent_final_test'])
        with self.assertRaisesRegex(ValueError,'decoded_pixels'):tiles.exclude_consumed(identity,self.registry)


if __name__=='__main__':unittest.main()
