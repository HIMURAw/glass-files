"""One file in a folder listing, and the date groups shown in Downloads (as in Windows Explorer)."""
from datetime import datetime, timedelta

from gi.repository import GLib, GObject, Gio

ATTRS = ",".join([
    "standard::name", "standard::display-name", "standard::type", "standard::size",
    "standard::content-type", "standard::icon", "standard::is-hidden", "standard::is-backup",
    "standard::is-symlink", "standard::symlink-target", "time::modified", "time::created",
    "thumbnail::path", "access::can-write", "access::can-trash",
])


class FileItem(GObject.Object):
    __gtype_name__ = "GlassFileItem"

    def __init__(self, parent: Gio.File, info: Gio.FileInfo):
        super().__init__()
        self.update(parent, info)

    def update(self, parent, info):
        self.info = info
        self.name = info.get_name()
        self.file = parent.get_child(self.name)
        self.display_name = info.get_display_name() or self.name
        self.is_dir = info.get_file_type() == Gio.FileType.DIRECTORY
        self.size = info.get_size() if not self.is_dir else -1
        self.content_type = info.get_content_type() or "application/octet-stream"
        self.hidden = info.get_is_hidden() or info.get_is_backup()
        self.symlink = info.get_is_symlink()
        dt = info.get_modification_date_time()
        self.mtime = dt.to_unix() if dt else 0
        ct = info.get_creation_date_time()
        self.ctime = ct.to_unix() if ct else 0
        self.icon = info.get_icon()
        self.thumbnail = info.get_attribute_byte_string("thumbnail::path")
        self.type_desc = "File folder" if self.is_dir else (Gio.content_type_get_description(self.content_type) or "File")
        self.child_count = None  # filled lazily for folders
        self.sort_key = GLib.utf8_collate_key_for_filename(self.display_name, -1)

    @property
    def path(self):
        return self.file.get_path()


def human_size(n):
    if n is None or n < 0:
        return ""
    units = ["B", "KB", "MB", "GB", "TB"]
    f = float(n)
    for u in units:
        if f < 1024 or u == units[-1]:
            if u == "B":
                return f"{int(f)} B"
            return f"{f:.1f} {u}"
        f /= 1024


def human_date(ts):
    if not ts:
        return ""
    return datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M")


# Windows Explorer's groups when sorting by date, newest first.
DATE_GROUPS = ["Today", "Yesterday", "Earlier this week", "Last week", "Earlier this month",
               "Last month", "Earlier this year", "A long time ago"]


def date_group(ts, now=None):
    now = now or datetime.now()
    t = datetime.fromtimestamp(ts) if ts else datetime(1970, 1, 1)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week = today - timedelta(days=today.weekday())
    month = today.replace(day=1)
    last_month = (month - timedelta(days=1)).replace(day=1)
    if t >= today:
        return 0
    if t >= today - timedelta(days=1):
        return 1
    if t >= week:
        return 2
    if t >= week - timedelta(days=7):
        return 3
    if t >= month:
        return 4
    if t >= last_month:
        return 5
    if t >= today.replace(month=1, day=1):
        return 6
    return 7


KIND_GROUPS = ["Folders", "Documents", "Pictures", "Videos", "Music", "Archives", "Programs", "Other"]


def kind_group(item):
    if item.is_dir:
        return 0
    ct = item.content_type
    if ct.startswith("image/"):
        return 2
    if ct.startswith("video/"):
        return 3
    if ct.startswith("audio/"):
        return 4
    if any(k in ct for k in ("zip", "tar", "compressed", "x-7z", "rar", "x-xz", "gzip", "bzip")):
        return 5
    if any(k in ct for k in ("executable", "x-sharedlib", "x-rpm", "x-deb", "appimage", "flatpak", "x-shellscript")):
        return 6
    if ct.startswith("text/") or any(k in ct for k in ("pdf", "document", "spreadsheet", "presentation", "msword", "officedocument", "json", "xml")):
        return 1
    return 7
