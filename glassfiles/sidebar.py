"""Left pane: quick access, bookmarks, drives with a usage bar, trash."""
import os
from urllib.parse import unquote

from gi.repository import GLib, GObject, Gio, Gtk, Pango

from .model import human_size

SPECIAL = [
    ("Home", GLib.get_home_dir(), "user-home-symbolic"),
    ("Desktop", GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DESKTOP), "user-desktop-symbolic"),
    ("Downloads", GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD), "folder-download-symbolic"),
    ("Documents", GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOCUMENTS), "folder-documents-symbolic"),
    ("Pictures", GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_PICTURES), "folder-pictures-symbolic"),
    ("Music", GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_MUSIC), "folder-music-symbolic"),
    ("Videos", GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_VIDEOS), "folder-videos-symbolic"),
]
BOOKMARKS = os.path.join(GLib.get_user_config_dir(), "gtk-3.0", "bookmarks")


class Sidebar(Gtk.Box):
    __gtype_name__ = "GlassSidebar"
    __gsignals__ = {
        "open": (GObject.SignalFlags.RUN_FIRST, None, (object, bool)),  # file, new tab
    }

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, css_classes=["gf-sidebar"])
        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE, css_classes=["gf-places"])
        self.list.connect("row-activated", lambda _l, row: self.emit("open", row.gf_file, False))
        middle = Gtk.GestureClick(button=2)
        middle.connect("pressed", self._middle)
        self.list.add_controller(middle)
        self.append(Gtk.ScrolledWindow(child=self.list, vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER))

        self.volumes = Gio.VolumeMonitor.get()
        for sig in ("mount-added", "mount-removed", "mount-changed"):
            self.volumes.connect(sig, lambda *_: self.rebuild())
        try:
            self._bm_monitor = Gio.File.new_for_path(BOOKMARKS).monitor_file(Gio.FileMonitorFlags.NONE, None)
            self._bm_monitor.connect("changed", lambda *_: self.rebuild())
        except GLib.Error:
            pass
        self.rebuild()

    def _middle(self, g, _n, x, y):
        row = self.list.get_row_at_y(int(y))
        if row and getattr(row, "gf_file", None):
            self.emit("open", row.gf_file, True)

    def _header(self, text):
        row = Gtk.ListBoxRow(activatable=False, selectable=False, css_classes=["gf-places-header"])
        row.set_child(Gtk.Label(label=text, xalign=0))
        self.list.append(row)

    def _row(self, title, gfile, icon, usage=None):
        row = Gtk.ListBoxRow(css_classes=["gf-place"])
        row.gf_file = gfile
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        top = Gtk.Box(spacing=10)
        top.append(Gtk.Box(css_classes=["gf-indicator"], valign=Gtk.Align.CENTER))  # lit when selected
        img = Gtk.Image(icon_name=icon) if isinstance(icon, str) else Gtk.Image(gicon=icon)
        top.append(img)
        top.append(Gtk.Label(label=title, xalign=0, hexpand=True, ellipsize=Pango.EllipsizeMode.END))
        box.append(top)
        if usage:
            used, total = usage
            bar = Gtk.LevelBar(min_value=0, max_value=1, value=used / total if total else 0,
                               css_classes=["gf-usage"])
            bar.add_offset_value("full", 0.9)
            box.append(bar)
            box.append(Gtk.Label(label=f"{human_size(total - used)} free of {human_size(total)}", xalign=0,
                                 css_classes=["gf-usage-text"]))
        row.set_child(box)
        row.set_tooltip_text(gfile.get_path() or gfile.get_uri())
        self.list.append(row)
        return row

    def _usage(self, f):
        try:
            info = f.query_filesystem_info("filesystem::size,filesystem::free", None)
            total = info.get_attribute_uint64("filesystem::size")
            free = info.get_attribute_uint64("filesystem::free")
            return (total - free, total) if total else None
        except GLib.Error:
            return None

    def rebuild(self):
        while (child := self.list.get_first_child()):
            self.list.remove(child)
        self._header("Quick access")
        for title, path, icon in SPECIAL:
            if path and os.path.isdir(path):
                self._row(title, Gio.File.new_for_path(path), icon)

        marks = []
        special = {p for _t, p, _i in SPECIAL}
        try:
            with open(BOOKMARKS) as fh:
                for line in fh:
                    uri, _, label = line.strip().partition(" ")
                    if uri.startswith("file://"):
                        f = Gio.File.new_for_uri(uri)
                        # The Quick access folders are listed already.
                        if f.get_path() and os.path.isdir(f.get_path()) and f.get_path() not in special:
                            marks.append((label or unquote(os.path.basename(f.get_path())), f))
        except OSError:
            pass
        if marks:
            self._header("Bookmarks")
            for label, f in marks:
                self._row(label, f, "folder-symbolic")

        self._header("This PC")
        root = Gio.File.new_for_path("/")
        self._row("System (/)", root, "drive-harddisk-system-symbolic", self._usage(root))
        seen = {"/"}
        for mount in self.volumes.get_mounts():
            f = mount.get_root()
            path = f.get_path()
            if not path or path in seen or mount.is_shadowed():
                continue
            seen.add(path)
            self._row(mount.get_name(), f, mount.get_symbolic_icon(), self._usage(f))
        self._row("Trash", Gio.File.new_for_uri("trash:///"), "user-trash-symbolic")

    def highlight(self, location):
        best = None
        row = self.list.get_first_child()
        while row:
            f = getattr(row, "gf_file", None)
            if f and f.equal(location):
                best = row
                break
            row = row.get_next_sibling()
        if best:
            self.list.select_row(best)
        else:
            self.list.unselect_all()
