"""Bounded, cancellable execution for read-only system tools."""
import os
import selectors
import signal
import subprocess
import time


_READ_CHUNK = 65536
_POST_EXIT_GRACE = 0.2
_TERM_GRACE = 0.15
_KILL_DRAIN_GRACE = 0.25


def _signal_group(process, sig):
    """Signal the subprocess session even if its original leader has exited."""
    try:
        os.killpg(process.pid, sig)
    except ProcessLookupError:
        return False
    return True


def _group_exists(process):
    try:
        os.killpg(process.pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def run_capped(args, *, timeout, cancel_event=None, stdout_limit=4 * 1024 * 1024,
               stderr_limit=256 * 1024, env=None):
    """Return (status, returncode, stdout, stderr), draining excess bytes.

    The requested runtime is bounded by ``timeout`` plus at most 0.6 seconds
    for process-group termination and pipe cleanup. Pipes are drained without
    reader threads, so inherited descriptors cannot hold the caller at join or
    stream.close. A child left behind after its parent exits makes the result
    ``failed`` and is terminated as part of the same process group.
    """
    if cancel_event and cancel_event.is_set():
        return 'cancelled', None, '', ''
    try:
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=True, env=env)
    except OSError:
        return 'failed', None, '', ''

    buffers = {'stdout': bytearray(), 'stderr': bytearray()}
    limits = {'stdout': max(0, stdout_limit), 'stderr': max(0, stderr_limit)}
    exceeded = set()
    streams = {'stdout': process.stdout, 'stderr': process.stderr}
    selector = selectors.DefaultSelector()
    open_streams = {}

    def unregister(name):
        stream = streams[name]
        try:
            selector.unregister(stream)
        except (KeyError, ValueError):
            pass
        open_streams.pop(name, None)

    def drain_ready(wait):
        for key, _ in selector.select(max(0, wait)):
            name = key.data
            try:
                chunk = os.read(key.fd, _READ_CHUNK)
            except BlockingIOError:
                continue
            except OSError:
                unregister(name)
                continue
            if not chunk:
                unregister(name)
                continue
            remaining = limits[name] - len(buffers[name])
            if remaining > 0:
                buffers[name].extend(chunk[:remaining])
            if len(chunk) > max(0, remaining):
                exceeded.add(name)

    for name, stream in streams.items():
        os.set_blocking(stream.fileno(), False)
        selector.register(stream, selectors.EVENT_READ, data=name)
        open_streams[name] = stream

    started = time.monotonic()
    deadline = started + max(0, timeout)
    parent_exit_deadline = None
    status = None
    diagnostic = ''

    try:
        while True:
            now = time.monotonic()
            if cancel_event and cancel_event.is_set():
                status = 'cancelled'
                break
            if now >= deadline:
                status = 'timeout'
                break

            returncode = process.poll()
            if returncode is not None:
                if not open_streams:
                    if _group_exists(process):
                        status = 'failed'
                        diagnostic = 'Prozessgruppe enthält nach Prozessende noch laufende Nachkommen.'
                    break
                if parent_exit_deadline is None:
                    parent_exit_deadline = min(deadline, now + _POST_EXIT_GRACE)
                elif now >= parent_exit_deadline:
                    status = 'failed'
                    diagnostic = 'Nachkommen halten Ausgabepipes nach Prozessende offen.'
                    break

            wait = min(0.025, max(0, deadline - now))
            if parent_exit_deadline is not None:
                wait = min(wait, max(0, parent_exit_deadline - now))
            drain_ready(wait)

        if status in ('timeout', 'cancelled', 'failed'):
            # Do not wait on the original process: it may already have exited.
            # Escalate the complete session after a short bounded grace period.
            _signal_group(process, signal.SIGTERM)
            term_deadline = time.monotonic() + _TERM_GRACE
            while open_streams and time.monotonic() < term_deadline:
                drain_ready(min(0.025, term_deadline - time.monotonic()))
            _signal_group(process, signal.SIGKILL)

            try:
                process.wait(timeout=0.1)
            except subprocess.TimeoutExpired:
                diagnostic = diagnostic or 'Elternprozess reagierte nicht auf SIGKILL.'

            kill_deadline = time.monotonic() + _KILL_DRAIN_GRACE
            while open_streams and time.monotonic() < kill_deadline:
                drain_ready(min(0.025, kill_deadline - time.monotonic()))

            if open_streams:
                diagnostic = diagnostic or 'Ausgabepipes blieben nach Prozessbereinigung offen.'
                for name in tuple(open_streams):
                    unregister(name)

        try:
            process.wait(timeout=0.1)
        except subprocess.TimeoutExpired:
            if status is None:
                status = 'failed'
                diagnostic = 'Elternprozess wurde nicht innerhalb der Bereinigungsfrist beendet.'

        if status is None:
            status = 'output_limit' if exceeded else 'ok' if process.returncode == 0 else 'failed'
    finally:
        for name in tuple(open_streams):
            unregister(name)
        selector.close()
        for stream in streams.values():
            if stream and not stream.closed:
                stream.close()

    stderr = buffers['stderr'].decode('utf-8', errors='replace')
    if diagnostic:
        stderr = f'{stderr}\n{diagnostic}'.strip()
    return status, process.returncode, buffers['stdout'].decode('utf-8', errors='replace'), stderr
