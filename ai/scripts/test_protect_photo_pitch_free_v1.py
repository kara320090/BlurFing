import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import protect_photo_pitch_free_v1 as entry


class PitchFreeEntryContracts(unittest.TestCase):
    def test_flags_are_booleans_before_any_source_or_model_access(self):
        for options in [dict(development_replay='false'),dict(include_observed_pose=1),dict(include_coarse_pad=1)]:
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


if __name__=='__main__':unittest.main()
