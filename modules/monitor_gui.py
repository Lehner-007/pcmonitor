"""Single-window inventory UI using the shared project dialogs."""
import os
import json
import tempfile
import threading
from collections import deque
from pathlib import Path
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,Gio,GLib,Gdk
from .gui import MainWindow as BaseWindow, vertical
from .model import ROOT,PROJECT
from .results import ResultList
from .file_dialogs import choose
from .device_details import eligible,current_state
from .ram_snapshot import merge_snapshot
from .jobs import Cancelled
from .hardware_sources import occupancy_matches
from .inventory import MAX_SESSION_EVENTS,SECTIONS,inventory,device_state,differences,report,retain_events,translate_value


class Application(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='de.lehner.pcmonitor',flags=Gio.ApplicationFlags.NON_UNIQUE)
    def do_activate(self):
        window=self.get_active_window()
        if window is None:window=MonitorWindow(self)
        window.present()


class MonitorWindow(BaseWindow):
    def __init__(self,app):
        self._initial_scan_completed=False
        self.snapshot=None;self.events=deque(maxlen=MAX_SESSION_EVENTS);self.events_omitted=0;self.scan_running=False;self.poll_running=False
        self.detail_windows={};self.detail_pending=set()
        self.section='board';self.previous=None;self.navigation_labels=[]
        super().__init__(app)
        old=self.menu.get_next_sibling();self.layout.remove(old)
        self.bindings[:]=[binding for binding in self.bindings if binding[0] not in (self.work,)]
        self.set_default_size(1100,720)
        content=Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL,vexpand=True)
        nav=Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        images=json.loads((ROOT/'assets/navigation.json').read_text())
        for section in SECTIONS:
            label=Gtk.Label(label=self.tr('section_'+section),xalign=0,wrap=True,margin_start=10,margin_end=10,margin_top=10,margin_bottom=10)
            self.navigation_labels.append(label)
            entry=Gtk.Box(spacing=8,margin_start=6,margin_end=6)
            picture=Gtk.Image.new_from_file(str(ROOT/'assets'/images[section]));picture.set_pixel_size(48)
            entry.append(picture);entry.append(label);nav.append(entry)
        scroll=Gtk.ScrolledWindow(min_content_width=210);scroll.set_child(nav)
        content.set_start_child(scroll);content.set_resize_start_child(False);content.set_shrink_start_child(True)
        right=vertical(margin=12)
        self.heading=Gtk.Label(xalign=0,wrap=True);right.append(self.heading)
        self.note=self.label('limits',xalign=0,wrap=True);right.append(self.note)
        self.filter_codes=('all','occupied','empty','unknown')
        self.occupancy=Gtk.DropDown.new_from_strings([self.tr('occupancy_'+c) for c in self.filter_codes]);right.append(self.occupancy)
        self.results=ResultList(self,[('name','field'),('kind','kind'),('value','value'),('occupancy','occupancy')],cell_action=('occupancy',lambda r:eligible(dict(occupancy=r.get('raw_occupancy'),device_id=r.get('device_id'))),self.open_detail))
        self.results.status_filter.set_visible(False)
        result_area=Gtk.Overlay(vexpand=True)
        result_area.set_child(self.results)
        self.watermark=Gtk.Picture.new_for_filename(str(ROOT/PROJECT['watermark']))
        self.watermark.set_size_request(240,240)
        self.watermark.set_halign(Gtk.Align.CENTER);self.watermark.set_valign(Gtk.Align.CENTER)
        self.watermark.set_opacity(0.08);self.watermark.set_can_target(False)
        result_area.add_overlay(self.watermark)
        right.append(result_area)
        content.set_end_child(right);content.set_resize_end_child(True);content.set_shrink_end_child(True)
        self.layout.insert_child_after(content,self.menu)
        nav.connect('row-selected',self.select_section);nav.select_row(nav.get_row_at_index(0))
        self.occupancy.connect('notify::selected',lambda *_:self.show_section())
        action=Gio.SimpleAction.new('refresh',None);action.connect('activate',lambda *_:self.refresh());self.add_action(action)
        app.set_accels_for_action('win.refresh',['F5']);self.apply_language(self.tr.code)
        self.poll_timer=GLib.timeout_add_seconds(3,self.poll)
        css=Gtk.CssProvider();css.load_from_path(str(ROOT/'assets/style.css'))
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        GLib.idle_add(self.refresh)

    def initial_update(self):
        """Erstinventur vor der gemeinsamen Hintergrundprüfung ausführen."""
        if not self.alive or self.closing:return False
        if not self._initial_scan_completed or self.busy:
            GLib.timeout_add(250,self.initial_update)
            return False
        return super().initial_update()

    def apply_language(self,code):
        super().apply_language(code)
        if self.lookup_action('refresh'):
            menu=self.menu.get_menu_model();view=Gio.Menu();view.append(self.tr('refresh'),'win.refresh');menu.insert_submenu(1,self.tr('view'),view)
            from .menus import compact_menus
            compact_menus(self.menu)
        if hasattr(self,'occupancy'):
            selected=self.occupancy.get_selected()
            self.occupancy.set_model(Gtk.StringList.new([self.tr('occupancy_'+c) for c in self.filter_codes]));self.occupancy.set_selected(selected)
            for key,label in zip(SECTIONS,self.navigation_labels):label.set_label(self.tr('section_'+key))
            self.show_section()
            for entry in self.detail_windows.values():
                self.translate_detail(entry)

    def select_section(self,_,selected):
        if selected:self.section=SECTIONS[selected.get_index()];self.show_section()

    def show_section(self):
        if not hasattr(self,'heading'):return
        self.heading.set_label(self.tr('section_'+self.section))
        capture=(self.snapshot or {}).get('ram_capture')
        note=self.tr('limits')
        if self.section=='ram' and capture:
            note+='\n'+self.tr(capture['status'])+' · '+capture.get('captured_at','')+' · '+self.tr(capture.get('query_mode','ram_mode_normal'))
        if self.section=='events' and (self.events or self.events_omitted):
            note+='\n'+self.tr('events_count').format(count=len(self.events))
            if self.events:
                note+='\n'+self.tr('events_coverage').format(start=self.events[0]['time'],end=self.events[-1]['time'])
            if self.events_omitted:
                note+='\n'+self.tr('events_omitted').format(count=self.events_omitted)
        self.note.set_label(note)
        enabled=self.section not in ('board','cpu','sensors','system','events') and any(r['occupancy'] for r in (self.snapshot or {}).get('sections',{}).get(self.section,[]))
        self.occupancy.set_sensitive(enabled)
        if self.section=='events':
            rows=[dict(name=e['time']+' · '+self.tr(e['kind']),value=e['device']+' · '+e['connector']+' · '+e['state'],occupancy='') for e in self.events]
            if not rows:rows=[dict(name=self.tr('events_start'),value=self.tr('events_none'),occupancy='')]
        else:
            rows=[];code=self.filter_codes[self.occupancy.get_selected()] if enabled else 'all'
            for r in (self.snapshot or {}).get('sections',{}).get(self.section,[]):
                if not occupancy_matches(r,code):continue
                rows.append(dict(id=r.get('device_id'),device_id=r.get('device_id'),raw_occupancy=r['occupancy'],name=translate_value(self.tr(r['name']),self.tr),kind=self.tr('kind_'+r.get('kind','property')),value=translate_value(r['value'],self.tr),occupancy=self.tr('occupancy_'+r['occupancy']) if r['occupancy'] else ''))
        self.results.set_rows(rows)

    def open_detail(self,record):
        identity=record.get('device_id')
        detail=(self.snapshot or {}).get('details',{}).get(identity)
        # Never trust a visible label, table index or caller-provided occupancy.
        rows=[r for group in (self.snapshot or {}).get('sections',{}).values() for r in group]
        if not detail or not any(r.get('device_id')==identity and eligible(r) for r in rows):return
        if identity in self.detail_pending:return
        self.detail_pending.add(identity)
        def finish(state):
            self.detail_pending.discard(identity)
            if not self.alive:return False
            if state is not True:
                self.invalidate_detail(identity,state)
                self.notify('details_removed' if state is False else 'details_unverified')
                return False
            if not any(r.get('device_id')==identity and eligible(r) for group in (self.snapshot or {}).get('sections',{}).values() for r in group):return False
            if identity in self.detail_windows:
                self.detail_windows[identity]['window'].present();return False
            dialog=self.track(Gtk.Window(title=self.tr('device_details')+' · '+detail['name'],transient_for=self,default_width=620,default_height=540))
            box=vertical();heading=Gtk.Label(label=translate_value(detail['name'],self.tr),xalign=0,wrap=True,selectable=True);box.append(heading)
            status_key=detail.get('capture_status','ram_capture_ok') if detail['family']=='ram' else 'details_verified'
            status=Gtk.Label(label=self.tr(status_key),xalign=0,wrap=True);box.append(status)
            scroll=Gtk.ScrolledWindow(vexpand=True);fields=vertical(margin=0)
            recorded=detail.get('captured_at',self.snapshot['created'])
            recorded_label=Gtk.Label(label=self.tr('details_recorded')+': '+recorded,xalign=0,wrap=True);fields.append(recorded_label)
            field_labels=[]
            display_fields=dict(detail['fields'])
            if detail['family']=='ram':display_fields['ram_query_mode']='@'+detail['query_mode']
            for key,value in display_fields.items():
                label=Gtk.Label(label=self.tr(key)+': '+translate_value(str(value),self.tr),xalign=0,wrap=True,selectable=True)
                fields.append(label);field_labels.append((key,value,label))
            scroll.set_child(fields);box.append(scroll)
            button=Gtk.Button(label=self.tr('close'));button.connect('clicked',lambda *_:self.close_dialog(dialog));box.append(button)
            dialog.set_child(box)
            self.detail_windows[identity]=dict(window=dialog,status=status,detail=detail,active=detail['family']!='ram',status_key=status_key,heading=heading,button=button,field_labels=field_labels,recorded_label=recorded_label,recorded=recorded)
            dialog.connect('close-request',lambda *_:(self.detail_windows.pop(identity,None),False)[1])
            dialog.connect('destroy',lambda *_:self.detail_windows.pop(identity,None))
            dialog.present()
            return False
        def worker():
            try:state=current_state(detail)
            except (OSError,ValueError,TypeError):state=None
            GLib.idle_add(finish,state)
        if detail['family']=='ram':finish(True)
        else:threading.Thread(target=worker,daemon=True,name='device-detail-check').start()

    def translate_detail(self,entry):
        entry['window'].set_title(self.tr('device_details')+' · '+entry['detail']['name'])
        entry['heading'].set_label(translate_value(entry['detail']['name'],self.tr))
        entry['button'].set_label(self.tr('close'))
        entry['status'].set_label(self.tr(entry['status_key']))
        entry['recorded_label'].set_label(self.tr('details_recorded')+': '+entry['recorded'])
        for key,value,label in entry['field_labels']:
            label.set_label(self.tr(key)+': '+translate_value(str(value),self.tr))

    def invalidate_detail(self,identity,state):
        status_key='details_removed' if state is False else 'details_unverified'
        entry=self.detail_windows.get(identity)
        if entry:
            entry['active']=False;entry['status_key']=status_key
            self.translate_detail(entry)
        # Disable stale actions and prevent stale detail data appearing in exports.
        if self.snapshot:
            self.snapshot.get('details',{}).pop(identity,None)
            for group in self.snapshot['sections'].values():
                for record in group:
                    if record.get('device_id')==identity:
                        record.pop('device_id',None);record['occupancy']='unknown';record['value']='@'+status_key
            self.show_section()

    def update_actions(self):
        super().update_actions()
        action=self.lookup_action('refresh')
        if action:action.set_enabled(not self.busy and not self.closing)

    def accept_inventory(self,result,notify_failure=True):
        self._initial_scan_completed=True
        if not self.alive or self.closing:return False
        had_previous=self.snapshot is not None
        self.snapshot=merge_snapshot(self.snapshot,result)
        if self.snapshot is None:
            self.notify('scan_error');return
        for identity,entry in self.detail_windows.items():
            if entry['detail']['family']!='ram':continue
            detail=self.snapshot.get('details',{}).get(identity)
            if detail:
                entry['detail']=detail;entry['recorded']=detail['captured_at'];entry['status_key']=detail['capture_status']
                entry['field_labels']=[(key,'@'+detail['query_mode'] if key=='ram_query_mode' else detail['fields'].get(key,'@unknown'),label) for key,_,label in entry['field_labels']]
            else:entry['status_key']='ram_capture_superseded'
            self.translate_detail(entry)
        self.show_section()
        capture=self.snapshot.get('ram_capture',{})
        if result is None and notify_failure:self.notify('scan_error')
        elif had_previous and capture.get('status') in ('ram_capture_old','ram_capture_unavailable'):self.notify('ram_refresh_failed')
        elif any(detail.get('firmware',{}).get('status') not in (None,'ram_fw_ok') for detail in self.snapshot.get('details',{}).values() if detail['family']=='ram'):
            self.notify('ram_firmware_refresh_failed')

    def refresh(self):
        if not self.alive:return False
        def scan(context):
            try:
                result=inventory(cancel_event=context.cancel_event)
                context.check_cancel()
                return result
            except Cancelled:
                GLib.idle_add(self.accept_inventory,None,False)
                raise
            except Exception:
                # Preserve confirmed RAM at the job boundary; never infer removal.
                self.logger.exception(self.tr('scan_error'))
                return None
        self.start_job(scan,self.accept_inventory,cancellable=True,title_key='refresh',error_key='scan_error')
        return False

    def poll(self):
        if not self.alive:return False
        if self.poll_running:return True
        self.poll_running=True
        watched=[(identity,entry['detail']) for identity,entry in self.detail_windows.items() if entry['active'] and entry['detail']['family']!='ram']
        def work():
            try:current=device_state(self.previous)
            except OSError:current=None
            checks={}
            for identity,detail in watched:
                try:checks[identity]=current_state(detail)
                except (OSError,ValueError,TypeError):checks[identity]=None
            GLib.idle_add(finish,current,checks)
        def finish(current,checks):
            self.poll_running=False
            if not self.alive:return False
            for identity,state in checks.items():
                if state is not True:self.invalidate_detail(identity,state)
            if current is not None:
                new=differences(self.previous,current) if self.previous is not None else []
                self.events_omitted+=retain_events(self.events,new,self.events.maxlen);self.previous=current
                if new and self.section=='events':self.show_section()
            return False
        threading.Thread(target=work,daemon=True,name='device-events').start()
        return True

    def export_results(self,*_):
        if not self.snapshot:self.notify('no_inventory');return
        dialog=self.track(Gtk.Window(title=self.tr('results_export'),transient_for=self,modal=True,default_width=460))
        box=vertical();box.append(self.label('export_note',wrap=True,xalign=0))
        personal=Gtk.CheckButton(label=self.tr('export_personal'));events=Gtk.CheckButton(label=self.tr('export_events'))
        box.append(personal);box.append(events)
        def save(*_):
            text=report(self.snapshot,self.tr,self.events if events.get_active() else (),personal.get_active(),self.events_omitted if events.get_active() else 0)
            self.close_dialog(dialog)
            def write(path):
                fd,tmp=tempfile.mkstemp(prefix='.pcmonitor-',dir=path.parent)
                try:
                    with os.fdopen(fd,'w',encoding='utf-8') as stream:stream.write(text);stream.flush();os.fsync(stream.fileno())
                    os.replace(tmp,path);self.set_status('job_completed')
                finally:
                    if os.path.exists(tmp):os.unlink(tmp)
            choose(self,'results_export',write,action=Gtk.FileChooserAction.SAVE,filename='pcmonitor.txt',filters=[('TXT',['*.txt'])])
        box.append(self.button('choose_save',save));box.append(self.button('cancel',lambda *_:self.close_dialog(dialog)))
        dialog.set_child(box);dialog.present()

    def on_close(self,*args):
        result=super().on_close(*args)
        if not result:
            if hasattr(self,'poll_timer'):GLib.source_remove(self.poll_timer)
            self.snapshot=None;self.detail_windows.clear();self.detail_pending.clear()
        return result
