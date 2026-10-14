"""Result identity and ordering tests use synthetic images only."""
from pathlib import Path
import tempfile
import threading
import tkinter as tk
import unittest
from unittest.mock import patch
from PIL import Image
import unified_gui


class GUIStateTests(unittest.TestCase):
    def setUp(self):
        try:self.root=tk.Tk()
        except tk.TclError as exc:self.skipTest('Display unavailable: '+str(exc))
        self.root.withdraw();self.addCleanup(self.root.destroy)
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.a=Path(self.folder.name)/'A.png';self.b=Path(self.folder.name)/'B.png'
        Image.new('RGB',(16,16),(140,100,80)).save(self.a)
        Image.new('RGB',(16,16),(100,140,80)).save(self.b)
        self.app=unified_gui.App(self.root);self.root.update_idletasks();self.callbacks=[]
        self.app.job=lambda work,complete:self.callbacks.append(complete)

    def payload(self,path):
        return dict(output_path=str(path),input_type='photo',status='success',fingerprints_detected=1,fingerprints_transformed=1,fingerprints_rejected=0)

    def test_selection_invalidates_preview_and_save(self):
        self.app.source=str(self.a);self.app.process();self.callbacks[-1](self.payload(self.a))
        self.assertEqual(self.app.save_button.cget('state'),'normal')
        with patch.object(unified_gui.filedialog,'askopenfilename',return_value=str(self.b)):self.app.select()
        self.assertIsNone(self.app.output);self.assertIsNone(self.app.photo)
        self.assertEqual(self.app.save_button.cget('state'),'disabled')
        with patch.object(unified_gui.filedialog,'asksaveasfilename') as dialog:self.app.save();dialog.assert_not_called()

    def test_older_completion_cannot_replace_newer_source_result(self):
        self.app.source=str(self.a);self.app.process()
        with patch.object(unified_gui.filedialog,'askopenfilename',return_value=str(self.b)):self.app.select()
        self.app.process();self.callbacks[1](self.payload(self.b));self.callbacks[0](self.payload(self.a))
        self.assertEqual(self.app.output,str(self.b));self.assertEqual(self.app.source,str(self.b))

    def test_reprocessing_same_path_discards_previous_completion(self):
        self.app.source=str(self.a);self.app.process();self.app.process()
        self.callbacks[1](self.payload(self.b));self.callbacks[0](self.payload(self.a))
        self.assertEqual(self.app.output,str(self.b))

    def test_cancel_selection_keeps_current_result(self):
        self.app.source=str(self.a);self.app.process();self.callbacks[-1](self.payload(self.b))
        with patch.object(unified_gui.filedialog,'askopenfilename',return_value=''):self.app.select()
        self.assertEqual(self.app.source,str(self.a));self.assertEqual(self.app.output,str(self.b))


class WorkerOrderingTests(unittest.TestCase):
    def app(self):
        app=unified_gui.App.__new__(unified_gui.App);app._generation=0;app._worker_lock=threading.Lock()
        app.root=type('Callbacks',(),{'after':lambda root,delay,callback:callback()})()
        return app

    def test_worker_jobs_are_serial_and_stale_results_are_ignored(self):
        app=self.app();started=threading.Event();release=threading.Event();second_started=threading.Event();values=[]
        def first():started.set();release.wait(2);return 'old'
        old=app.job(first,values.append);self.assertTrue(started.wait(2));app._generation+=1
        new=app.job(lambda:(second_started.set(),'new')[1],values.append)
        self.assertFalse(second_started.wait(.05));release.set();old.join(2);new.join(2)
        self.assertFalse(old.is_alive());self.assertFalse(new.is_alive());self.assertEqual(values,['new'])

    def test_stale_errors_do_not_interrupt_new_selection(self):
        app=self.app();started=threading.Event();release=threading.Event()
        def failing():started.set();release.wait(2);raise RuntimeError('old request')
        with patch.object(unified_gui.messagebox,'showerror') as dialog:
            worker=app.job(failing,lambda value:None);self.assertTrue(started.wait(2));app._generation+=1
            release.set();worker.join(2);self.assertFalse(worker.is_alive());dialog.assert_not_called()


if __name__=='__main__':unittest.main()
