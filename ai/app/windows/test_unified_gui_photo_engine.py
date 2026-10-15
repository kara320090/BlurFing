"""Synthetic explicit PHOTO-engine GUI transport and stale-result checks."""
from pathlib import Path
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch
from PIL import Image
import unified_gui


class PhotoEngineGUI(unittest.TestCase):
    def setUp(self):
        try:self.root=tk.Tk()
        except tk.TclError as exc:self.skipTest('Display unavailable: '+str(exc))
        self.root.withdraw();self.addCleanup(self.root.destroy)
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.source=Path(self.folder.name)/'synthetic photo.png';Image.new('RGB',(16,12),(180,100,80)).save(self.source)
        self.app=unified_gui.App(self.root);self.app.source=str(self.source)
        self.payload=dict(input_type='photo',status='partial_success',fingerprints_detected=64,fingerprints_transformed=1,fingerprints_rejected=63,output_path=str(self.source))
        self.root.update_idletasks()

    def tearDown(self):self.root.update_idletasks()

    def native(self):
        self.app.photo_engine.set('native_v12');self.app.photo_model.set('private model');self.app.consumed_registry.set('registry.json')

    def test_default_legacy_adds_no_new_CLI_arguments(self):self.assertEqual(self.app.photo_arguments(),[])

    def test_native_selection_strict_by_default_and_replay_explicit(self):
        self.native();arguments=self.app.photo_arguments()
        self.assertIn('native_v12',arguments);self.assertIn('private model',arguments);self.assertNotIn('--development-replay',arguments)
        self.app.development_replay.set(True);self.assertIn('--development-replay',self.app.photo_arguments())

    def test_distal_does_not_forward_learned_model_and_warns_boundary_review(self):
        self.native();self.app.photo_engine.set('distal_v13');arguments=self.app.photo_arguments()
        self.assertNotIn('--photo-model',arguments);self.assertIn('distal_v13',arguments)
        self.assertIn('boundary review',self.app.label.cget('text'))

    def test_missing_native_configuration_is_shown_without_running(self):
        self.app.photo_engine.set('native_v12')
        with patch.object(self.app,'job') as job,patch.object(unified_gui.messagebox,'showerror') as dialog:self.app.process()
        job.assert_not_called();dialog.assert_called_once()

    def test_pose_selection_does_not_forward_stale_V6_model_and_warns_single_hand(self):
        self.native();self.app.photo_engine.set('pose_v14');arguments=self.app.photo_arguments()
        self.assertEqual(arguments,['--photo-engine','pose_v14','--consumed-registry','registry.json'])
        self.assertNotIn('--photo-model',arguments);self.assertIn('one full hand',self.app.engine_notice())

    def test_configuration_change_invalidates_preview_and_save(self):
        self.app.job=lambda work,complete:complete(work())
        with patch.object(self.app,'execute',return_value=self.payload):self.app.process()
        self.assertIsNotNone(self.app.output);self.assertEqual(self.app.save_button.cget('state'),'normal')
        self.app.photo_engine.set('distal_v13')
        self.assertIsNone(self.app.output);self.assertEqual(self.app.save_button.cget('state'),'disabled')

    def test_process_captures_selected_configuration_and_ignores_old_completion(self):
        self.native();queued=[];self.app.job=lambda work,complete:queued.append((work,complete))
        self.app.process();self.app.photo_engine.set('legacy')
        with patch.object(self.app,'execute',return_value=self.payload) as execute:queued[0][0]()
        self.assertIn('native_v12',execute.call_args.args[1])
        queued[0][1](self.payload);self.assertIsNone(self.app.output)

    def test_process_and_benchmark_use_the_same_explicit_engine(self):
        self.native();self.app.development_replay.set(True);self.app.job=lambda work,complete:complete(work())
        with patch.object(self.app,'execute',return_value=self.payload) as execute:
            self.app.process();self.app.benchmark()
        self.assertEqual(execute.call_count,12)
        for call in execute.call_args_list:
            self.assertIn('native_v12',call.args[1]);self.assertIn('--development-replay',call.args[1])
        self.assertIn('candidate regions 64',self.app.label.cget('text'))


if __name__=='__main__':unittest.main()
