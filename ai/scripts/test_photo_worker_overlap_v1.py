import subprocess
import sys
import unittest
from photo_worker_overlap_v1 import pending_worker


class WorkerOverlapTests(unittest.TestCase):
    def test_success_and_stderr_are_reaped(self):
        with pending_worker([sys.executable,'-c','import sys;sys.stderr.write("diagnostic")']) as job:
            job.finish();job.finish()
            self.assertEqual(job.stderr,b'diagnostic')
        self.assertEqual(job.process.returncode,0)

    def test_parent_failure_stops_owned_worker(self):
        with self.assertRaisesRegex(RuntimeError,'parent'):
            with pending_worker([sys.executable,'-c','import time;time.sleep(30)']) as job:
                raise RuntimeError('parent')
        self.assertIsNotNone(job.process.poll())

    def test_deadline_is_measured_from_launch_and_nonzero_is_not_success(self):
        with self.assertRaises(subprocess.TimeoutExpired):
            with pending_worker([sys.executable,'-c','import time;time.sleep(30)'],timeout=.05) as job:
                job.finish()
        self.assertIsNotNone(job.process.poll())
        with self.assertRaises(subprocess.CalledProcessError):
            with pending_worker([sys.executable,'-c','raise SystemExit(7)']) as failed:
                failed.finish()
        self.assertEqual(failed.process.returncode,7)


if __name__=='__main__':unittest.main()
