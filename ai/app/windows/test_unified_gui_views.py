"""Synthetic presentation checks; never evidence of detector/matcher accuracy."""
import json
from pathlib import Path
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch
from PIL import Image
import unified_gui


class GUIViewTests(unittest.TestCase):
    def test_status_reason_preview_and_save_for_all_presentations(self):
        try:root=tk.Tk()
        except tk.TclError as exc:self.skipTest('Display unavailable: '+str(exc))
        root.withdraw()
        try:
            app=unified_gui.App(root)
            with tempfile.TemporaryDirectory(prefix='synthetic gui view ') as folder:
                folder=Path(folder);source=folder/'source.png';returned=folder/'returned.png'
                Image.new('RGB',(16,16),(120,100,80)).save(source)
                Image.new('RGB',(16,16),(80,100,120)).save(returned)
                source_bytes=source.read_bytes();app.source=str(source)
                # The actual completion callback is exercised synchronously.
                # Inference is replaced only in this presentation-only test.
                app.job=lambda work,complete:complete(work())
                for status,transformed in [('success',2),('partial_success',1),('rejected',0)]:
                    payload=dict(input_type='photo',status=status,fingerprints_detected=2,fingerprints_transformed=transformed,fingerprints_rejected=2-transformed,output_path=str(returned),regions=[dict(reason='synthetic_pitch_unobserved')])
                    with patch.object(app,'execute',return_value=payload):app.process()
                    root.update_idletasks()
                    self.assertIn(status,app.label.cget('text'))
                    self.assertIn('synthetic_pitch_unobserved',app.text.get('1.0','end'))
                    self.assertIsNotNone(app.photo)
                    destination=folder/(status+'.png')
                    with patch.object(unified_gui.filedialog,'asksaveasfilename',return_value=str(destination)):app.save()
                    self.assertEqual(destination.read_bytes(),returned.read_bytes())
                self.assertEqual(source.read_bytes(),source_bytes)
        finally:root.destroy()


if __name__=='__main__':unittest.main()
