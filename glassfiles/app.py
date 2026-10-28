"""Glass Files: a file manager in the Mor / Dynamic Island look, laid out like Windows 11 Explorer."""
import json
import os
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gio, Gtk  # noqa: E402

from . import tint  # noqa: E402
from .window import Window  # noqa: E402

APP_ID = "io.github.himuraw.GlassFiles"
CONFIG = os.path.join(GLib.get_user_config_dir(), "glass-files", "settings.json")
HERE = os.path.dirname(os.path.abspath(__file__))

FM1_XML = """
<node>
  <interface name="org.freedesktop.FileManager1">
    <method name="ShowFolders"><arg type="as" name="URIs" direction="in"/><arg type="s" name="StartupId" direction="in"/></method>
    <method name="ShowItems"><arg type="as" name="URIs" direction="in"/><arg type="s" name="StartupId" direction="in"/></method>
    <method name="ShowItemProperties"><arg type="as" name="URIs" direction="in"/><arg type="s" name="StartupId" direction="in"/></method>
  </interface>
</node>"""


class Settings(dict):
    def __init__(self):
        super().__init__()
        try:
            with open(CONFIG) as fh:
                self.update(json.load(fh))
        except (OSError, ValueError):
            pass

    def save(self):
        os.makedirs(os.path.dirname(CONFIG), exist_ok=True)
        tmp = CONFIG + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(self, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, CONFIG)


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID,
                         flags=Gio.ApplicationFlags.HANDLES_OPEN | Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.settings = Settings()
        self.clip = None
        self._service = False
        a = Gio.SimpleAction.new("new-window", None)
        a.connect("activate", lambda *_: self.new_window())
        self.add_action(a)

    def do_startup(self):
        Adw.Application.do_startup(self)
        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.PREFER_DARK)
        self.css = Gtk.CssProvider()
        self._load_css()
        # Above the user's gtk.css (800): the Mor theme cuts corners at 45°, the file manager is softer.
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), self.css, 900)
        # The colour theme (tema-rengi) changes live: style.css is violet, recoloured on load.
        os.makedirs(tint.CONFIG.parent, exist_ok=True)
        self._tema = Gio.File.new_for_path(str(tint.CONFIG.parent)).monitor_directory(Gio.FileMonitorFlags.NONE, None)
        self._tema.connect("changed", lambda _m, f, *_: f.get_basename() == "current.json" and self._load_css())
        Gio.bus_own_name(Gio.BusType.SESSION, "org.freedesktop.FileManager1",
                         Gio.BusNameOwnerFlags.ALLOW_REPLACEMENT | Gio.BusNameOwnerFlags.REPLACE,
                         self._on_bus, None, None)

    def _load_css(self):
        path = os.environ.get("GF_CSS") or os.path.join(HERE, "style.css")
        with open(path) as fh:
            css = tint.recolor_css(fh.read())
        # Glass (cam) changes shape too: rounded white frost on top, its colours already final.
        if tint.current().get("round"):
            with open(os.path.join(HERE, "style-cam.css")) as fh:
                css += fh.read()
        self.css.load_from_string(css)

    def _on_bus(self, conn, _name):
        node = Gio.DBusNodeInfo.new_for_xml(FM1_XML)
        conn.register_object("/org/freedesktop/FileManager1", node.interfaces[0], self._on_call)

    def _on_call(self, _conn, _sender, _path, _iface, method, params, invocation):
        uris = params.unpack()[0]
        files = [Gio.File.new_for_uri(u) for u in uris]
        if method == "ShowFolders":
            for f in files:
                self.new_window(f)
        elif files:
            # ShowItems / ShowItemProperties: open the parent and select the item.
            win = self.new_window(files[0].get_parent() or files[0])
            name = files[0].get_basename()
            GLib.timeout_add(400, lambda: (win.browser.select_name(name), False)[1])
        invocation.return_value(None)
        if self._service:
            self._service = False
            self.release()

    def new_window(self, location=None):
        win = Window(self, self.settings, location)
        win.present()
        return win

    def do_activate(self):
        self.new_window()

    def do_open(self, files, _n, _hint):
        """Several folders open as tabs of one window; a file opens its folder with it selected."""
        win = None
        for f in files:
            is_dir = f.query_file_type(Gio.FileQueryInfoFlags.NONE, None) == Gio.FileType.DIRECTORY
            folder = f if is_dir else (f.get_parent() or f)
            if win is None:
                win = self.new_window(folder)
            else:
                win.open_tab(folder)
            if not is_dir:
                GLib.timeout_add(400, lambda w=win, n=f.get_basename(): (w.browser.select_name(n), False)[1])

    def do_command_line(self, cmdline):
        args = cmdline.get_arguments()[1:]
        if "--service" in args:
            # Started by D-Bus activation for FileManager1: stay up until the call arrives.
            if not self._service:
                self._service = True
                self.hold()
                GLib.timeout_add_seconds(20, lambda: (self._service and (setattr(self, "_service", False), self.release()), False)[1])
            return 0
        targets = [a for a in args if not a.startswith("-")]
        if not targets:
            self.activate()
        else:
            self.do_open([cmdline.create_file_for_arg(a) for a in targets], len(targets), "")
        return 0


def main():
    # No display (D-Bus activation while the session is ending): nothing to show, leave quietly.
    if not Gtk.init_check():
        return 0
    return App().run(sys.argv)
