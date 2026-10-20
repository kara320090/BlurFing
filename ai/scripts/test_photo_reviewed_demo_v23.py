import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
import photo_reviewed_demo_v23 as demo
import test_photo_visibility_reviewed_apply_v1 as fixtures


class DemoTests(unittest.TestCase):
    def test_actual_saved_report_links_masks_and_immutable_review(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = fixtures.ReviewedApplyTests().reviewed_project(root/'source', 6)
            original, _ = project.arrays('SYNTH-001')
            state_before = {str(p):p.read_bytes() for p in project.state.rglob('*.json')}
            result = demo.run(project.roster_path, project.state, root/'out',
                              source_ids=['SYNTH-001'], seed=31)
            self.assertEqual(result['applied_regions'], 1)
            self.assertEqual(result['review_required'], 1)
            self.assertFalse(result['privacy_validated'])
            self.assertFalse((root/'out/INCOMPLETE.txt').exists())
            text = (root/'out/report.html').read_text('utf-8')
            self.assertIn('불확실', text)
            for ref in re.findall(r'(?:href|src)="([^"]+)"', text):
                self.assertTrue((root/'out'/ref).is_file(), ref)
            with Image.open(root/'out/previews/SYNTH-001-original.png') as image:
                self.assertEqual(image.size, (original.shape[1], original.shape[0]))
            self.assertEqual(state_before, {str(p):p.read_bytes() for p in project.state.rglob('*.json')})
            with self.assertRaises(FileExistsError):
                demo.run(project.roster_path, project.state, root/'out', source_ids=['SYNTH-001'])

    def test_damaged_saved_result_not_published_as_complete(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = fixtures.ReviewedApplyTests().reviewed_project(root/'source', 1)
            real_batch = demo.run_batch
            def damage(*args, **kwargs):
                batch = real_batch(*args, **kwargs)
                path = Path(args[2])/'SYNTH-001/returned.png'
                with Image.open(path) as image:
                    data = np.array(image)
                data[0,0] ^= 255
                Image.fromarray(data).save(path)
                return batch
            with patch.object(demo, 'run_batch', side_effect=damage), self.assertRaisesRegex(RuntimeError, 'verification'):
                demo.run(project.roster_path, project.state, root/'out', source_ids=['SYNTH-001'], seed=31)
            self.assertTrue((root/'out/INCOMPLETE.txt').exists())
            self.assertFalse((root/'out/report.html').exists())

    def test_missing_explicit_selection_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'out'
            with self.assertRaisesRegex(ValueError, 'selection'):
                demo.run('missing', 'missing', path, source_ids=[])
            self.assertFalse(path.exists())


if __name__ == '__main__':
    unittest.main()
