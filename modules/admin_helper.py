"""Standalone fixed probe; executed with system Python -I -S, never imported as root."""
import json
import os
import signal
import stat
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path


def trusted(path):
    path=Path(path).resolve()
    for entry in (path,*path.parents):
        try:info=entry.stat()
        except OSError:return False
        if info.st_uid!=0 or info.st_mode & (stat.S_IWGRP|stat.S_IWOTH):return False
    return path.is_file()


def stop(process):
    try:os.killpg(process.pid,signal.SIGTERM)
    except ProcessLookupError:return
    try:process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        try:os.killpg(process.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        process.wait()


def probe(paths,args,cancel):
    record=dict(status='missing',returncode=None,stdout='',stderr='',captured_at='')
    tool=next((path for path in paths if trusted(path)),None)
    if tool is not None:
        if cancel.is_set():record['status']='cancelled'
        else:
            try:
                process=subprocess.Popen([tool,*args],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,errors='replace',start_new_session=True,env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','LC_ALL':'C'})
                deadline=time.monotonic()+20
                while True:
                    if cancel.is_set() or time.monotonic()>deadline:
                        stop(process);record['status']='cancelled' if cancel.is_set() else 'timeout'
                        stdout,stderr=process.communicate();break
                    try:
                        stdout,stderr=process.communicate(timeout=.2);record['status']='ok' if process.returncode==0 else 'failed';break
                    except subprocess.TimeoutExpired:continue
                record.update(returncode=process.returncode,stdout=stdout,stderr=stderr)
            except OSError:record['status']='failed'
    record['captured_at']=datetime.now().astimezone().strftime('%d.%m.%Y %H:%M:%S %Z')
    return record


def main():
    if len(sys.argv)!=1:return 2
    cancel=threading.Event()
    def watch():
        # EOF also cancels if the normal application exits unexpectedly.
        os.read(sys.stdin.fileno(),1);cancel.set()
    threading.Thread(target=watch,daemon=True).start()
    records={}
    records['lshw']=probe(('/usr/bin/lshw','/usr/sbin/lshw'),('-json',),cancel)
    records['dmidecode']=probe(('/usr/sbin/dmidecode','/usr/bin/dmidecode'),('--type','17'),cancel)
    print(json.dumps(dict(schema=1,uid=os.getuid(),sources=records)),flush=True)
    return 0

if __name__=='__main__':sys.exit(main())
