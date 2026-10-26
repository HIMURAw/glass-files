"""File operations, run off the UI thread. Deleting goes to the trash unless asked otherwise."""
import os
import subprocess
import threading

from gi.repository import GLib, Gio


def unique_child(folder: Gio.File, name: str, copy_suffix=False) -> Gio.File:
    """folder/name, or "name (2)", "name (3)"… if taken. The number goes before the extension."""
    stem, ext = os.path.splitext(name) if not name.startswith(".") else (name, "")
    if os.path.isdir(os.path.join(folder.get_path() or "", name)):
        stem, ext = name, ""
    candidate = folder.get_child(name)
    if copy_suffix and candidate.query_exists(None):
        stem = f"{stem} - Copy"
        candidate = folder.get_child(stem + ext)
    n = 2
    while candidate.query_exists(None):
        candidate = folder.get_child(f"{stem} ({n}){ext}")
        n += 1
    return candidate


def _run(work, done):
    def target():
        errors = []
        try:
            work(errors)
        except Exception as e:  # report, never crash the window
            errors.append(str(e))
        GLib.idle_add(lambda: (done(errors), False)[1])
    threading.Thread(target=target, daemon=True).start()


def same_filesystem(a: Gio.File, b: Gio.File):
    try:
        ia = a.query_info("id::filesystem", Gio.FileQueryInfoFlags.NONE, None)
        ib = b.query_info("id::filesystem", Gio.FileQueryInfoFlags.NONE, None)
        return ia.get_attribute_string("id::filesystem") == ib.get_attribute_string("id::filesystem")
    except GLib.Error:
        return False


def transfer(sources, target: Gio.File, move: bool, done):
    """Copy or move files/folders into target. Same name: a numbered copy, nothing is overwritten."""
    def work(errors):
        for src in sources:
            name = src.get_basename()
            same_dir = src.get_parent() and src.get_parent().equal(target)
            if move and same_dir:
                continue
            dest = unique_child(target, name, copy_suffix=same_dir)
            cmd = ["mv", "-n", "--"] if move else ["cp", "-a", "--reflink=auto", "--"]
            r = subprocess.run(cmd + [src.get_path(), dest.get_path()], capture_output=True, text=True)
            if r.returncode != 0:
                errors.append(r.stderr.strip() or f"{name}: failed")
    _run(work, done)


def trash(files, done):
    def work(errors):
        for f in files:
            try:
                f.trash(None)
            except GLib.Error as e:
                errors.append(f"{f.get_basename()}: {e.message}")
    _run(work, done)


def delete_forever(files, done):
    def work(errors):
        for f in files:
            r = subprocess.run(["rm", "-rf", "--", f.get_path()], capture_output=True, text=True)
            if r.returncode != 0:
                errors.append(r.stderr.strip())
    _run(work, done)


def restore_from_trash(files, done):
    def work(errors):
        for f in files:
            try:
                info = f.query_info("trash::orig-path", Gio.FileQueryInfoFlags.NONE, None)
                orig = info.get_attribute_byte_string("trash::orig-path")
                if not orig:
                    continue
                dest = Gio.File.new_for_path(orig)
                if dest.query_exists(None):
                    dest = unique_child(dest.get_parent(), dest.get_basename())
                f.move(dest, Gio.FileCopyFlags.NOFOLLOW_SYMLINKS, None, None)
            except GLib.Error as e:
                errors.append(f"{f.get_basename()}: {e.message}")
    _run(work, done)


def empty_trash(done):
    def work(errors):
        trash_root = Gio.File.new_for_uri("trash:///")
        en = trash_root.enumerate_children("standard::name", Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS, None)
        for info in en:
            child = trash_root.get_child(info.get_name())
            try:
                _delete_recursive(child)
            except GLib.Error as e:
                errors.append(e.message)
    _run(work, done)


def _delete_recursive(f: Gio.File):
    try:
        en = f.enumerate_children("standard::name", Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS, None)
        for info in en:
            _delete_recursive(f.get_child(info.get_name()))
    except GLib.Error:
        pass
    f.delete(None)


def rename(f: Gio.File, new_name: str):
    """Raises GLib.Error on failure (shown to the user)."""
    return f.set_display_name(new_name, None)


def make_folder(parent: Gio.File, name="New folder"):
    d = unique_child(parent, name)
    d.make_directory(None)
    return d


def make_file(parent: Gio.File, name, template: Gio.File | None = None):
    f = unique_child(parent, name)
    if template:
        template.copy(f, Gio.FileCopyFlags.NONE, None, None)
    else:
        f.create(Gio.FileCreateFlags.NONE, None).close(None)
    return f


def folder_size(f: Gio.File, done):
    """Total size and item count of a folder, for the properties dialog."""
    result = {"size": 0, "files": 0, "dirs": 0}

    def work(errors):
        for root, dirs, files in os.walk(f.get_path()):
            result["dirs"] += len(dirs)
            for name in files:
                result["files"] += 1
                try:
                    result["size"] += os.lstat(os.path.join(root, name)).st_size
                except OSError:
                    pass
    _run(work, lambda errors: done(result))
