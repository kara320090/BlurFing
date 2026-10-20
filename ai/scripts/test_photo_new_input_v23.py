import io
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageOps

import photo_new_input_v23 as app
import test_photo_visibility_reviewed_apply_v1 as fixtures


def encoded(array, orientation=1):
    stream = io.BytesIO()
    exif = Image.Exif()
    exif[274] = orientation
    Image.fromarray(array).save(stream, format='PNG', exif=exif)
    return stream.getvalue()


class NewPhotoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.session = app.Session(self.root / 'session')
        self.rgb, _, _ = fixtures.ReviewedApplyTests().fixture()
        self.raw = encoded(self.rgb)
        self.session.upload(self.raw, '../../private/name.png')

    def tearDown(self):
        if self.session.thread:
            self.session.thread.join(30)
        self.temp.cleanup()

    def bind(self, **kw):
        c = self.session.current
        return dict(id=c['id'], revision=c['revision'], **kw)

    def edit(self, **kw):
        return self.session.edit(self.bind(**kw))

    def polygon(self, x=12):
        return [[x, 12], [x+64, 12], [x+64, 115], [x, 115]]

    def selected(self):
        self.edit(action='new', points=self.polygon())
        self.edit(action='decision', region_id=1, decision='visible')
        self.edit(action='new', points=self.polygon(97))

    def finish(self):
        self.session.thread.join(60)
        self.assertFalse(self.session.thread.is_alive())
        self.assertIsNone(self.session.busy)

    def test_orientation_rgba_gray_and_native_size(self):
        for orientation in range(1, 9):
            raw = encoded(self.rgb, orientation)
            self.session.upload(raw, 'EXIF.png')
            with Image.open(io.BytesIO(raw)) as image:
                expected = np.asarray(ImageOps.exif_transpose(image))
            c = self.session.current
            np.testing.assert_array_equal(c['rgb'], expected)
            self.assertEqual((c['folder']/'original.upload').read_bytes(), raw)
            with Image.open(c['folder']/'canonical.png') as image:
                self.assertEqual(image.getexif()[274], 1)
        rgba = np.concatenate((self.rgb, np.full((*self.rgb.shape[:2], 1), 128, np.uint8)), axis=2)
        self.session.upload(encoded(rgba), 'alpha.png')
        expected = ((self.rgb.astype(np.uint32)*128+255*127+127)//255).astype(np.uint8)
        np.testing.assert_array_equal(self.session.current['rgb'], expected)
        self.session.upload(encoded(self.rgb[:, :, 0]), 'gray.png')
        np.testing.assert_array_equal(self.session.current['rgb'][:, :, 2], self.rgb[:, :, 0])

    def test_failed_upload_preserves_previous_and_no_Gt_creation(self):
        previous = self.session.current
        for raw in (b'not an image', encoded(self.rgb, 0)):
            with self.assertRaises((ValueError, Image.UnidentifiedImageError)):
                self.session.upload(raw, 'bad.png')
            self.assertIs(self.session.current, previous)
        self.assertEqual(previous['name'], 'name.png')
        self.assertFalse(list(self.root.rglob('*ground_truth*')))

    def test_phone_mpo_uses_only_primary_image_and_records_auxiliary_frames(self):
        stream = io.BytesIO()
        Image.fromarray(self.rgb).save(stream, format='MPO', save_all=True,
                                     append_images=[Image.fromarray(self.rgb[::-1])])
        raw = stream.getvalue()
        with Image.open(io.BytesIO(raw)) as image:
            self.assertEqual(image.n_frames, 2)
            primary = np.array(image.convert('RGB'))
        state = self.session.upload(raw, 'phone.JPG')
        np.testing.assert_array_equal(self.session.current['rgb'], primary)
        self.assertTrue(state['photo']['primary_frame_only'])
        self.assertEqual(self.session.current['identity']['frame_used'], 0)
        self.assertEqual((self.session.current['folder']/'original.upload').read_bytes(), raw)

    def test_revision_overlap_coordinate_undo_and_visibility_reset(self):
        stale = self.bind(action='new', points=self.polygon())
        self.edit(action='new', points=self.polygon())
        self.assertEqual(self.session.current['decisions'][1], 'uncertain')
        with self.assertRaisesRegex(ValueError, 'stale'):
            self.session.edit(stale)
        with self.assertRaisesRegex(ValueError, 'overlaps'):
            self.edit(action='new', points=self.polygon(20))
        with self.assertRaisesRegex(ValueError, 'outside'):
            self.edit(action='new', points=[[-1, 0], [20, 0], [20, 20]])
        self.edit(action='decision', region_id=1, decision='visible')
        self.edit(action='erase', region_id=1, points=[[12, 12], [20, 12], [20, 25]])
        self.assertEqual(self.session.current['decisions'][1], 'uncertain')
        self.edit(action='undo')
        self.assertEqual(self.session.current['decisions'][1], 'visible')
        self.assertEqual(int((self.session.current['labels'] > 0).sum()), 65*104)
        self.edit(action='delete', region_id=1)
        self.assertFalse(self.session.current['regions'])

    def test_real_v23_saved_output_is_source_bound_and_outside_is_identical(self):
        self.selected()
        with self.assertRaisesRegex(ValueError, 'confirmation'):
            self.session.start_job(self.bind(confirmed=False), 'apply')
        self.session.start_job(self.bind(confirmed=True), 'apply', seed=41)
        self.finish()
        self.assertIsNone(self.session.error)
        c = self.session.current
        result = c['result']
        self.assertEqual(result['applied_regions'], 1)
        self.assertEqual(result['review_required'], 1)
        out = Path(result['path'])
        with Image.open(out/'returned.png') as image:
            rgb = np.array(image)
        with Image.open(out/'applied_mask.png') as image:
            mask = np.asarray(image) > 0
        np.testing.assert_array_equal(mask, c['labels'] == 1)
        np.testing.assert_array_equal(rgb[~mask], self.rgb[~mask])
        self.assertTrue(np.any(rgb[mask] != self.rgb[mask]))
        self.assertFalse((out/'INCOMPLETE.txt').exists())
        report = json.loads((out/'result.private.json').read_text('utf-8'))
        self.assertEqual(report['appearance'], 'junction_v23')
        self.assertFalse(report['training_GT'])
        self.assertFalse(report['privacy_validated'])
        self.edit(action='decision', region_id=1, decision='uncertain')
        self.assertIsNone(self.session.current['result'])
        self.assertTrue((out/'returned.png').exists())
        with self.assertRaisesRegex(ValueError, 'no_explicit_visible'):
            self.session.start_job(self.bind(confirmed=True), 'apply')

    def test_busy_and_input_tamper_do_not_publish_a_result(self):
        self.selected()
        self.session.busy = 'detect'
        with self.assertRaisesRegex(ValueError, 'job_running'):
            self.session.upload(self.raw, 'new.png')
        with self.assertRaisesRegex(ValueError, 'job_running'):
            self.edit(action='delete', region_id=1)
        self.session.busy = None
        (self.session.current['folder']/'canonical.png').write_bytes(b'tampered')
        self.session.start_job(self.bind(confirmed=True), 'apply', seed=41)
        self.finish()
        self.assertEqual(self.session.error, 'canonical_input_changed')
        self.assertIsNone(self.session.current['result'])

    def test_failed_edit_storage_keeps_last_complete_revision(self):
        self.selected()
        before = self.session.current
        with patch.object(app, 'json_write', side_effect=OSError('disk full')):
            with self.assertRaisesRegex(OSError, 'disk full'):
                self.edit(action='delete', region_id=1)
        self.assertIs(self.session.current, before)
        self.assertEqual(before['decisions'][1], 'visible')
        self.edit(action='delete', region_id=1)
        self.assertNotIn(1, self.session.current['decisions'])

    def test_failed_detector_does_not_erase_manual_draft(self):
        self.selected()
        before = self.session.current['labels'].copy()
        self.session.detector_available = True
        with patch.object(app.subprocess, 'run', return_value=app.subprocess.CompletedProcess([], 1)):
            self.session.start_job(self.bind(replace_draft=True), 'detect')
            self.finish()
        np.testing.assert_array_equal(before, self.session.current['labels'])
        self.assertIn('manual_edit', self.session.error)

    def test_detector_proposals_require_new_human_decisions(self):
        self.selected()
        self.session.detector_available = True
        def proposal(args, **kwargs):
            folder = Path(args[args.index('--output')+1])
            source = Path(args[args.index('--source')+1])
            mask = np.zeros(self.rgb.shape[:2], np.uint8)
            mask[30:70, 20:65] = 255
            Image.fromarray(mask).save(folder/'proposal.png')
            _, selection = app.review_candidates(mask > 0, mask > 0, np.zeros_like(mask, bool))
            app.json_write(folder/'proposal.private.json', {
                'source_sha256':app.file_hash(source), 'candidate_selection':selection})
            return app.subprocess.CompletedProcess([], 0)
        with self.assertRaisesRegex(ValueError, 'replacing'):
            self.session.start_job(self.bind(), 'detect')
        with patch.object(app.subprocess, 'run', side_effect=proposal):
            self.session.start_job(self.bind(replace_draft=True), 'detect')
            self.finish()
        self.assertIsNone(self.session.error)
        self.assertEqual(self.session.current['decisions'], {1:'uncertain'})
        with self.assertRaisesRegex(ValueError, 'no_explicit_visible'):
            self.session.start_job(self.bind(confirmed=True), 'apply')
        self.edit(action='undo')
        self.assertEqual(self.session.current['decisions'], {1:'visible', 2:'uncertain'})

    def test_corrupt_saved_result_is_not_published(self):
        self.selected()
        save = app.save_final_rgb_png
        def corrupted(*args):
            result = save(*args)
            with Image.open(args[3]) as image:
                altered = np.array(image)
            altered[0, 0] ^= 255
            Image.fromarray(altered).save(args[3])
            return result
        with patch.object(app, 'save_final_rgb_png', side_effect=corrupted):
            self.session.start_job(self.bind(confirmed=True), 'apply', seed=41)
            self.finish()
        self.assertEqual(self.session.error, 'saved_output_verification_failed')
        self.assertIsNone(self.session.current['result'])
        self.assertTrue(list(self.session.current['folder'].glob('apply-*/INCOMPLETE.txt')))

    def test_unanchored_candidates_remain_reviewable_not_automatically_approved(self):
        base = np.zeros((120, 180), bool)
        base[10:65, 10:45] = True
        base[20:85, 90:135] = True
        refined = np.zeros_like(base)
        refined[25:75, 90:130] = True
        base_before, refined_before = base.copy(), refined.copy()
        unanchored = np.zeros_like(base)
        unanchored[:, :60] = True
        selected, report = app.review_candidates(base, refined, unanchored)
        expected = refined.copy()
        expected[10:65, 10:45] = True
        np.testing.assert_array_equal(selected, expected)
        np.testing.assert_array_equal(base, base_before)
        np.testing.assert_array_equal(refined, refined_before)
        self.assertEqual(report['restored_candidate_components'], 1)
        self.assertFalse(report['protection_authorized'])
        self.assertFalse(report['whole_finger_coverage_verified'])
        empty = np.zeros_like(base)
        restored, report = app.review_candidates(base, empty, base)
        np.testing.assert_array_equal(restored, base)
        self.assertEqual(report['restored_candidate_components'], 2)
        restored, report = app.review_candidates(empty, empty, empty)
        self.assertFalse(restored.any())
        self.assertEqual(report['restored_candidate_components'], 0)
        unchanged, report = app.review_candidates(base, refined, empty)
        np.testing.assert_array_equal(unchanged, refined)
        self.assertEqual(report['restored_pixels'], 0)
        with self.assertRaisesRegex(ValueError, 'mask_contract'):
            app.review_candidates(base, empty[:100], empty)

    def test_http_origin_host_token_upload_and_result_contract(self):
        server = app.make_server(self.session)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        origin = 'http://127.0.0.1:' + str(server.server_port)
        def request(route, raw=None, **headers):
            return urllib.request.urlopen(urllib.request.Request(server.url+route, data=raw, headers=headers))
        try:
            with request('') as response:
                self.assertIn('새 사진'.encode(), response.read())
                self.assertIn("frame-ancestors 'none'", response.headers['Content-Security-Policy'])
            for headers in ({'Origin': 'https://example.com'}, {'Origin': origin, 'Host': 'evil.example'}):
                with self.assertRaises(urllib.error.HTTPError):
                    request('api/edit', b'{}', **headers, **{'Content-Type':'application/json'})
            with self.assertRaises(urllib.error.HTTPError):
                urllib.request.urlopen(origin+'/s/wrong/api/state')
            with request('api/upload', self.raw, Origin=origin, **{'Content-Type':'application/octet-stream'}) as response:
                state = json.load(response)
            self.assertEqual(state['photo']['width'], self.rgb.shape[1])
            self.assertFalse(state['photo']['regions'])
            uid = state['photo']['id']
            with request('photo/'+uid+'/original.png') as response:
                with Image.open(io.BytesIO(response.read())) as image:
                    self.assertEqual(image.size, (270,128))
            with self.assertRaises(urllib.error.HTTPError):
                request('photo/'+uid+'/../../original.upload')
            with request('api/stop', b'{}', Origin=origin, **{'Content-Type':'application/json'}) as response:
                self.assertTrue(json.load(response)['stopped'])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(5)


if __name__ == '__main__':
    unittest.main()
