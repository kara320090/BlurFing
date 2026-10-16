import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import protect_photo_pitch_free_v1 as entry


class PitchFreeEntryContracts(unittest.TestCase):
    def test_flags_are_booleans_before_any_source_or_model_access(self):
        for options in [dict(development_replay='false'),dict(include_observed_pose=1),dict(include_coarse_pad=1),dict(complete_holes=1),dict(allow_scanner=1)]:
            with patch.object(entry,'capture_runtime_sources') as capture:
                with self.assertRaisesRegex(ValueError,'flag_must_be_boolean'):
                    entry.run('missing.png','missing-model','missing.json','unused-output',**options)
                capture.assert_not_called()

    def test_existing_output_is_not_overwritten_even_for_invalid_input(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'result';target.mkdir();sentinel=target/'keep.txt';sentinel.write_text('keep')
            with patch.object(entry,'capture_runtime_sources') as capture:
                with self.assertRaisesRegex(FileExistsError,'fresh_output_required'):
                    entry.run('missing.png','missing-model','missing.json',target)
                capture.assert_not_called();self.assertEqual(sentinel.read_text(),'keep')

    def test_scanner_dispatch_precedes_photo_model_loading_and_unknown_does_not_fallback(self):
        import json
        import numpy as np
        from PIL import Image
        from test_pad_refinement_tiles_v3 import TileFixture
        import sys,types
        from unittest.mock import Mock
        inference=types.ModuleType('infer_whole_pad_context_v6');inference.load_model=Mock();inference.run=Mock()
        import scanner_fingerprint_detector as scanner
        fixture=TileFixture();fixture.setUp();self.addCleanup(fixture.doCleanups)
        source=fixture.root/'gray.png';Image.fromarray(np.full((32,32),127,np.uint8)).save(source)
        registry=fixture.root/'registry.json';registry.write_text(json.dumps(fixture.registry))
        with patch.dict(sys.modules,{'infer_whole_pad_context_v6':inference}),patch.object(entry.shared,'route_input',return_value=dict(input_type='FINGERPRINT_IMAGE')),patch.object(inference,'load_model') as model,patch.object(scanner,'detect_scanner',return_value=([],dict(status='rejected',reject_reason='synthetic_no_ROI'))):
            returned,report=entry.run(source,'unused-model',registry,fixture.root/'scanner',allow_scanner=True)
            model.assert_not_called();self.assertEqual(report['input_type'],'FINGERPRINT_IMAGE')
            self.assertEqual(report['status'],'no_mask_original_returned');self.assertTrue(report['review_required'])
            self.assertFalse(report['whole_photo_protection_verified']);self.assertTrue(np.all(returned==127))
            with self.assertRaisesRegex(ValueError,'requires_scanner_mode'):entry.run(source,'unused',registry,fixture.root/'photo-only')
        with patch.object(entry.shared,'route_input',return_value=dict(input_type='UNKNOWN')):
            with self.assertRaisesRegex(ValueError,'uncertain_review_required'):entry.run(source,'unused',registry,fixture.root/'unknown',allow_scanner=True)
        self.assertFalse((fixture.root/'unknown').exists())


if __name__=='__main__':unittest.main()
