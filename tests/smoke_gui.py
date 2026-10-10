"""Run on the existing graphical session; does not modify system settings."""
import gi
import os
import tempfile
from pathlib import Path

_test_config=tempfile.TemporaryDirectory(dir=Path(__file__).parent)
os.environ.pop('PYTHON_TEMPLATE_DEV',None)
os.environ['XDG_CONFIG_HOME']=_test_config.name
gi.require_version('Gtk','4.0')
from gi.repository import GLib, Gtk
from modules.monitor_gui import Application
from modules.menus import descendants

app=Application();failures=[]
app.connect('activate',lambda *_:Gtk.Settings.get_default().set_property('gtk-application-prefer-dark-theme',os.environ.get('PCMONITOR_TEST_DARK')=='1'))
def inspect():
    try:
        w=app.get_active_window()
        assert w.snapshot and len(w.navigation_labels)==16
        assert w.watermark.get_mapped() and 0 < w.watermark.get_opacity() <= 0.1
        assert not w.watermark.get_can_target()
        assert sum(isinstance(x,Gtk.Image) for x in descendants(w.layout))>=16
        for section in ('cpu','ram','events','board'):
            w.section=section;w.show_section()
            assert w.occupancy.get_sensitive()==(section=='ram')
        w.apply_language('en');assert w.heading.get_label()=='Mainboard'
        w.apply_language('de')
        w.unmaximize();w.set_default_size(820,600)
        # Actually open the one-entry View menu and check its allocated contents.
        popovers=[x for x in descendants(w.menu) if isinstance(x,Gtk.Popover)]
        view=popovers[1];view.popup()
        GLib.timeout_add(300,check_menu,w,view)
    except Exception as exc:
        failures.append(repr(exc));app.quit()
    return False

def check_menu(w,view):
    try:
        areas=[x for x in descendants(view) if isinstance(x,Gtk.ScrolledWindow)]
        assert areas
        for area in areas:
            child=area.get_child()
            natural=child.measure(Gtk.Orientation.VERTICAL,-1).natural
            actual=child.get_allocated_height()
            assert actual <= natural+12,(natural,actual)
        assert view.get_mapped()
        print('GUI: 16 images; DE/EN; occupancy; 820x600; one-entry menu height verified')
    except Exception as exc:failures.append(repr(exc))
    finally:
        view.popdown();w.close();app.quit()
    return False
GLib.timeout_add_seconds(7,inspect)
app.run([])
_test_config.cleanup()
if failures:raise RuntimeError(failures)
