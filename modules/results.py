"""Gemeinsame Ergebnisliste mit Suche, Filter, Sortierung und stabiler Auswahl."""
from gi.repository import Gtk, Gio, GObject, Gdk

_row_provider = None


def striped_rows(view):
    global _row_provider
    view.add_css_class('template-results')
    if _row_provider is None:
        _row_provider = Gtk.CssProvider()
        _row_provider.load_from_data(b'''
            columnview.template-results listview > row:nth-child(even):not(:selected):not(:hover) {
                background-color: alpha(@theme_fg_color, 0.09);
            }
        ''')
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),
            _row_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


class ResultRow(GObject.Object):
    def __init__(self, data):
        super().__init__()
        self.data = data


class ResultList(Gtk.Box):
    def __init__(self, owner, columns, cell_action=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8, vexpand=True)
        self.owner, self.columns = owner, columns
        self.search = Gtk.SearchEntry(placeholder_text=owner.tr('result_search'))
        self.filter_codes = ('all', 'ok', 'warning', 'error')
        self.status_filter = Gtk.DropDown.new_from_strings([owner.tr('result_' + key) for key in self.filter_codes])
        controls = Gtk.Box(spacing=8)
        self.search.set_hexpand(True)
        controls.append(self.search)
        controls.append(self.status_filter)
        self.append(controls)
        self.store = Gio.ListStore.new(ResultRow)
        self.filter = Gtk.CustomFilter.new(self.matches)
        filtered = Gtk.FilterListModel.new(self.store, self.filter)
        self.sorted = Gtk.SortListModel.new(filtered, None)
        self.selection = Gtk.SingleSelection.new(self.sorted)
        self.selection.set_autoselect(False)
        self.selection.set_can_unselect(True)
        self.view = Gtk.ColumnView.new(self.selection)
        striped_rows(self.view)
        self.view.set_show_column_separators(True)
        self.view.set_show_row_separators(True)
        self.headers = []
        for key, label_key in columns:
            factory = Gtk.SignalListItemFactory()
            def setup(_, item, field=key):
                label=Gtk.Label(xalign=0,margin_start=8,margin_end=8,margin_top=6,margin_bottom=6,wrap=True)
                if cell_action and field==cell_action[0]:
                    box=Gtk.Box();box.append(label)
                    button=Gtk.Button()
                    button.connect('clicked',lambda *_:cell_action[2](item.get_item().data) if item.get_item() else None)
                    box.append(button);item.set_child(box)
                else:item.set_child(label)
            factory.connect('setup',setup)
            def bind(_, item, field=key):
                record=item.get_item().data
                if cell_action and field==cell_action[0]:
                    box=item.get_child();label=box.get_first_child();button=label.get_next_sibling()
                    allowed=cell_action[1](record)
                    label.set_label(self.display(record,field));label.set_visible(not allowed)
                    button.set_label(self.display(record,field));button.set_visible(allowed);button.set_sensitive(allowed)
                    button.set_tooltip_text(self.owner.tr('device_details')+' · '+str(record.get('name','')))
                else:item.get_child().set_label(self.display(record,field))
            factory.connect('bind', bind)
            column = Gtk.ColumnViewColumn.new(owner.tr(label_key), factory)
            column.set_resizable(True)
            column.set_expand(True)
            def compare(a, b, *_args, field=key):
                left, right = a.data.get(field, ''), b.data.get(field, '')
                if not (type(left) in (int, float) and type(right) in (int, float)):
                    left, right = self.display(a.data, field).casefold(), self.display(b.data, field).casefold()
                return (left > right) - (left < right)
            column.set_sorter(Gtk.CustomSorter.new(compare))
            self.view.append_column(column)
            self.headers.append((column, label_key))
        self.sorted.set_sorter(self.view.get_sorter())
        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_child(self.view)
        self.append(scroll)
        self.count = Gtk.Label(xalign=0)
        self.append(self.count)
        self.search.connect('search-changed', self.refilter)
        self.status_filter.connect('notify::selected', self.refilter)
        self.sorted.connect('items-changed', lambda *_: self.update_count())
        self.update_count()

    def display(self, record, field):
        value = record.get(field, '')
        return self.owner.tr('result_' + value) if field == 'status' else str(value)

    def matches(self, row):
        code = self.filter_codes[self.status_filter.get_selected()]
        query = self.search.get_text().casefold().strip()
        return (code == 'all' or row.data.get('status') == code) and (
            not query or any(query in self.display(row.data, key).casefold() for key, _ in self.columns))

    def refilter(self, *_):
        self.filter.changed(Gtk.FilterChange.DIFFERENT)
        self.update_count()

    def update_count(self):
        self.count.set_label(self.owner.tr('result_count', visible=self.sorted.get_n_items(), total=self.store.get_n_items()))

    def rows(self, visible=False):
        model = self.sorted if visible else self.store
        return [model.get_item(i).data.copy() for i in range(model.get_n_items())]

    def set_rows(self, rows):
        selected = self.selection.get_selected_item()
        selected_id = selected.data.get('id') if selected else None
        self.store.splice(0, self.store.get_n_items(), [ResultRow(row.copy()) for row in rows])
        if selected_id is not None:
            for i in range(self.sorted.get_n_items()):
                if self.sorted.get_item(i).data.get('id') == selected_id:
                    self.selection.set_selected(i)
                    break
        self.update_count()

    def translate(self):
        self.search.set_placeholder_text(self.owner.tr('result_search'))
        selected = self.status_filter.get_selected()
        self.status_filter.set_model(Gtk.StringList.new([self.owner.tr('result_' + key) for key in self.filter_codes]))
        self.status_filter.set_selected(selected)
        for column, key in self.headers:
            column.set_title(self.owner.tr(key))
        self.set_rows(self.rows())
        self.refilter()


def example_rows(tr):
    return [dict(id='a', name=tr('example_a'), status='ok', details=tr('example_ok')),
            dict(id='b', name=tr('example_b'), status='warning', details=tr('example_warning')),
            dict(id='c', name=tr('example_c'), status='error', details=tr('example_error'))]
