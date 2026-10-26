"""One tab: a folder shown as a details list (with date/kind groups) or as icons.

Groups are our own header rows in the list, not GTK's list sections: in GTK 4.22 a ColumnView
lays its section headers out but paints the rows over them (2026-10-26), so the headers never show.
"""
from gi.repository import Gdk, GLib, GObject, Gio, Gtk, Pango

from . import ops
from .model import ATTRS, DATE_GROUPS, KIND_GROUPS, FileItem, date_group, human_date, human_size, kind_group

HOME = Gio.File.new_for_path(GLib.get_home_dir())
DOWNLOADS = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD)

SORT_KEYS = {
    "name": lambda i: i.sort_key,
    "date": lambda i: i.mtime,
    "type": lambda i: i.type_desc.casefold(),
    "size": lambda i: i.size,
}


def location_name(f: Gio.File):
    if f.equal(HOME):
        return "Ev"
    if f.get_uri() == "trash:///":
        return "Çöp kutusu"
    if f.get_path() == "/":
        return "Sistem"
    return f.get_basename() or f.get_uri()


class GroupHeader(GObject.Object):
    __gtype_name__ = "GlassGroupHeader"

    def __init__(self, title, count):
        super().__init__()
        self.title = title
        self.count = count


class Browser(Gtk.Box):
    __gtype_name__ = "GlassBrowser"
    __gsignals__ = {
        "location-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "selection-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "items-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "open-in-tab": (GObject.SignalFlags.RUN_FIRST, None, (object,)),
        "context-menu": (GObject.SignalFlags.RUN_FIRST, None, (object, float, float, bool)),
        "transfer": (GObject.SignalFlags.RUN_FIRST, None, (object, object, bool)),
    }

    def __init__(self, settings, location: Gio.File):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.settings = settings
        self.location = None
        self.back_stack, self.forward_stack = [], []
        self.query = ""
        self.loading = False
        self._cancel = None
        self._monitor = None
        self._monitor_id = 0
        self._rebuild_id = 0
        self._syncing_sort = False
        self.group_mode = "none"
        self.view_mode = "details"
        self.sort_key, self.sort_desc = "name", False

        self.items = {}  # name -> FileItem, the folder's contents
        self.flat = Gio.ListStore(item_type=GObject.Object)  # what is shown: items and group headers
        self.selection = Gtk.MultiSelection(model=self.flat)
        self.selection.connect("selection-changed", lambda *_: self.emit("selection-changed"))

        self.stack = Gtk.Stack(vexpand=True, hexpand=True, transition_type=Gtk.StackTransitionType.CROSSFADE)
        self._build_details()
        self._build_grid()
        self.empty = Gtk.Label(label="Bu klasör boş", css_classes=["gf-empty"], vexpand=True)
        self.stack.add_named(self.empty, "empty")
        self.append(self.stack)

        drop = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY | Gdk.DragAction.MOVE)
        drop.connect("drop", self._on_drop)
        self.stack.add_controller(drop)

        self.navigate(location, history=False)

    # ---------- What is shown ----------

    def _visible(self, item):
        if item.hidden and not self.settings.get("show_hidden", False):
            return False
        return not self.query or self.query in item.display_name.casefold()

    def _group_of(self, item):
        if self.group_mode == "date":
            return date_group(item.mtime)
        if self.group_mode == "kind":
            return kind_group(item)
        return 0

    def rebuild(self):
        """Filter, sort and group the folder into the shown list, keeping the selection."""
        if self._rebuild_id:
            GLib.source_remove(self._rebuild_id)
            self._rebuild_id = 0
        keep = {i.name for i in self.selected_items()}
        items = [i for i in self.items.values() if self._visible(i)]
        items.sort(key=SORT_KEYS[self.sort_key], reverse=self.sort_desc)
        items.sort(key=lambda i: not i.is_dir)  # stable: folders first, each part keeps the order
        rows = []
        if self.group_mode != "none" and self.view_mode == "details":
            buckets = {}
            for i in items:
                buckets.setdefault(self._group_of(i), []).append(i)
            titles = DATE_GROUPS if self.group_mode == "date" else KIND_GROUPS
            for g in sorted(buckets):
                rows.append(GroupHeader(titles[g], len(buckets[g])))
                rows.extend(buckets[g])
        else:
            rows = items
        self.flat.splice(0, self.flat.get_n_items(), rows)
        if keep:
            for pos, row in enumerate(rows):
                if isinstance(row, FileItem) and row.name in keep:
                    self.selection.select_item(pos, False)
        self._sync_empty()
        self.emit("items-changed")

    def _queue_rebuild(self, delay=80):
        if not self._rebuild_id:
            self._rebuild_id = GLib.timeout_add(delay, self._rebuild_timeout)

    def _rebuild_timeout(self):
        self._rebuild_id = 0
        self.rebuild()
        return False

    def set_query(self, text):
        self.query = text.casefold().strip()
        self.rebuild()

    def refilter(self):
        self.rebuild()

    def set_grouping(self, mode):
        self.group_mode = mode
        self.rebuild()
        self._remember()

    def set_view(self, mode):
        self.view_mode = mode
        self.rebuild()
        self._remember()

    def sort_by(self, key, descending=False):
        self.sort_key, self.sort_desc = key, descending
        self._show_sort_indicator()
        self.rebuild()
        self._remember()

    def current_sort(self):
        return self.sort_key, self.sort_desc

    def _show_sort_indicator(self):
        self._syncing_sort = True
        self.cv.sort_by_column(self.columns[self.sort_key],
                               Gtk.SortType.DESCENDING if self.sort_desc else Gtk.SortType.ASCENDING)
        self._syncing_sort = False

    def _on_header_sort(self, sorter, _change):
        """A column header was clicked: the ColumnView only keeps the state, the list is sorted here."""
        if self._syncing_sort:
            return
        col = sorter.get_primary_sort_column()
        if not col:
            return
        self.sort_key = next((k for k, c in self.columns.items() if c == col), "name")
        self.sort_desc = sorter.get_primary_sort_order() == Gtk.SortType.DESCENDING
        self.rebuild()
        self._remember()

    def _remember(self):
        if not self.location or not self.location.get_uri():
            return
        folders = self.settings.setdefault("folders", {})
        folders[self.location.get_uri()] = {"view": self.view_mode, "group": self.group_mode,
                                           "sort": self.sort_key, "desc": self.sort_desc}
        self.settings.save()

    def _restore_view(self):
        saved = self.settings.get("folders", {}).get(self.location.get_uri())
        if saved:
            view, group, sort, desc = saved["view"], saved["group"], saved["sort"], saved["desc"]
        elif self.location.get_path() == DOWNLOADS:
            # Like Windows: Downloads is grouped by date, newest first.
            view, group, sort, desc = "details", "date", "date", True
        else:
            view, group, sort, desc = self.settings.get("default_view", "details"), "none", "name", False
        self.view_mode, self.group_mode = view, group
        self.sort_key, self.sort_desc = sort, desc
        self._show_sort_indicator()

    # ---------- Loading ----------

    def navigate(self, location: Gio.File, history=True):
        if self.location and history and not location.equal(self.location):
            self.back_stack.append(self.location)
            self.forward_stack.clear()
        self.location = location
        self.query = ""
        self._restore_view()
        self.reload()
        self.emit("location-changed")

    def go_back(self):
        if self.back_stack:
            self.forward_stack.append(self.location)
            self.navigate(self.back_stack.pop(), history=False)

    def go_forward(self):
        if self.forward_stack:
            self.back_stack.append(self.location)
            self.navigate(self.forward_stack.pop(), history=False)

    def go_up(self):
        parent = self.location.get_parent()
        if parent:
            self.navigate(parent)

    def reload(self):
        if self._cancel:
            self._cancel.cancel()
        self._cancel = Gio.Cancellable()
        self.items = {}
        self.flat.remove_all()
        self.loading = True
        self.empty.set_label("Bu klasör boş")
        self._watch()
        self.location.enumerate_children_async(ATTRS, Gio.FileQueryInfoFlags.NONE, GLib.PRIORITY_DEFAULT,
                                               self._cancel, self._on_enumerate, self._cancel)

    def _on_enumerate(self, f, res, cancel):
        try:
            en = f.enumerate_children_finish(res)
        except GLib.Error as e:
            if not cancel.is_cancelled():
                self.loading = False
                self.empty.set_label(f"Açılamadı: {e.message}")
                self._sync_empty()
            return
        en.next_files_async(512, GLib.PRIORITY_DEFAULT, cancel, self._on_batch, cancel)

    def _on_batch(self, en, res, cancel):
        try:
            infos = en.next_files_finish(res)
        except GLib.Error:
            return
        if cancel.is_cancelled():
            return
        if infos:
            for info in infos:
                item = FileItem(self.location, info)
                self.items[item.name] = item
            # A big folder shows up as it loads, without re-sorting on every batch.
            self._queue_rebuild(120)
            en.next_files_async(512, GLib.PRIORITY_DEFAULT, cancel, self._on_batch, cancel)
        else:
            en.close_async(GLib.PRIORITY_DEFAULT, None, None)
            self.loading = False
            self.rebuild()

    # ---------- Live updates ----------

    def _watch(self):
        if self._monitor:
            self._monitor.disconnect(self._monitor_id)
            self._monitor.cancel()
            self._monitor = None
        try:
            self._monitor = self.location.monitor_directory(Gio.FileMonitorFlags.WATCH_MOVES, None)
            self._monitor_id = self._monitor.connect("changed", self._on_changed)
        except GLib.Error:
            pass

    def _on_changed(self, _mon, f, other, event):
        E = Gio.FileMonitorEvent
        if event in (E.DELETED, E.MOVED_OUT):
            if self.items.pop(f.get_basename(), None):
                self._queue_rebuild()
        elif event in (E.CREATED, E.MOVED_IN, E.CHANGES_DONE_HINT, E.ATTRIBUTE_CHANGED):
            self._upsert(f)
        elif event == E.RENAMED:
            self.items.pop(f.get_basename(), None)
            if other and other.get_parent() and other.get_parent().equal(self.location):
                self._upsert(other)
            else:
                self._queue_rebuild()

    def _upsert(self, f):
        location = self.location

        def done(src, res):
            try:
                info = src.query_info_finish(res)
            except GLib.Error:
                return
            if location.equal(self.location):
                item = FileItem(self.location, info)
                self.items[item.name] = item
                self._queue_rebuild()
        f.query_info_async(ATTRS, Gio.FileQueryInfoFlags.NONE, GLib.PRIORITY_DEFAULT, None, done)

    def _sync_empty(self):
        if self.flat.get_n_items() == 0 and not self.loading:
            if self.query:
                self.empty.set_label(f"“{self.query}” ile eşleşen öğe yok")
            self.stack.set_visible_child_name("empty")
        else:
            self.stack.set_visible_child_name(self.view_mode)

    # ---------- Selection ----------

    def selected_items(self):
        out = []
        bits = self.selection.get_selection()
        ok, it, pos = Gtk.BitsetIter.init_first(bits)
        while ok:
            row = self.flat.get_item(pos)
            if isinstance(row, FileItem):
                out.append(row)
            ok, pos = it.next()
        return out

    def select_name(self, name):
        for i in range(self.flat.get_n_items()):
            row = self.flat.get_item(i)
            if isinstance(row, FileItem) and row.name == name:
                self.selection.select_item(i, True)
                if self.view_mode == "details":
                    self.cv.scroll_to(i, None, Gtk.ListScrollFlags.FOCUS, None)
                else:
                    self.grid.scroll_to(i, Gtk.ListScrollFlags.FOCUS, None)
                return

    def visible_count(self):
        return sum(1 for i in range(self.flat.get_n_items()) if isinstance(self.flat.get_item(i), FileItem))

    # ---------- Details view ----------

    def _build_details(self):
        self.cv = Gtk.ColumnView(model=self.selection, show_column_separators=False, show_row_separators=False,
                                 enable_rubberband=True, reorderable=False, css_classes=["gf-details"])
        self.cv.connect("activate", lambda _cv, pos: self.activate(pos))
        self.columns = {}

        # Group header rows can't be selected, opened or focused.
        rows = Gtk.SignalListItemFactory()

        def row_bind(_f, row):
            header = isinstance(row.get_item(), GroupHeader)
            row.set_selectable(not header)
            row.set_activatable(not header)
            row.set_focusable(not header)
        rows.connect("bind", row_bind)
        self.cv.set_row_factory(rows)

        def text_col(key, title, text_of, width=None, xalign=0.0):
            factory = Gtk.SignalListItemFactory()

            def setup(_f, li):
                label = Gtk.Label(xalign=xalign, ellipsize=Pango.EllipsizeMode.END, css_classes=["gf-cell", "dim-label"])
                self._wire_cell(label, li)
                li.set_child(label)

            def bind(_f, li):
                row = li.get_item()
                li.get_child().set_label("" if isinstance(row, GroupHeader) else text_of(row))
            factory.connect("setup", setup)
            factory.connect("bind", bind)
            col = Gtk.ColumnViewColumn(title=title, factory=factory, resizable=True,
                                       sorter=Gtk.CustomSorter.new(lambda *_: Gtk.Ordering.EQUAL, None))
            if width:
                col.set_fixed_width(width)
            self.cv.append_column(col)
            self.columns[key] = col

        name_factory = Gtk.SignalListItemFactory()

        def name_setup(_f, li):
            stack = Gtk.Stack(hhomogeneous=False, vhomogeneous=False)
            box = Gtk.Box(spacing=8, css_classes=["gf-cell", "gf-name"])
            box.append(Gtk.Image(pixel_size=18))
            box.append(Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.MIDDLE, hexpand=True))
            stack.add_named(box, "item")
            head = Gtk.Box(spacing=8, css_classes=["gf-group"])
            head.append(Gtk.Label(xalign=0, css_classes=["gf-group-title"]))
            head.append(Gtk.Label(xalign=0, css_classes=["gf-group-count"]))
            stack.add_named(head, "header")
            self._wire_cell(stack, li)
            li.set_child(stack)

        def name_bind(_f, li):
            row = li.get_item()
            stack = li.get_child()
            if isinstance(row, GroupHeader):
                head = stack.get_child_by_name("header")
                head.get_first_child().set_label(row.title)
                head.get_last_child().set_label(str(row.count))
                stack.set_visible_child_name("header")
                return
            box = stack.get_child_by_name("item")
            img, label = box.get_first_child(), box.get_last_child()
            img.set_from_gicon(row.icon) if row.icon else img.set_from_icon_name("text-x-generic")
            label.set_label(row.display_name)
            box.set_opacity(0.6 if row.hidden else 1.0)
            stack.set_visible_child_name("item")
        name_factory.connect("setup", name_setup)
        name_factory.connect("bind", name_bind)
        name_col = Gtk.ColumnViewColumn(title="Ad", factory=name_factory, expand=True, resizable=True,
                                        sorter=Gtk.CustomSorter.new(lambda *_: Gtk.Ordering.EQUAL, None))
        self.cv.append_column(name_col)
        self.columns["name"] = name_col

        text_col("date", "Değiştirme tarihi", lambda i: human_date(i.mtime), 150)
        text_col("type", "Tür", lambda i: i.type_desc, 170)
        text_col("size", "Boyut", lambda i: human_size(i.size), 90, xalign=1.0)
        self.cv.get_sorter().connect("changed", self._on_header_sort)

        scroll = Gtk.ScrolledWindow(child=self.cv, vexpand=True)
        self._wire_background(self.cv)
        self.stack.add_named(scroll, "details")

    # ---------- Icons view ----------

    def _build_grid(self):
        factory = Gtk.SignalListItemFactory()

        def setup(_f, li):
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, css_classes=["gf-tile"])
            pic = Gtk.Image(pixel_size=64, halign=Gtk.Align.CENTER)
            thumb = Gtk.Picture(content_fit=Gtk.ContentFit.COVER, halign=Gtk.Align.CENTER,
                                css_classes=["gf-thumb"], visible=False)
            thumb.set_size_request(96, 72)
            label = Gtk.Label(wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR, lines=2,
                              ellipsize=Pango.EllipsizeMode.END, justify=Gtk.Justification.CENTER,
                              max_width_chars=14)
            box.append(pic)
            box.append(thumb)
            box.append(label)
            self._wire_cell(box, li)
            li.set_child(box)

        def bind(_f, li):
            item = li.get_item()
            if not isinstance(item, FileItem):
                return
            box = li.get_child()
            pic = box.get_first_child()
            thumb = pic.get_next_sibling()
            label = box.get_last_child()
            if item.thumbnail:
                thumb.set_filename(item.thumbnail.decode() if isinstance(item.thumbnail, bytes) else item.thumbnail)
                thumb.set_visible(True)
                pic.set_visible(False)
            else:
                thumb.set_visible(False)
                pic.set_visible(True)
                pic.set_from_gicon(item.icon) if item.icon else pic.set_from_icon_name("text-x-generic")
            label.set_label(item.display_name)
        factory.connect("setup", setup)
        factory.connect("bind", bind)
        self.grid = Gtk.GridView(model=self.selection, factory=factory, max_columns=30, min_columns=2,
                                 enable_rubberband=True, css_classes=["gf-grid"])
        self.grid.connect("activate", lambda _g, pos: self.activate(pos))
        self._wire_background(self.grid)
        self.stack.add_named(Gtk.ScrolledWindow(child=self.grid, vexpand=True), "icons")

    # ---------- Pointer: open, context menu, middle click, drag ----------

    def _wire_cell(self, widget, li):
        widget.gf_listitem = li
        drag = Gtk.DragSource(actions=Gdk.DragAction.COPY | Gdk.DragAction.MOVE)
        drag.connect("prepare", self._drag_prepare, li)
        widget.add_controller(drag)

    def _drag_prepare(self, _src, _x, _y, li):
        if not isinstance(li.get_item(), FileItem):
            return None
        pos = li.get_position()
        if not self.selection.is_selected(pos):
            self.selection.select_item(pos, True)
        files = [i.file for i in self.selected_items()]
        return Gdk.ContentProvider.new_for_value(Gdk.FileList.new_from_array(files))

    def _item_at(self, view, x, y):
        w = view.pick(x, y, Gtk.PickFlags.DEFAULT)
        while w and w is not view:
            li = getattr(w, "gf_listitem", None)
            if li is not None and isinstance(li.get_item(), FileItem):
                return li.get_position()
            w = w.get_parent()
        return None

    def _wire_background(self, view):
        click = Gtk.GestureClick(button=0)

        def pressed(g, n, x, y):
            button = g.get_current_button()
            pos = self._item_at(view, x, y)
            if button == 3:
                if pos is not None and not self.selection.is_selected(pos):
                    self.selection.select_item(pos, True)
                elif pos is None:
                    self.selection.unselect_all()
                self.emit("context-menu", view, x, y, pos is not None)
                g.set_state(Gtk.EventSequenceState.CLAIMED)
            elif button == 2 and pos is not None:
                item = self.flat.get_item(pos)
                if item.is_dir:
                    self.emit("open-in-tab", item.file)
                g.set_state(Gtk.EventSequenceState.CLAIMED)
            elif button == 8:
                self.go_back()
            elif button == 9:
                self.go_forward()
        click.connect("pressed", pressed)
        view.add_controller(click)

    def activate(self, pos):
        item = self.flat.get_item(pos)
        if not isinstance(item, FileItem):
            return
        if item.is_dir:
            self.navigate(item.file)
        else:
            Gtk.FileLauncher(file=item.file).launch(self.get_root(), None, None)

    def _on_drop(self, target, value, x, y):
        files = value.get_files() if hasattr(value, "get_files") else list(value)
        if not files:
            return False
        view = self.cv if self.view_mode == "details" else self.grid
        point = self.stack.translate_coordinates(view, x, y)
        pos = self._item_at(view, *point) if point else None
        dest = self.location
        if pos is not None and self.flat.get_item(pos).is_dir:
            dest = self.flat.get_item(pos).file
        files = [f for f in files if not f.equal(dest)]
        if not files:
            return False
        self.emit("transfer", files, dest, ops.same_filesystem(files[0], dest))
        return True
