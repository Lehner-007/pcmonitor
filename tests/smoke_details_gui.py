"""GTK fixture integration: binding, activation, sort/filter, stale windows."""
import os
import tempfile
from pathlib import Path
from unittest.mock import patch
_config=tempfile.TemporaryDirectory(dir=Path(__file__).parent)
os.environ.pop('PYTHON_TEMPLATE_DEV',None);os.environ['XDG_CONFIG_HOME']=_config.name
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,GLib
from modules.monitor_gui import Application
from modules.menus import descendants
from modules.inventory import SECTIONS,row

snapshot=dict(created='10.10.2026 12:00:00',sections={s:[] for s in SECTIONS},details={})
for index,state in enumerate(('occupied','occupied','empty','unknown','')):
    record=row('Same Model',str(index),state);record['device_id']=f'device{index}'
    snapshot['sections']['display'].append(record)
    snapshot['details'][record['device_id']]=dict(id=record['device_id'],name='Same Model',family='display',fields={'active_mode':f'{index}x1080','supported_modes':'1920x1080 / 60 Hz'})
app=Application();failures=[];checks=[];removed=set()
def verify(detail):
    checks.append(detail['id']);return detail['id'] not in removed

def buttons(w):return [x for x in descendants(w.results.view) if isinstance(x,Gtk.Button) and x.get_visible() and x.get_label()==w.tr('occupancy_occupied')]
def later(function):GLib.timeout_add(300,function)
def guard(function):
    def wrapper():
        try:function()
        except Exception as exc:failures.append(repr(exc));app.quit()
        return False
    return wrapper

@guard
def first():
    global w
    w=app.get_active_window();assert w.snapshot
    w.section='display';w.show_section();w.unmaximize();w.set_default_size(820,600)
    later(bound)
@guard
def bound():
    assert len(buttons(w))==2
    for record in w.results.rows()[2:]:w.open_detail(record)
    assert not w.detail_pending and not checks
    # Ordinary Gtk.Button click action; no row-wide activation is installed.
    buttons(w)[0].emit('clicked');later(clicked)
@guard
def clicked():
    assert 'device0' in w.detail_windows and checks==['device0']
    w.results.view.sort_by_column(w.results.headers[2][0],Gtk.SortType.DESCENDING)
    w.occupancy.set_selected(1);w.results.search.set_text('Same Model');w.results.refilter()
    later(keyboard)
@guard
def keyboard():
    assert len(buttons(w))==2
    button=buttons(w)[0];assert button.get_focusable();button.grab_focus()
    # GTK's keyboard activation path, with delayed Button activation semantics.
    assert button.activate()
    GLib.timeout_add(600,key_done)
@guard
def key_done():
    assert 'device1' in w.detail_windows,checks
    assert w.detail_windows['device1']['detail']['fields']['active_mode']=='1x1080'
    w.apply_language('en');assert w.detail_windows['device1']['button'].get_label()=='Close'
    w.apply_language('de');assert w.detail_windows['device1']['button'].get_label()=='Schließen'
    removed.add('device1');w.poll();later(stale)
@guard
def stale():
    assert not w.detail_windows['device1']['active']
    assert w.tr('details_removed')==w.detail_windows['device1']['status'].get_label()
    assert 'device1' not in w.snapshot['details']
    assert not any(r.get('device_id')=='device1' for r in w.results.rows())
    global prior
    prior=checks.count('device1');w.poll();later(stopped)
@guard
def stopped():
    assert checks.count('device1')==prior
    for entry in list(w.detail_windows.values()):w.close_dialog(entry['window'])
    w.close();app.quit()
    print('GTK details: click, keyboard activation, same-name IDs, sorting/filtering, DE/EN, removal and stopped queries verified')
app.connect('activate',lambda *_:Gtk.Settings.get_default().set_property('gtk-application-prefer-dark-theme',os.environ.get('PCMONITOR_TEST_DARK')=='1'))
with patch('modules.monitor_gui.inventory',return_value=snapshot),patch('modules.monitor_gui.current_state',side_effect=verify),patch('modules.monitor_gui.device_state',return_value={}):
    GLib.timeout_add_seconds(2,first)
    GLib.timeout_add_seconds(15,lambda: (failures.append('timeout'),app.quit(),False)[-1])
    app.run([])
_config.cleanup()
if failures:raise RuntimeError(failures)
