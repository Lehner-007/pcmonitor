import os
import signal
import tempfile
import subprocess
import sys
import threading
import time
import unittest
from modules.processes import run_capped


class BoundedProcessTests(unittest.TestCase):
    def test_normal_process_returns_both_streams(self):
        status,code,stdout,stderr=run_capped([sys.executable,'-c',
            "import sys; print('out'); print('err',file=sys.stderr)"],timeout=2)
        self.assertEqual((status,code),('ok',0))
        self.assertEqual(stdout,'out\n')
        self.assertEqual(stderr,'err\n')

    def test_stdout_and_stderr_are_capped_while_drained(self):
        script="import sys; sys.stdout.write('x'*200000); sys.stderr.write('y'*200000)"
        status,code,stdout,stderr=run_capped([sys.executable,'-c',script],timeout=3,
            stdout_limit=1024,stderr_limit=512)
        self.assertEqual((status,code),('output_limit',0))
        self.assertEqual((len(stdout),len(stderr)),(1024,512))

    def test_timeout_reaps_process(self):
        started=time.monotonic()
        status,code,_,_=run_capped([sys.executable,'-c','import time; time.sleep(10)'],timeout=.1)
        self.assertEqual(status,'timeout')
        self.assertIsNotNone(code)
        self.assertLess(time.monotonic()-started,1.0)

    def test_cancellation_stops_running_process(self):
        cancel=threading.Event();result=[]
        worker=threading.Thread(target=lambda:result.append(run_capped(
            [sys.executable,'-c','import time; time.sleep(10)'],timeout=5,cancel_event=cancel)))
        worker.start();time.sleep(.1);cancel.set();worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(result[0][0],'cancelled')

    def test_exited_parent_with_sigterm_ignoring_child_is_cleaned_boundedly(self):
        with tempfile.TemporaryDirectory(prefix='pcmonitor-process-test-') as folder:
            pid_file=os.path.join(folder,'child-pids')
            child_script=('import signal,time; '
                'signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(30)')
            parent_script=(
                'import os,subprocess,sys; '
                'child=subprocess.Popen([sys.executable,"-c",sys.argv[2]]).pid; '
                'open(sys.argv[1],"w").write(f"{os.getpid()} {child}")'
            )
            result=[]
            worker=threading.Thread(target=lambda:result.append(run_capped(
                [sys.executable,'-c',parent_script,pid_file,child_script],timeout=4)),
                daemon=True)
            started=time.monotonic()
            worker.start()
            worker.join(2)
            pids=[]
            if os.path.exists(pid_file):
                try:
                    with open(pid_file,encoding='ascii') as pid_stream:
                        pids=[int(value) for value in pid_stream.read().split()]
                except (OSError,ValueError):
                    pids=[]
            try:
                self.assertFalse(worker.is_alive(), 'run_capped exceeded the independent 2s watchdog')
                self.assertLess(time.monotonic()-started,2)
                self.assertEqual(result[0][0],'failed')
                self.assertIn('Nachkommen',result[0][3])
                self.assertEqual(len(pids),2)
                child_pid=pids[1]
                process_state=None
                for _ in range(20):
                    try:
                        with open(f'/proc/{child_pid}/stat',encoding='ascii') as stat_file:
                            process_state=stat_file.read().split(') ',1)[1][0]
                    except FileNotFoundError:
                        process_state=None
                    if process_state in (None,'Z'):
                        break
                    time.sleep(.025)
                self.assertIn(process_state,(None,'Z'), 'SIGTERM-ignoring child remained alive')
            finally:
                # Independent final cleanup if an assertion catches a regression.
                if len(pids)==2:
                    try:
                        os.killpg(pids[0],signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                worker.join(.5)
            self.assertFalse(worker.is_alive(), 'process runner thread remained after cleanup')

    def test_exited_parent_with_redirected_living_child_is_not_success(self):
        with tempfile.TemporaryDirectory(prefix='pcmonitor-process-test-') as folder:
            pid_file=os.path.join(folder,'child-pids')
            parent_script=(
                'import os,subprocess,sys; '
                'child=subprocess.Popen([sys.executable,"-c","import time; time.sleep(30)"],'
                'stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).pid; '
                'open(sys.argv[1],"w").write(f"{os.getpid()} {child}")'
            )
            status,code,_,stderr=run_capped(
                [sys.executable,'-c',parent_script,pid_file],timeout=3)
            self.assertEqual((status,code),('failed',0))
            self.assertIn('Nachkommen',stderr)
            with open(pid_file,encoding='ascii') as pid_stream:
                group_id,child_pid=map(int,pid_stream.read().split())
            try:
                process_state=None
                for _ in range(20):
                    try:
                        with open(f'/proc/{child_pid}/stat',encoding='ascii') as stat_file:
                            process_state=stat_file.read().split(') ',1)[1][0]
                    except FileNotFoundError:
                        process_state=None
                    if process_state in (None,'Z'):
                        break
                    time.sleep(.025)
                self.assertIn(process_state,(None,'Z'), 'redirected child remained alive')
            finally:
                try:
                    os.killpg(group_id,signal.SIGKILL)
                except ProcessLookupError:
                    pass


if __name__=='__main__':unittest.main()
