"""Exactly one pkexec request for a fixed isolated read-only probe."""
import json
import os
import signal
import shutil
import subprocess
import threading
import time
import logging
import re
from pathlib import Path
from .admin_helper import trusted

MAX_HELPER_STDOUT=20*1024*1024
MAX_HELPER_STDERR=512*1024


def _stop_group(process):
    try:os.killpg(process.pid,signal.SIGTERM)
    except (ProcessLookupError,AttributeError):
        try:process.terminate()
        except (ProcessLookupError,AttributeError):pass
    try:process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        try:os.killpg(process.pid,signal.SIGKILL)
        except (ProcessLookupError,AttributeError):
            try:process.kill()
            except (ProcessLookupError,AttributeError):pass
        process.wait()


def _system_stdlib():
    """Ask the exact isolated interpreter that will execute the helper."""
    result=subprocess.run(['/usr/bin/python3','-I','-S','-c',
        'import sysconfig; print(sysconfig.get_path("stdlib"))'],capture_output=True,text=True,timeout=5,check=True)
    path=Path(result.stdout.strip())
    if not path.is_absolute():raise ValueError('invalid stdlib path')
    return path


def _safe_stderr(value):
    # Never copy arbitrary tool diagnostics (may contain device identifiers).
    text=value.decode('utf-8',errors='replace') if isinstance(value,bytes) else str(value)
    known=('Fatal Python error:', 'Python runtime state:', 'Error executing command',
           'Error executing ', 'Error opening current controlling terminal',
           'Not authorized', 'No authentication agent', 'SyntaxError:',
           'ModuleNotFoundError:', 'ImportError:', 'PermissionError:')
    lines=[]
    for line in text.splitlines():
        if line.startswith(known):
            # Keep fixed error categories, no arbitrary trailing paths or names.
            category=line.split(':',1)[0]
            if '_enter_buffered_busy' in line:category+=': _enter_buffered_busy at interpreter shutdown'
            lines.append(category[:100])
    return '; '.join(lines) or ('[stderr present; content withheld]' if text else '')


def _finish(status,stage,sources=None,returncode=None,stderr='',error=None):
    diagnostic=dict(status=status,stage=stage,returncode=returncode,
                    stderr=_safe_stderr(stderr),error=error)
    logging.getLogger('pcmonitor.application').info('Admin probe: %s',json.dumps(diagnostic,ensure_ascii=False))
    for key,record in (sources or {}).items():
        logging.getLogger('pcmonitor.application').info('Admin source %s: status=%s returncode=%s time=%s stderr=%s',
            key,record['status'],record.get('returncode'),record['captured_at'],_safe_stderr(record.get('stderr','')))
    return dict(status=status,sources=sources or {},diagnostic=diagnostic)


def query_admin_sources(cancel_event=None):
    pkexec=shutil.which('pkexec')
    if not pkexec:return _finish('missing','pkexec_lookup')
    python='/usr/bin/python3'
    if not trusted(pkexec) or not trusted(python):return _finish('unsafe','executable_trust')
    try:stdlib=_system_stdlib()
    except (OSError,ValueError,subprocess.SubprocessError) as exc:return _finish('failed','stdlib_lookup',error=type(exc).__name__)
    if not trusted(stdlib/'json/__init__.py'):return _finish('unsafe','stdlib_trust')
    # Source is passed as fixed code, not imported from a project path as root.
    # -I -S excludes cwd, PYTHONPATH, user site and sitecustomize.
    helper=Path(__file__).with_name('admin_helper.py')
    # Installed copies must be root owned and non-writable along their full path.
    if str(helper.resolve()).startswith(('/usr/','/opt/')) and not trusted(helper):return _finish('unsafe','helper_trust')
    try:code=helper.read_text()
    except OSError as exc:return _finish('failed','helper_read',error=type(exc).__name__)
    try:
        process=subprocess.Popen([pkexec,python,'-I','-S','-c',code],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
    except OSError as exc:return _finish('failed','process_start',error=type(exc).__name__)
    output={'stdout':bytearray(),'stderr':bytearray()};limits={'stdout':MAX_HELPER_STDOUT,'stderr':MAX_HELPER_STDERR};exceeded=set();output_lock=threading.Lock();limit_reached=threading.Event()
    def drain(name,stream):
        while True:
            chunk=stream.read(65536)
            if not chunk:break
            with output_lock:
                remaining=limits[name]-len(output[name])
                if remaining>0:output[name].extend(chunk[:remaining])
                if len(chunk)>remaining:exceeded.add(name);limit_reached.set()
        stream.close()
    readers=[threading.Thread(target=drain,args=(name,stream),daemon=True) for name,stream in [('stdout',process.stdout),('stderr',process.stderr)]]
    for reader in readers:reader.start()
    deadline=time.monotonic()+120
    status=None
    while process.poll() is None:
        if limit_reached.is_set():
            status='output_limit'
            try:process.stdin.close()
            except (OSError,ValueError):pass
            _stop_group(process)
            break
        if (cancel_event and cancel_event.is_set()) or time.monotonic()>deadline:
            status='cancelled' if cancel_event and cancel_event.is_set() else 'timeout'
            try:process.stdin.close()  # cooperating elevated helper terminates its tool groups
            except (OSError,ValueError):pass
            _stop_group(process)
            break
        time.sleep(.05)
    if not process.stdin.closed:process.stdin.close()
    for reader in readers:reader.join(timeout=2)
    if any(reader.is_alive() for reader in readers):
        _stop_group(process)
        for reader in readers:reader.join(timeout=1)
    captured={name:bytes(value) for name,value in output.items()}
    if status:return _finish(status,'process_wait',returncode=process.returncode,stderr=captured['stderr'])
    if process.returncode:return _finish('denied' if process.returncode in (126,127) else 'failed','process_exit',returncode=process.returncode,stderr=captured['stderr'])
    try:
        if exceeded:raise ValueError('helper output limit')
        result=json.loads(captured['stdout'])
    except (ValueError,TypeError) as exc:
        return _finish('output_limit' if exceeded else 'failed','output_limit' if exceeded else 'json_decode',returncode=process.returncode,stderr=captured['stderr'],error=type(exc).__name__)
    try:
        if result.get('schema')!=1 or result.get('uid')!=0:raise ValueError('invalid probe')
        sources=result['sources']
        for key in ('lshw','dmidecode'):
            record=sources[key]
            if record['status'] not in ('ok','missing','failed','timeout','cancelled','output_limit'):raise ValueError('invalid source')
            if not isinstance(record['stdout'],str) or not isinstance(record['captured_at'],str):raise ValueError('invalid source')
        return _finish('ok','complete',sources,process.returncode,captured['stderr'])
    except (ValueError,TypeError,KeyError,AttributeError) as exc:return _finish('failed','schema_validate',returncode=process.returncode,stderr=captured['stderr'],error=type(exc).__name__)
