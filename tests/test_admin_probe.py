import io
import json
import subprocess
import threading
import unittest
from unittest.mock import patch
from pathlib import Path
from modules.admin_probe import query_admin_sources
from modules.admin_helper import probe


def records(lshw='ok',dmi='ok'):
    return dict(schema=1,uid=0,sources={key:dict(status=status,stdout='{}',stderr='',returncode=0,captured_at='10.10.2026 12:00:00') for key,status in [('lshw',lshw),('dmidecode',dmi)]})

class FakeProcess:
    def __init__(self,data,code=0,pending=False):
        self.stdin=io.BytesIO();self.stdout=io.BytesIO(json.dumps(data).encode());self.stderr=io.BytesIO();self.returncode=None if pending else code
    def poll(self):return self.returncode
    def wait(self,timeout=None):self.returncode=0;return 0
    def terminate(self):self.returncode=-15
    def kill(self):self.returncode=-9

class AdminProbeTests(unittest.TestCase):
    def setUp(self):
        stdlib=patch("modules.admin_probe._system_stdlib",return_value=Path("/usr/lib/python3.12"))
        stdlib.start();self.addCleanup(stdlib.stop)

    def test_one_fixed_isolated_request_and_separate_sources(self):
        for lshw,dmi in [('ok','ok'),('missing','ok'),('failed','ok'),('ok','missing'),('ok','timeout')]:
            process=FakeProcess(records(lshw,dmi))
            with patch('modules.admin_probe.shutil.which',return_value='/fixture/pkexec'),patch('modules.admin_probe.trusted',return_value=True),patch('modules.admin_probe.subprocess.Popen',return_value=process) as launch:
                result=query_admin_sources()
            self.assertEqual(launch.call_count,1)
            args=launch.call_args.args[0];self.assertEqual(args[:5],['/fixture/pkexec','/usr/bin/python3','-I','-S','-c'])
            self.assertNotIn('from modules',args[5]);self.assertNotIn('pkexec',args[5])
            self.assertEqual(result['sources']['lshw']['status'],lshw)
            self.assertEqual(result['sources']['dmidecode']['status'],dmi)
            self.assertTrue(process.stdin.closed)

    def test_denial_never_retries(self):
        with patch('modules.admin_probe.shutil.which',return_value='/fixture/pkexec'),patch('modules.admin_probe.trusted',return_value=True),patch('modules.admin_probe.subprocess.Popen',return_value=FakeProcess({},126)) as launch:
            self.assertEqual(query_admin_sources()['status'],'denied');self.assertEqual(launch.call_count,1)

    def test_cancel_and_timeout_close_helper_channel(self):
        for cancel in (True,False):
            process=FakeProcess(records(),pending=True);event=threading.Event()
            if cancel:event.set()
            with patch('modules.admin_probe.shutil.which',return_value='/fixture/pkexec'),patch('modules.admin_probe.trusted',return_value=True),patch('modules.admin_probe.subprocess.Popen',return_value=process),patch('modules.admin_probe.time.monotonic',side_effect=[0,121]):
                result=query_admin_sources(event)
            self.assertEqual(result['status'],'cancelled' if cancel else 'timeout');self.assertTrue(process.stdin.closed)

    def test_missing_pkexec_and_unsafe_interpreter(self):
        with patch('modules.admin_probe.shutil.which',return_value=None),patch('modules.admin_probe.subprocess.Popen') as launch:
            self.assertEqual(query_admin_sources()['status'],'missing');launch.assert_not_called()
        with patch('modules.admin_probe.shutil.which',return_value='/fixture/pkexec'),patch('modules.admin_probe.trusted',return_value=False):self.assertEqual(query_admin_sources()['status'],'unsafe')

    def test_helper_fixed_direct_tools_and_individual_missing(self):
        code=Path('modules/admin_helper.py').read_text()
        self.assertIn("('/usr/bin/lshw','/usr/sbin/lshw'),('-json',)",code)
        self.assertIn("('/usr/sbin/dmidecode','/usr/bin/dmidecode'),('--type','17')",code)
        with patch('modules.admin_helper.trusted',return_value=False):
            self.assertEqual(probe(('/fixture/tool',),(),threading.Event())['status'],'missing')

    def test_actual_unprivileged_child_cancelled_and_reaped(self):
        # No elevation; exercise the same child-process cleanup logic with a sleep.
        event=threading.Event();timer=threading.Timer(.25,event.set);timer.start()
        result=probe(('/usr/bin/python3',),('-I','-S','-c','import time; time.sleep(30)'),event)
        timer.join();self.assertEqual(result['status'],'cancelled');self.assertIsNotNone(result['returncode'])

    def test_inventory_independent_source_success_and_no_retry(self):
        from modules.inventory import inventory
        from test_ram_firmware import FIXTURE
        bank=dict(id='bank:0',slot='DIMMA2',size=17179869184,product='Module')
        for lshw_ok in (True,False):
            bundle=records('ok' if lshw_ok else 'failed','missing' if lshw_ok else 'ok')
            bundle['sources']['lshw']['stdout']=json.dumps(bank) if lshw_ok else ''
            bundle['sources']['dmidecode']['stdout']='' if lshw_ok else FIXTURE
            with patch.dict('os.environ',{'PCMONITOR_ADMIN_QUERY':'1'}),patch('modules.inventory.query_admin_sources',return_value=dict(status='ok',sources=bundle['sources'])) as admin,patch('modules.inventory.json_command',return_value={}),patch('modules.inventory.run',return_value=''),patch('modules.inventory.bluez_devices',return_value=[]):
                result=inventory()
            self.assertEqual(admin.call_count,1)
            if lshw_ok:self.assertTrue(result['ram_capture']['confirmed'])
            else:
                self.assertEqual(result['firmware_capture']['devices']['DIMMA2']['fields']['ram_configured_rate'],'6000 MT/s')
                self.assertTrue(any(r['name']=='dmidecode / DIMMA2' for r in result['sections']['system']))

    def test_reject_nonroot_helper_output(self):
        data=records();data['uid']=1000
        with patch('modules.admin_probe.shutil.which',return_value='/fixture/pkexec'),patch('modules.admin_probe.trusted',return_value=True),patch('modules.admin_probe.subprocess.Popen',return_value=FakeProcess(data)):
            self.assertEqual(query_admin_sources()['status'],'failed')

class AdminDiagnosticTests(unittest.TestCase):
    def test_helper_exit_with_open_control_pipe(self):
        # Reproduce interpreter shutdown with the same live watcher, no hardware.
        code=Path('modules/admin_helper.py').read_text().split("if __name__=='__main__':")[0]
        code+="\nprobe=lambda paths,args,cancel: dict(status='missing',returncode=None,stdout='',stderr='',captured_at='test')\nmain()\n"
        process=subprocess.Popen(['/usr/bin/python3','-I','-S','-c',code],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            process.wait(timeout=8)
            self.assertEqual(process.returncode,0)
            self.assertEqual(json.loads(process.stdout.read())['schema'],1)
            self.assertEqual(process.stderr.read(),b'')
        finally:
            process.stdin.close();process.stdout.close();process.stderr.close()

    def test_diagnostic_failure_categories_and_privacy(self):
        from modules.admin_probe import _safe_stderr
        self.assertNotIn('SECRET',_safe_stderr('serial: SECRET'))
        for stage,data,rc in [('json_decode',b'',0),('json_decode',b'not json',0),('schema_validate',b'{}',0),('process_exit',b'{}',1)]:
            process=FakeProcess({},rc);process.stdout=io.BytesIO(data)
            process.stderr=io.BytesIO(b'Fatal Python error: _enter_buffered_busy serial SECRET')
            with patch('modules.admin_probe._system_stdlib',return_value=Path('/usr/lib/python3.12')),patch('modules.admin_probe.trusted',return_value=True),patch('modules.admin_probe.shutil.which',return_value='/fixture/pkexec'),patch('modules.admin_probe.subprocess.Popen',return_value=process):
                result=query_admin_sources()
            self.assertEqual(result['diagnostic']['stage'],stage)
            self.assertEqual(result['diagnostic']['returncode'],rc)
            self.assertNotIn('SECRET',str(result['diagnostic']))

    def test_actual_target_interpreter_stdlib(self):
        from modules.admin_probe import _system_stdlib
        # Calling interpreter sysconfig must never determine the target path.
        with patch('sysconfig.get_path',return_value='/wrong/caller'):
            path=_system_stdlib()
        self.assertTrue((path/'json/__init__.py').is_file())
        self.assertNotEqual(str(path),'/wrong/caller')

    def test_start_failure_diagnostic(self):
        with patch('modules.admin_probe._system_stdlib',return_value=Path('/usr/lib/python3.12')),patch('modules.admin_probe.trusted',return_value=True),patch('modules.admin_probe.shutil.which',return_value='/fixture/pkexec'),patch('modules.admin_probe.subprocess.Popen',side_effect=OSError('private value')):
            result=query_admin_sources()
        self.assertEqual(result['diagnostic']['stage'],'process_start')
        self.assertEqual(result['diagnostic']['error'],'OSError')
        self.assertNotIn('private value',str(result))
