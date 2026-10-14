"""Real child transport regression; no Tk window or biometric inputs needed."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import unified_gui


class GUITransportTests(unittest.TestCase):
    def test_unicode_json_and_child_diagnostics(self):
        with tempfile.TemporaryDirectory(prefix='gui transport ') as folder:
            root=Path(folder);(root/'scripts').mkdir()
            (root/'scripts'/'probe.py').write_text(
                "import sys,json\nsys.stdout.reconfigure(encoding='utf-8')\n"
                "sys.stderr.reconfigure(encoding='utf-8')\n"
                "print('진행 정보',file=sys.stderr)\n"
                "print(json.dumps({'status':'rejected','reason':'피치 미관측'},ensure_ascii=False))\n",
                encoding='utf-8')
            with patch.object(unified_gui,'ROOT',root),patch.dict(os.environ,{'BLURFING_CORE_PYTHON':sys.executable}):
                result=unified_gui.App.__new__(unified_gui.App).execute('probe.py',[])
            self.assertEqual(result,dict(status='rejected',reason='피치 미관측'))

    def test_child_error_is_not_reported_as_success(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'scripts').mkdir()
            (root/'scripts'/'probe.py').write_text("print('{\"status\":\"error\",\"error\":\"synthetic_failure\"}')\nraise SystemExit(1)\n")
            with patch.object(unified_gui,'ROOT',root),patch.dict(os.environ,{'BLURFING_CORE_PYTHON':sys.executable}):
                with self.assertRaisesRegex(RuntimeError,'synthetic_failure'):
                    unified_gui.App.__new__(unified_gui.App).execute('probe.py',[])


if __name__=='__main__':unittest.main()
