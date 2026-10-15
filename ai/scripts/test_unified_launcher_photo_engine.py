"""Windows argument transport only; generated probes perform no AI inference."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


@unittest.skipUnless(os.name=='nt' and shutil.which('powershell.exe'),'Windows PowerShell transport requires Windows')
class LauncherPhotoEngineTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory(prefix='unified launcher ');self.addCleanup(self.folder.cleanup)
        self.root=Path(self.folder.name);self.ai=self.root/'ai'
        for relative in ('scripts','app/windows','platform/windows'):(self.ai/relative).mkdir(parents=True)
        original=Path(__file__).resolve().parents[1]/'platform/windows/run_unified.ps1'
        self.launcher=self.ai/'platform/windows/run_unified.ps1';shutil.copyfile(original,self.launcher)
        self.probe="import sys,json\nprint(json.dumps(sys.argv[1:]))\n"
        (self.ai/'scripts/protect_fingerprint.py').write_text(self.probe,encoding='utf-8')
        (self.ai/'app/windows/unified_gui.py').write_text(self.probe,encoding='utf-8')
        self.model=self.root/'private model 폴더';self.model.mkdir()
        self.registry=self.root/'private registry.json';self.registry.write_text('{}')

    def call(self,extra):
        command=['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(self.launcher),
            '-CorePython',sys.executable,'-ColfispoofPython','','-ColfispoofSource','','-ColfispoofModel','',*extra]
        result=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',errors='replace')
        return result,json.loads(result.stdout) if result.returncode==0 else None

    def test_default_CLI_transport_is_exact_legacy_arguments(self):
        result,arguments=self.call(['-InputImage','input photo.png','-OutputDirectory','fresh output'])
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(arguments,['--input','input photo.png','--output','fresh output'])

    def test_native_CLI_preserves_path_arguments_and_explicit_replay(self):
        result,arguments=self.call(['-InputImage','input photo.png','-OutputDirectory','fresh output',
            '-PhotoEngine','native_v12','-PhotoModel',str(self.model),'-ConsumedRegistry',str(self.registry),'-DevelopmentReplay'])
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(arguments,['--input','input photo.png','--output','fresh output',
            '--photo-engine','native_v12','--consumed-registry',str(self.registry),'--photo-model',str(self.model),'--development-replay'])

    def test_distal_GUI_transport_has_registry_and_no_learned_pad_model(self):
        result,arguments=self.call(['-Gui','-PhotoEngine','distal_v13','-ConsumedRegistry',str(self.registry)])
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(arguments,['--photo-engine','distal_v13','--consumed-registry',str(self.registry)])

    def test_ambiguous_and_missing_configuration_never_reaches_probe(self):
        for extra in (['-Gui','-ConsumedRegistry',str(self.registry)],['-Gui','-PhotoEngine','native_v12','-ConsumedRegistry',str(self.registry)],
            ['-Gui','-PhotoEngine','distal_v13','-ConsumedRegistry',str(self.registry),'-PhotoModel',str(self.model)]):
            with self.subTest(extra=extra):
                result,arguments=self.call(extra);self.assertNotEqual(result.returncode,0)
                self.assertIsNone(arguments);self.assertEqual(result.stdout,'')

    def test_pose_CLI_transport_is_explicit_registry_only(self):
        result,arguments=self.call(['-InputImage','photo.png','-OutputDirectory','fresh',
            '-PhotoEngine','pose_v14','-ConsumedRegistry',str(self.registry)])
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(arguments,['--input','photo.png','--output','fresh','--photo-engine','pose_v14','--consumed-registry',str(self.registry)])


if __name__=='__main__':unittest.main()
