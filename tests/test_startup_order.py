"""Erstinventur und Updateprüfung dürfen sich den JobRunner nicht wegnehmen."""
import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import GLib

from modules.monitor_gui import Application, MonitorWindow
from modules.model import VERSION, now
from modules.gui import MainWindow
from test_ram_snapshot import generation


class StartupTests(unittest.TestCase):
    def test_first_inventory_finishes_before_update_worker(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp, patch.dict(os.environ, XDG_CONFIG_HOME=tmp):
            os.environ.pop('PYTHON_TEMPLATE_DEV', None)
            app = Application()
            app.register(None)
            order = []

            def scan(**kwargs):
                order.append('scan')
                return generation()

            def update(*args):
                order.append('update')
                return dict(version=VERSION)

            with patch('modules.monitor_gui.inventory', side_effect=scan), patch('modules.gui.release_info', side_effect=update):
                window = MonitorWindow(app)
                window.opts.update(update_check=True, last_update_check='')
                window.present()
                try:
                    deadline = time.monotonic() + 5
                    while (len(order) < 2 or window.jobs.running) and time.monotonic() < deadline:
                        while GLib.MainContext.default().pending():
                            GLib.MainContext.default().iteration(False)
                        time.sleep(.01)
                    self.assertEqual(order, ['scan', 'update'])
                    self.assertIsNotNone(window.snapshot)
                    self.assertTrue(window._initial_scan_completed)
                finally:
                    window.close()


class UpdateDecisionTests(unittest.TestCase):
    def test_disabled_automatic_update_does_not_start(self):
        window = SimpleNamespace(busy=False, opts=dict(update_check=False, update_url='https://example.invalid/version.json'), check_update=lambda *a, **k: self.fail('automatic check started'))
        self.assertFalse(MainWindow.initial_update(window))

    def test_enabled_but_not_due_does_not_start(self):
        window = SimpleNamespace(busy=False, opts=dict(update_check=True, update_url='https://example.invalid/version.json', last_update_check=now(), update_interval_value=1, update_interval_unit='weeks'), check_update=lambda *a, **k: self.fail('early automatic check started'))
        self.assertFalse(MainWindow.initial_update(window))

    def test_due_automatic_update_starts_and_manual_check_remains_available(self):
        calls = []
        window = SimpleNamespace(busy=False, opts=dict(update_check=True, update_url='https://example.invalid/version.json', last_update_check='', update_interval_value=1, update_interval_unit='weeks'), check_update=lambda *a, **k: calls.append((a, k)))
        MainWindow.initial_update(window)
        self.assertEqual(calls, [(('https://example.invalid/version.json',), {'automatic': True})])

        manual_calls = []

        class ManualWindow:
            opts = dict(update_check=False, update_url='https://example.invalid/version.json')
            update_status_key = ''

            def refresh_update_controls(self):
                pass

            def background(self, work, done, **kwargs):
                manual_calls.append(kwargs)
                done(dict(version=VERSION, deb=None))

            def set_status(self, *args):
                pass

            def tr(self, key):
                return key

        with patch('modules.gui.release_info', return_value=dict(version=VERSION, deb=None)), patch('modules.gui.save_settings'):
            MainWindow.check_update(ManualWindow(), automatic=False)
        self.assertTrue(manual_calls)
