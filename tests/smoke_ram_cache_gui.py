"""GTK session-cache integration; fixture data, no privileged hardware query."""
import os,tempfile
from pathlib import Path
from unittest.mock import patch
_config=tempfile.TemporaryDirectory(dir=Path(__file__).parent)
os.environ.pop('PYTHON_TEMPLATE_DEV',None);os.environ['XDG_CONFIG_HOME']=_config.name
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,GLib
from modules.monitor_gui import Application
from modules.inventory import SECTIONS
from modules.menus import descendants
from test_ram_snapshot import generation
from copy import deepcopy
from modules.ram_firmware import module_firmware,parse_memory_devices
initial=generation()
second=generation(module='C');initial['sections']['ram']+=second['sections']['ram']
initial['sections']['ram'][1]['slot_id']='slot1';initial['sections']['ram'][1]['name']='DIMM1'
initial['details'].update(second['details']);initial['details']['ram:C']['name']='DIMM1'
source=dict(status='ram_fw_ok',captured_at='10.10.2026 12:00:05',elevated=True,warning='@ram_fw_smbios_warning',devices=parse_memory_devices((Path(__file__).parent/'fixtures/ram_ddr5_dmidecode.txt').read_text()))
for identity,slot in (('ram:A','DIMMA2'),('ram:C','DIMMB2')):
    detail=initial['details'][identity];detail['firmware']=module_firmware(source,slot);detail['fields'].update(detail['firmware']['fields'])
for section in SECTIONS:initial['sections'].setdefault(section,[])
# Ineligible RAM entries never gain a detail action.
for state in ('empty','unknown',''):
    initial['sections']['ram'].append(dict(name='No action',value='',occupancy=state,personal=False))
app=Application();failures=[];notices=[];checks=[]
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
    w=app.get_active_window();w.notify=lambda key,*a,**k:notices.append(key)
    w.section='ram';w.show_section()
    for record in w.results.rows()[2:]:w.open_detail(record)
    assert not w.detail_windows
    w.open_detail(w.results.rows()[0]);w.open_detail(w.results.rows()[1])
    assert set(w.detail_windows)=={'ram:A','ram:C'}
    assert not checks
    assert w.detail_windows['ram:A']['detail']['fields']['ram_configured_rate']=='6000 MT/s'
    assert w.detail_windows['ram:C']['detail']['fields']['ram_reported_speed']=='6000 MT/s'
    for entry in w.detail_windows.values():
        assert not entry['active'];assert entry['status_key']=='ram_capture_ok'
        assert entry['recorded']=='10.10.2026 12:00:00'
    w.results.view.sort_by_column(w.results.headers[0][0],Gtk.SortType.DESCENDING)
    w.occupancy.set_selected(1);w.results.search.set_text('DIMM1');w.results.refilter()
    assert len(w.results.rows(visible=True))==1
    w.open_detail(w.results.rows(visible=True)[0]);w.poll();later(refresh_failed)
@guard
def refresh_failed():
    assert not checks
    restricted=deepcopy(initial);restricted['ram_capture']['confirmed']=False;restricted['created']='10.10.2026 13:00:00'
    w.accept_inventory(restricted)
    assert notices[-1]=='ram_refresh_failed'
    assert w.detail_windows['ram:A']['status_key']=='ram_capture_old'
    assert w.detail_windows['ram:C']['recorded']=='10.10.2026 12:00:00'
    w.apply_language('en');assert 'Older confirmed RAM capture' in w.detail_windows['ram:A']['status'].get_label()
    w.apply_language('de')
    fresh=deepcopy(initial);fresh['ram_capture']['captured_at']='10.10.2026 14:00:00'
    for detail in fresh['details'].values():detail['captured_at']='10.10.2026 14:00:00'
    # A's slot becomes proven empty; C stays the same module in its own slot.
    fresh['sections']['ram'][0].update(occupancy='empty',value='')
    fresh['sections']['ram'][0].pop('device_id');fresh['details'].pop('ram:A')
    w.accept_inventory(fresh)
    assert w.detail_windows['ram:A']['status_key']=='ram_capture_superseded'
    assert w.detail_windows['ram:A']['recorded']=='10.10.2026 12:00:00'
    assert w.detail_windows['ram:C']['status_key']=='ram_capture_ok'
    assert w.detail_windows['ram:C']['recorded']=='10.10.2026 14:00:00'
    w.poll();later(finish)
@guard
def finish():
    assert not checks
    w.close();assert w.snapshot is None and not w.detail_windows
    app.quit();print('GTK RAM cache: two modules, click/poll without queries, failed refresh, timestamps, confirmed empty, sorting/filtering, DE/EN and cache discard verified')
app.connect('activate',lambda *_:Gtk.Settings.get_default().set_property('gtk-application-prefer-dark-theme',os.environ.get('PCMONITOR_TEST_DARK')=='1'))
with patch('modules.monitor_gui.inventory',return_value=initial),patch('modules.monitor_gui.current_state',side_effect=lambda d:checks.append(d) or True),patch('modules.monitor_gui.device_state',return_value={}),patch('modules.inventory.run',side_effect=AssertionError('unexpected lshw/pkexec')):
    GLib.timeout_add_seconds(2,first)
    GLib.timeout_add_seconds(15,lambda:(failures.append('timeout'),app.quit(),False)[-1])
    app.run([])
_config.cleanup()
if failures:raise RuntimeError(failures)
