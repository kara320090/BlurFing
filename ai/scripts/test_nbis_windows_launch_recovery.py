import unittest
import json
import hashlib
import subprocess
import tempfile
from pathlib import Path
from PIL import Image
from unittest.mock import Mock, patch
from platform_loader import load_adapter

module = load_adapter('nbis', system='Windows')


def denied(code=5):
    error = PermissionError('test process start denial')
    error.winerror = code
    return error


class WindowsLaunchTests(unittest.TestCase):
    def invoke(self, events, limit=2, audit=None, verify=None):
        audit = {'retry_count': 0} if audit is None else audit
        command = {}
        process = Mock(pid=123)
        with patch.object(module.subprocess, 'Popen', side_effect=events + [process]) as launch, \
             patch.object(module.time, 'sleep') as sleep:
            result = module._launch(['bridge.exe', 'match'], '.', verify or Mock(),
                                    audit, command, Mock(), limit)
        return result, process, audit, command, launch, sleep

    def test_default_no_retry(self):
        with patch.object(module.subprocess, 'Popen', side_effect=denied()) as start, \
             patch.object(module.time, 'sleep') as sleep:
            with self.assertRaises(PermissionError):
                module._launch(['bridge.exe'], '.', Mock(), {'retry_count': 0}, {}, Mock(), 0)
        self.assertEqual(start.call_count, 1)
        sleep.assert_not_called()

    def test_recovered_launch_records_every_attempt_and_rechecks(self):
        verify = Mock()
        result, process, audit, command, start, sleep = self.invoke([denied()], verify=verify)
        self.assertIs(result, process)
        self.assertEqual(audit['retry_count'], 1)
        self.assertEqual([r['status'] for r in command['launch_attempts']], ['launch_failure', 'launched'])
        self.assertEqual(verify.call_count, 2)
        sleep.assert_called_once_with(.5)
        self.assertEqual(start.call_args_list[0], start.call_args_list[1])

    def test_persistent_denial_stops_after_shared_budget(self):
        audit = {'retry_count': 0}
        with patch.object(module.subprocess, 'Popen', side_effect=denied()) as start, \
             patch.object(module.time, 'sleep') as sleep:
            with self.assertRaises(PermissionError):
                module._launch(['bridge.exe'], '.', Mock(), audit, {}, Mock(), 2)
            self.assertEqual(start.call_count, 3)
            self.assertEqual([c.args[0] for c in sleep.call_args_list], [.5, 1.])
            # Later commands cannot restart the exhausted job budget.
            with self.assertRaises(PermissionError):
                module._launch(['bridge.exe'], '.', Mock(), audit, {}, Mock(), 2)
            self.assertEqual(start.call_count, 4)

    def test_other_os_error_not_retried(self):
        with patch.object(module.subprocess, 'Popen', side_effect=denied(2)) as start, \
             patch.object(module.time, 'sleep') as sleep:
            with self.assertRaises(PermissionError):
                module._launch(['bridge.exe'], '.', Mock(), {'retry_count': 0}, {}, Mock(), 2)
        self.assertEqual(start.call_count, 1)
        sleep.assert_not_called()

    def test_changed_runtime_or_output_stops_before_retry(self):
        verify = Mock(side_effect=[None, RuntimeError('changed')])
        with patch.object(module.subprocess, 'Popen', side_effect=denied()) as start, \
             patch.object(module.time, 'sleep'):
            with self.assertRaisesRegex(RuntimeError, 'changed'):
                module._launch(['bridge.exe'], '.', verify, {'retry_count': 0}, {}, Mock(), 2)
        self.assertEqual(start.call_count, 1)

    def test_started_process_is_never_retried_by_launcher(self):
        _, process, audit, command, start, sleep = self.invoke([])
        process.communicate.assert_not_called()
        self.assertEqual(start.call_count, 1)
        self.assertEqual(audit['retry_count'], 0)
        sleep.assert_not_called()

    def test_invalid_retry_budget_fails_before_runtime(self):
        for value in (-1, 3, True, .5, '2'):
            with self.subTest(value=value), patch.object(module, 'inspect_runtime') as inspect:
                with self.assertRaises(ValueError):
                    module.run_nbis_job({}, [], run_name='test', max_launch_retries=value)
                inspect.assert_not_called()

    def test_audit_failure_after_start_cleans_up_child(self):
        process = Mock(pid=123)
        persist = Mock(side_effect=[None, OSError('audit disk full')])
        with patch.object(module.subprocess, 'Popen', return_value=process):
            with self.assertRaisesRegex(OSError, 'audit disk full'):
                module._launch(['bridge.exe'], '.', Mock(), {'retry_count': 0}, {}, persist, 2)
        process.kill.assert_called_once(); process.wait.assert_called_once()

    def test_executed_failure_timeout_and_IO_are_not_retried(self):
        for behavior, expected in [('exit', 'process_failure'), ('timeout', 'timeout'), ('io', 'process_io_failure')]:
            with self.subTest(behavior=behavior), tempfile.TemporaryDirectory() as temp:
                root = Path(temp); exe = root/'bridge.exe'; exe.write_bytes(b'fake-test-only')
                image = root/'input.png'; Image.new('L', (32, 32), 128).save(image)
                created = []
                class FakeProcess:
                    def __init__(self, args, **kwargs):
                        self.args=args; self.pid=123; self.returncode=0; self.killed=False
                        created.append(self)
                    def __enter__(self): return self
                    def __exit__(self, *args): return False
                    def communicate(self, **kwargs):
                        if self.args[1]=='raw':
                            Path(self.args[-1]).write_text('1 2 3 4\n'*12, encoding='ascii')
                            return '12\n', ''
                        if behavior=='timeout' and not self.killed:
                            raise subprocess.TimeoutExpired(self.args, 45)
                        if behavior=='io': raise OSError('pipe read error')
                        self.returncode=7
                        return '', 'execution failure'
                    def kill(self): self.killed=True
                    def wait(self): return self.returncode
                runtime=dict(exe=str(exe),exe_sha256=hashlib.sha256(exe.read_bytes()).hexdigest())
                with patch.object(module, 'inspect_runtime', return_value=runtime), \
                     patch.object(module.tempfile, 'gettempdir', return_value=str(root)), \
                     patch.object(module.subprocess, 'Popen', side_effect=FakeProcess) as launch, \
                     patch.object(module.time, 'sleep') as sleep:
                    with self.assertRaises(RuntimeError):
                        module.run_nbis_job({'a':image}, [{'key':'self','probe':'a','candidate':'a'}],
                                            run_name='failure_contract',max_launch_retries=2)
                self.assertEqual(launch.call_count,2);sleep.assert_not_called()
                record=json.loads(next(root.glob('blurfing*/audit.json')).read_text())
                self.assertEqual(record['commands'][-1]['status'],expected)
                self.assertFalse(record['failure_is_nonmatch']);self.assertEqual(record['retry_count'],0)
                if behavior!='exit':self.assertTrue(created[-1].killed)


if __name__ == '__main__':
    unittest.main()
