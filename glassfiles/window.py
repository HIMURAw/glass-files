"""The window: tab strip, address row, command bar, sidebar, tabs, details pane, status bar."""
import os
import subprocess

from gi.repository import Adw, Gdk, GLib, Gio, Gtk, Pango

from . import ops
from .browser import Browser, HOME, location_name
from .model import human_date, human_size
from .sidebar import Sidebar

TEMPLATES = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_TEMPLATES)


def button(icon, tooltip, action=None, label=None, css=()):
    if label:
        b = Gtk.Button(tooltip_text=tooltip, css_classes=["flat", *css])
        content = Adw.ButtonContent(icon_name=icon, label=label)
        b.set_child(content)
    else:
        b = Gtk.Button(icon_name=icon, tooltip_text=tooltip, css_classes=["flat", *css])
    if action:
        b.set_action_name(action)
    return b


def menu_button(icon, label, model, tooltip):
    mb = Gtk.MenuButton(menu_model=model, tooltip_text=tooltip, css_classes=["flat", "gf-cmd"])
    mb.set_child(Adw.ButtonContent(icon_name=icon, label=label))
    return mb


class PathBar(Gtk.Stack):
    """Breadcrumbs; click the empty part (or Ctrl+L) to type a path."""

    def __init__(self, on_go):
        super().__init__(hexpand=True, css_classes=["gf-pathbar"], transition_type=Gtk.StackTransitionType.CROSSFADE,
                         transition_duration=120)
        self.on_go = on_go
        self.crumbs = Gtk.Box(spacing=0, css_classes=["gf-crumbs"])
        click = Gtk.GestureClick()
        click.connect("released", lambda g, n, x, y: self.edit() if self.crumbs.pick(x, y, 0) in (self.crumbs, self.filler) else None)
        self.crumbs_wrap = Gtk.Box(hexpand=True)
        self.crumbs_wrap.append(self.crumbs)
        self.filler = Gtk.Box(hexpand=True)
        self.crumbs_wrap.append(self.filler)
        self.crumbs_wrap.add_controller(click)
        self.add_named(self.crumbs_wrap, "crumbs")
        self.entry = Gtk.Entry(hexpand=True, css_classes=["gf-path-entry"])
        self.entry.connect("activate", self._typed)
        key = Gtk.EventControllerKey()
        key.connect("key-pressed", lambda c, kv, *_: (self.show_crumbs(), True)[1] if kv == Gdk.KEY_Escape else False)
        self.entry.add_controller(key)
        focus = Gtk.EventControllerFocus()
        focus.connect("leave", lambda *_: self.show_crumbs())
        self.entry.add_controller(focus)
        self.add_named(self.entry, "entry")
        self.location = None

    def set_location(self, f: Gio.File):
        self.location = f
        while (c := self.crumbs.get_first_child()):
            self.crumbs.remove(c)
        parts = []
        cur = f
        while cur is not None:
            parts.append(cur)
            if cur.equal(HOME):
                break
            cur = cur.get_parent()
        parts.reverse()
        for i, part in enumerate(parts):
            if i:
                self.crumbs.append(Gtk.Image(icon_name="go-next-symbolic", css_classes=["gf-crumb-sep"]))
            b = Gtk.Button(css_classes=["flat", "gf-crumb"])
            if part.equal(HOME):
                b.set_child(Adw.ButtonContent(icon_name="user-home-symbolic", label="Ev"))
            elif part.get_uri() == "trash:///":
                b.set_child(Adw.ButtonContent(icon_name="user-trash-symbolic", label="Çöp kutusu"))
            else:
                b.set_label(location_name(part))
            b.connect("clicked", lambda _b, p=part: self.on_go(p))
            self.crumbs.append(b)
        self.show_crumbs()

    def edit(self):
        if self.location:
            self.entry.set_text(self.location.get_path() or self.location.get_uri())
        self.set_visible_child_name("entry")
        self.entry.grab_focus()
        self.entry.select_region(0, -1)

    def show_crumbs(self):
        self.set_visible_child_name("crumbs")

    def _typed(self, entry):
        text = entry.get_text().strip()
        if not text:
            return
        f = Gio.File.new_for_commandline_arg(os.path.expanduser(text))
        if f.query_file_type(Gio.FileQueryInfoFlags.NONE, None) == Gio.FileType.DIRECTORY:
            self.on_go(f)
        else:
            entry.add_css_class("error")
            GLib.timeout_add(900, lambda: (entry.remove_css_class("error"), False)[1])


class DetailsPane(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10, css_classes=["gf-details-pane"],
                         width_request=260)
        self.image = Gtk.Image(pixel_size=96, css_classes=["gf-preview-icon"])
        self.picture = Gtk.Picture(content_fit=Gtk.ContentFit.CONTAIN, css_classes=["gf-preview"], visible=False,
                                   height_request=170)
        self.title = Gtk.Label(wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR, xalign=0, css_classes=["gf-preview-title"])
        self.subtitle = Gtk.Label(xalign=0, css_classes=["dim-label"])
        self.grid = Gtk.Grid(column_spacing=12, row_spacing=6, css_classes=["gf-props"])
        for w in (self.image, self.picture, self.title, self.subtitle, Gtk.Separator(), self.grid):
            self.append(w)

    def _rows(self, rows):
        while (c := self.grid.get_first_child()):
            self.grid.remove(c)
        for i, (k, v) in enumerate(rows):
            self.grid.attach(Gtk.Label(label=k, xalign=0, yalign=0, css_classes=["dim-label"]), 0, i, 1, 1)
            self.grid.attach(Gtk.Label(label=v, xalign=0, wrap=True, wrap_mode=Pango.WrapMode.CHAR,
                                       selectable=True, hexpand=True), 1, i, 1, 1)

    def show(self, browser: Browser):
        items = browser.selected_items()
        self.picture.set_visible(False)
        self.image.set_visible(True)
        if len(items) == 1:
            it = items[0]
            if it.thumbnail:
                self.picture.set_filename(it.thumbnail.decode() if isinstance(it.thumbnail, bytes) else it.thumbnail)
                self.picture.set_visible(True)
                self.image.set_visible(False)
            elif it.icon:
                self.image.set_from_gicon(it.icon)
            self.title.set_label(it.display_name)
            self.subtitle.set_label(it.type_desc)
            rows = []
            if not it.is_dir:
                rows.append(("Boyut", f"{human_size(it.size)} ({it.size:,} bayt)".replace(",", ".")))
            rows += [("Değiştirme", human_date(it.mtime))]
            if it.ctime:
                rows.append(("Oluşturma", human_date(it.ctime)))
            rows.append(("Konum", (it.file.get_parent().get_path() or it.file.get_parent().get_uri()) if it.file.get_parent() else ""))
            self._rows(rows)
        elif len(items) > 1:
            self.image.set_from_icon_name("edit-select-all-symbolic")
            self.title.set_label(f"{len(items)} öğe seçili")
            total = sum(i.size for i in items if i.size > 0)
            dirs = sum(1 for i in items if i.is_dir)
            self.subtitle.set_label(f"{dirs} klasör, {len(items) - dirs} dosya")
            self._rows([("Toplam boyut", human_size(total) + (" (klasörler hariç)" if dirs else ""))])
        else:
            self.image.set_from_icon_name("folder-symbolic")
            self.title.set_label(location_name(browser.location))
            self.subtitle.set_label(f"{browser.visible_count()} öğe")
            self._rows([("Konum", browser.location.get_path() or browser.location.get_uri())])


class Window(Adw.ApplicationWindow):
    def __init__(self, app, settings, location=None):
        super().__init__(application=app, title="Dosyalar", css_classes=["gf-window"])
        self.settings = settings
        w, h = settings.get("size", [1180, 720])
        self.set_default_size(w, h)
        if settings.get("maximized"):
            self.maximize()
        self.connect("close-request", self._save_state)

        self.toasts = Adw.ToastOverlay()
        self.set_content(self.toasts)
        view = Adw.ToolbarView(top_bar_style=Adw.ToolbarStyle.FLAT, bottom_bar_style=Adw.ToolbarStyle.FLAT)
        self.toasts.set_child(view)

        # Row 1: tabs, like Windows 11 Explorer's title bar.
        self.tabs = Adw.TabView()
        self.tabs.connect("notify::selected-page", lambda *_: self._on_tab_switched())
        self.tabs.connect("close-page", self._on_close_page)
        self.tabbar = Adw.TabBar(view=self.tabs, autohide=False, expand_tabs=False, css_classes=["gf-tabbar"],
                                 hexpand=False, halign=Gtk.Align.START)
        plus = Gtk.Button(icon_name="list-add-symbolic", tooltip_text="Yeni sekme (Ctrl+T)",
                          action_name="win.new-tab", css_classes=["flat", "gf-newtab"])
        self.tabbar.set_end_action_widget(plus)
        strip = Gtk.Box(css_classes=["gf-tabstrip"])
        strip.append(self.tabbar)
        strip.append(Gtk.Box(hexpand=True))  # empty title bar: drag the window from here
        strip.append(Gtk.WindowControls(side=Gtk.PackType.END, css_classes=["gf-controls"]))
        view.add_top_bar(Gtk.WindowHandle(child=strip))
        # Not expanding (so "+" sits right after the last tab, as in Windows), yet wide enough
        # for every tab up to the window's width; past that the tab bar scrolls.
        self.tabs.connect("notify::n-pages", lambda *_: self._size_tabbar())
        self.connect("notify::default-width", lambda *_: self._size_tabbar())
        self.connect("notify::maximized", lambda *_: GLib.idle_add(lambda: (self._size_tabbar(), False)[1]))

        # Row 2: navigation, path, search.
        nav = Gtk.Box(spacing=4, css_classes=["gf-navbar"])
        self.back_btn = button("go-previous-symbolic", "Geri (Alt+Sol)", "win.back")
        self.fwd_btn = button("go-next-symbolic", "İleri (Alt+Sağ)", "win.forward")
        self.up_btn = button("go-up-symbolic", "Üst klasör (Alt+Yukarı)", "win.up")
        for b in (self.back_btn, self.fwd_btn, self.up_btn, button("view-refresh-symbolic", "Yenile (F5)", "win.reload")):
            nav.append(b)
        self.pathbar = PathBar(lambda f: self.browser.navigate(f))
        nav.append(self.pathbar)
        self.search = Gtk.SearchEntry(placeholder_text="Bu klasörde ara", width_chars=24, css_classes=["gf-search"])
        self.search.connect("search-changed", lambda e: self.browser and self.browser.set_query(e.get_text()))
        nav.append(self.search)
        view.add_top_bar(nav)

        # Row 3: commands, like Windows 11's command bar.
        cmd = Gtk.Box(spacing=2, css_classes=["gf-cmdbar"])
        self.new_menu = Gio.Menu()
        cmd.append(menu_button("list-add-symbolic", "Yeni", self.new_menu, "Yeni klasör ya da dosya"))
        cmd.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL, css_classes=["gf-vsep"]))
        for icon, tip, act in [("edit-cut-symbolic", "Kes (Ctrl+X)", "win.cut"),
                               ("edit-copy-symbolic", "Kopyala (Ctrl+C)", "win.copy"),
                               ("edit-paste-symbolic", "Yapıştır (Ctrl+V)", "win.paste"),
                               ("document-edit-symbolic", "Yeniden adlandır (F2)", "win.rename"),
                               ("user-trash-symbolic", "Sil (Delete)", "win.trash")]:
            cmd.append(button(icon, tip, act, css=("gf-cmd-icon",)))
        cmd.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL, css_classes=["gf-vsep"]))
        cmd.append(menu_button("view-sort-descending-symbolic", "Sırala", self._sort_menu(), "Sıralama ve gruplama"))
        cmd.append(menu_button("view-grid-symbolic", "Görünüm", self._view_menu(), "Görünüm"))
        cmd.append(Gtk.Box(hexpand=True))
        cmd.append(button("view-dual-symbolic", "Ayrıntılar bölmesi (Alt+Shift+P)", "win.details-pane",
                          label="Ayrıntılar"))
        more = Gtk.MenuButton(icon_name="view-more-symbolic", menu_model=self._more_menu(), tooltip_text="Diğer",
                              css_classes=["flat"])
        cmd.append(more)
        view.add_top_bar(cmd)

        # Body: sidebar | tabs | details pane.
        self.sidebar = Sidebar()
        self.sidebar.connect("open", lambda _s, f, new_tab: self.open_tab(f) if new_tab else self.browser.navigate(f))
        self.details = DetailsPane()
        self.details_revealer = Gtk.Revealer(child=self.details, transition_type=Gtk.RevealerTransitionType.SLIDE_LEFT,
                                             reveal_child=settings.get("details_pane", False))
        center = Gtk.Box()
        self.tabs.set_hexpand(True)
        center.append(self.tabs)
        center.append(self.details_revealer)
        self.paned = Gtk.Paned(start_child=self.sidebar, end_child=center, shrink_start_child=False,
                               resize_start_child=False, position=settings.get("sidebar", 230),
                               css_classes=["gf-paned"])
        view.set_content(self.paned)

        # Status bar.
        status = Gtk.Box(spacing=12, css_classes=["gf-status"])
        self.status_count = Gtk.Label(xalign=0)
        self.status_sel = Gtk.Label(xalign=0, css_classes=["dim-label"])
        self.status_job = Gtk.Box(spacing=6, visible=False)
        self.status_job.append(Gtk.Spinner(spinning=True))
        self.status_job_label = Gtk.Label()
        self.status_job.append(self.status_job_label)
        status.append(self.status_count)
        status.append(self.status_sel)
        status.append(Gtk.Box(hexpand=True))
        status.append(self.status_job)
        for icon, mode, tip in (("view-list-symbolic", "details", "Ayrıntılar"), ("view-grid-symbolic", "icons", "Simgeler")):
            b = Gtk.Button(icon_name=icon, tooltip_text=tip, css_classes=["flat", "gf-status-btn"],
                           action_name="win.view", action_target=GLib.Variant("s", mode))
            status.append(b)
        view.add_bottom_bar(status)

        self._actions()
        self.browser = None
        self.open_tab(location or HOME)

    # ---------- Tabs ----------

    def open_tab(self, location, select=True):
        b = Browser(self.settings, location)
        page = self.tabs.append(b)
        page.set_title(location_name(location))
        page.set_icon(Gio.ThemedIcon.new("folder-symbolic"))
        b.connect("location-changed", self._on_location, page)
        b.connect("selection-changed", lambda *_: self._sync_status())
        b.connect("items-changed", lambda *_: self._sync_status())
        b.connect("open-in-tab", lambda _b, f: self.open_tab(f, select=False))
        b.connect("context-menu", self._context_menu)
        b.connect("transfer", lambda _b, files, dest, move: self.transfer(files, dest, move))
        self._view_shortcuts(b)
        if select:
            self.tabs.set_selected_page(page)
        return b

    def _size_tabbar(self):
        width = self.get_width() or self.get_default_size()[0]
        want = self.tabs.get_n_pages() * 210 + 48
        self.tabbar.set_size_request(max(260, min(want, width - 170)), -1)

    def _on_close_page(self, view, page):
        if view.get_n_pages() == 1:
            self.close()
            return True
        view.close_page_finish(page, True)
        return True

    def _on_tab_switched(self):
        page = self.tabs.get_selected_page()
        if not page:
            return
        self.browser = page.get_child()
        self.search.set_text(self.browser.query)
        self._on_location(self.browser, page)

    def _on_location(self, b, page):
        page.set_title(location_name(b.location))
        page.set_tooltip(b.location.get_path() or b.location.get_uri())
        if b is not self.browser:
            return
        self.pathbar.set_location(b.location)
        self.sidebar.highlight(b.location)
        self.search.set_placeholder_text(f"{location_name(b.location)} içinde ara")
        if self.search.get_text():
            self.search.set_text("")
        self.set_title(location_name(b.location))
        self._sync_nav()
        self._sync_status()
        self._fill_new_menu()

    def _sync_nav(self):
        b = self.browser
        self.lookup_action("back").set_enabled(bool(b.back_stack))
        self.lookup_action("forward").set_enabled(bool(b.forward_stack))
        self.lookup_action("up").set_enabled(b.location.get_parent() is not None)
        in_trash = b.location.get_uri().startswith("trash:")
        for name in ("new-folder", "new-file", "paste", "rename"):
            self.lookup_action(name).set_enabled(not in_trash)
        self.lookup_action("restore").set_enabled(in_trash)
        self.lookup_action("view").set_state(GLib.Variant("s", b.view_mode))
        self.lookup_action("group").set_state(GLib.Variant("s", b.group_mode))
        key, desc = b.current_sort()
        self.lookup_action("sort").set_state(GLib.Variant("s", key))
        self.lookup_action("descending").set_state(GLib.Variant("b", desc))

    def _sync_status(self):
        b = self.browser
        if not b:
            return
        n = b.visible_count()
        self.status_count.set_label(f"{n} öğe")
        sel = b.selected_items()
        if sel:
            size = sum(i.size for i in sel if i.size > 0)
            self.status_sel.set_label(f"{len(sel)} öğe seçili" + (f"  ·  {human_size(size)}" if size else ""))
        else:
            self.status_sel.set_label("")
        if self.details_revealer.get_reveal_child():
            self.details.show(b)

    # ---------- Menus ----------

    def _sort_menu(self):
        m = Gio.Menu()
        s = Gio.Menu()
        for label, key in (("Ad", "name"), ("Değiştirme tarihi", "date"), ("Tür", "type"), ("Boyut", "size")):
            s.append(label, f"win.sort::{key}")
        m.append_section(None, s)
        d = Gio.Menu()
        d.append("Azalan", "win.descending")
        m.append_section(None, d)
        g = Gio.Menu()
        for label, key in (("Gruplama yok", "none"), ("Tarihe göre grupla", "date"), ("Türe göre grupla", "kind")):
            g.append(label, f"win.group::{key}")
        m.append_section("Grupla", g)
        return m

    def _view_menu(self):
        m = Gio.Menu()
        v = Gio.Menu()
        v.append("Ayrıntılar", "win.view::details")
        v.append("Büyük simgeler", "win.view::icons")
        m.append_section(None, v)
        o = Gio.Menu()
        o.append("Ayrıntılar bölmesi", "win.details-pane")
        o.append("Gizli öğeler", "win.toggle-hidden")
        m.append_section("Göster", o)
        return m

    def _more_menu(self):
        m = Gio.Menu()
        a = Gio.Menu()
        a.append("Tümünü seç", "win.select-all")
        a.append("Yolu kopyala", "win.copy-path")
        a.append("Terminalde aç", "win.open-terminal")
        a.append("Yer imlerine ekle", "win.add-bookmark")
        m.append_section(None, a)
        b = Gio.Menu()
        b.append("Yeni pencere", "app.new-window")
        b.append("Çöp kutusunu boşalt", "win.empty-trash")
        b.append("Özellikler", "win.properties")
        m.append_section(None, b)
        return m

    def _fill_new_menu(self):
        self.new_menu.remove_all()
        basic = Gio.Menu()
        basic.append("Klasör", "win.new-folder")
        for label, key in (("Metin belgesi", "txt"), ("Markdown belgesi", "md"), ("Boş dosya", "empty")):
            basic.append(label, f"win.new-file::{key}")
        self.new_menu.append_section(None, basic)
        if TEMPLATES and os.path.isdir(TEMPLATES):
            tpl = Gio.Menu()
            for name in sorted(os.listdir(TEMPLATES)):
                if not name.startswith("."):
                    tpl.append(os.path.splitext(name)[0], f"win.new-file::tpl:{name}")
            if tpl.get_n_items():
                self.new_menu.append_section("Şablonlar", tpl)

    def _context_menu(self, browser, view, x, y, on_item):
        m = Gio.Menu()
        in_trash = browser.location.get_uri().startswith("trash:")
        if on_item:
            items = browser.selected_items()
            open_s = Gio.Menu()
            open_s.append("Aç", "win.open")
            if len(items) == 1 and items[0].is_dir:
                open_s.append("Yeni sekmede aç", "win.open-in-tab")
            elif len(items) == 1:
                open_s.append("Birlikte aç…", "win.open-with")
            m.append_section(None, open_s)
            edit = Gio.Menu()
            if in_trash:
                edit.append("Geri yükle", "win.restore")
            else:
                edit.append("Kes", "win.cut")
                edit.append("Kopyala", "win.copy")
                edit.append("Yeniden adlandır", "win.rename")
                edit.append("Yolu kopyala", "win.copy-path")
            m.append_section(None, edit)
            danger = Gio.Menu()
            if not in_trash:
                danger.append("Çöpe at", "win.trash")
            danger.append("Kalıcı olarak sil", "win.delete")
            m.append_section(None, danger)
            props = Gio.Menu()
            props.append("Özellikler", "win.properties")
            m.append_section(None, props)
        else:
            if in_trash:
                m.append("Çöp kutusunu boşalt", "win.empty-trash")
            else:
                m.append_submenu("Yeni", self.new_menu)
                paste = Gio.Menu()
                paste.append("Yapıştır", "win.paste")
                m.append_section(None, paste)
            view_s = Gio.Menu()
            view_s.append_submenu("Sırala", self._sort_menu())
            view_s.append_submenu("Görünüm", self._view_menu())
            m.append_section(None, view_s)
            extra = Gio.Menu()
            extra.append("Terminalde aç", "win.open-terminal")
            extra.append("Özellikler", "win.properties")
            m.append_section(None, extra)
        pop = Gtk.PopoverMenu(menu_model=m, has_arrow=False, halign=Gtk.Align.START)
        pop.set_parent(view)
        r = Gdk.Rectangle()
        r.x, r.y, r.width, r.height = int(x), int(y), 1, 1
        pop.set_pointing_to(r)
        pop.connect("closed", lambda p: GLib.idle_add(lambda: (p.unparent(), False)[1]))
        pop.popup()

    # ---------- Actions ----------

    def _actions(self):
        simple = {
            "new-tab": lambda: self.open_tab(self.browser.location if self.browser else HOME),
            "close-tab": lambda: self.tabs.close_page(self.tabs.get_selected_page()),
            "back": lambda: self.browser.go_back(),
            "forward": lambda: self.browser.go_forward(),
            "up": lambda: self.browser.go_up(),
            "reload": lambda: self.browser.reload(),
            "focus-location": lambda: self.pathbar.edit(),
            "focus-search": lambda: self.search.grab_focus(),
            "open": self._open,
            "open-in-tab": lambda: [self.open_tab(i.file, select=False) for i in self.browser.selected_items() if i.is_dir],
            "open-with": self._open_with,
            "open-terminal": self._open_terminal,
            "new-folder": self._new_folder,
            "cut": lambda: self._copy(cut=True),
            "copy": lambda: self._copy(cut=False),
            "paste": self._paste,
            "rename": self._rename,
            "trash": self._trash,
            "delete": self._delete,
            "restore": self._restore,
            "empty-trash": self._empty_trash,
            "select-all": lambda: self.browser.selection.select_all(),
            "properties": self._properties,
            "copy-path": self._copy_path,
            "add-bookmark": self._add_bookmark,
        }
        for name, fn in simple.items():
            a = Gio.SimpleAction.new(name, None)
            a.connect("activate", lambda _a, _p, fn=fn: fn())
            self.add_action(a)

        nf = Gio.SimpleAction.new("new-file", GLib.VariantType.new("s"))
        nf.connect("activate", lambda _a, p: self._new_file(p.get_string()))
        self.add_action(nf)

        def stateful(name, vtype, initial, on_change):
            a = Gio.SimpleAction.new_stateful(name, GLib.VariantType.new(vtype) if vtype else None, initial)

            def activate(act, param):
                if param is None:  # boolean toggle
                    param = GLib.Variant("b", not act.get_state().get_boolean())
                act.set_state(param)
                on_change(param)
            a.connect("activate", activate)
            self.add_action(a)

        stateful("view", "s", GLib.Variant("s", "details"), lambda v: self.browser.set_view(v.get_string()))
        stateful("group", "s", GLib.Variant("s", "none"), lambda v: self.browser.set_grouping(v.get_string()))
        stateful("sort", "s", GLib.Variant("s", "name"),
                 lambda v: self.browser.sort_by(v.get_string(), self.lookup_action("descending").get_state().get_boolean()))
        stateful("descending", None, GLib.Variant("b", False),
                 lambda v: self.browser.sort_by(self.lookup_action("sort").get_state().get_string(), v.get_boolean()))
        stateful("toggle-hidden", None, GLib.Variant("b", self.settings.get("show_hidden", False)), self._set_hidden)
        stateful("details-pane", None, GLib.Variant("b", self.settings.get("details_pane", False)), self._set_details)

        app = self.get_application()
        for action, keys in {
            "win.new-tab": ["<Ctrl>t"], "win.close-tab": ["<Ctrl>w"], "win.new-folder": ["<Ctrl><Shift>n"],
            "win.back": ["<Alt>Left"], "win.forward": ["<Alt>Right"], "win.up": ["<Alt>Up"],
            "win.reload": ["F5", "<Ctrl>r"], "win.focus-location": ["<Ctrl>l", "<Alt>d"],
            "win.focus-search": ["<Ctrl>f", "<Ctrl>e"], "win.toggle-hidden": ["<Ctrl>h"],
            "win.details-pane": ["<Alt><Shift>p"], "win.properties": ["<Alt>Return"],
            "win.copy-path": ["<Ctrl><Shift>c"], "app.new-window": ["<Ctrl>n"],
        }.items():
            app.set_accels_for_action(action, keys)

    def _view_shortcuts(self, browser):
        """Keys that would clash with typing live on the view only, not on the whole window."""
        ctl = Gtk.ShortcutController(scope=Gtk.ShortcutScope.LOCAL)
        for trigger, action in (("Delete", "win.trash"), ("<Shift>Delete", "win.delete"), ("F2", "win.rename"),
                                ("<Ctrl>c", "win.copy"), ("<Ctrl>x", "win.cut"), ("<Ctrl>v", "win.paste"),
                                ("<Ctrl>a", "win.select-all"), ("BackSpace", "win.back"),
                                ("<Ctrl>Return", "win.open-in-tab")):
            ctl.add_shortcut(Gtk.Shortcut(trigger=Gtk.ShortcutTrigger.parse_string(trigger),
                                          action=Gtk.NamedAction.new(action)))
        browser.add_controller(ctl)

    def toast(self, text):
        self.toasts.add_toast(Adw.Toast(title=text, timeout=3))

    def _job(self, text):
        self.status_job_label.set_label(text)
        self.status_job.set_visible(True)

    def _job_done(self, errors, ok_text=None):
        self.status_job.set_visible(False)
        if errors:
            self.toast("Hata: " + errors[0][:160])
        elif ok_text:
            self.toast(ok_text)

    def _files(self):
        return [i.file for i in self.browser.selected_items()]

    def _open(self):
        items = self.browser.selected_items()
        dirs = [i for i in items if i.is_dir]
        if len(items) == 1 and dirs:
            self.browser.navigate(dirs[0].file)
            return
        for d in dirs:
            self.open_tab(d.file, select=False)
        for i in items:
            if not i.is_dir:
                Gtk.FileLauncher(file=i.file).launch(self, None, None)

    def _open_with(self):
        items = self.browser.selected_items()
        if len(items) == 1:
            Gtk.FileLauncher(file=items[0].file, always_ask=True).launch(self, None, None)

    def _open_terminal(self):
        path = self.browser.location.get_path()
        if path:
            subprocess.Popen(["ptyxis", "--new-window", "-d", path], start_new_session=True)

    def _new_folder(self):
        try:
            d = ops.make_folder(self.browser.location)
        except GLib.Error as e:
            self.toast(e.message)
            return
        self._ask_name(d, select_all=True)

    def _new_file(self, kind):
        names = {"txt": "Yeni Metin Belgesi.txt", "md": "Yeni Belge.md", "empty": "Yeni dosya"}
        template = None
        if kind.startswith("tpl:"):
            name = kind[4:]
            template = Gio.File.new_for_path(os.path.join(TEMPLATES, name))
        else:
            name = names[kind]
        try:
            f = ops.make_file(self.browser.location, name, template)
        except GLib.Error as e:
            self.toast(e.message)
            return
        self._ask_name(f)

    def _ask_name(self, f, select_all=False):
        """Rename right after creating, as in Windows."""
        GLib.timeout_add(150, lambda: (self.browser.select_name(f.get_basename()), self._rename_file(f, select_all), False)[2])

    def _rename(self):
        items = self.browser.selected_items()
        if len(items) == 1:
            self._rename_file(items[0].file, items[0].is_dir)

    def _rename_file(self, f, select_all=False):
        name = f.get_basename()
        dialog = Adw.AlertDialog(heading="Yeniden adlandır")
        entry = Gtk.Entry(text=name, activates_default=True)
        dialog.set_extra_child(entry)
        dialog.add_response("cancel", "Vazgeç")
        dialog.add_response("ok", "Adlandır")
        dialog.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("ok")
        dialog.set_close_response("cancel")

        def respond(_d, response):
            new = entry.get_text().strip()
            if response != "ok" or not new or new == name:
                return
            if "/" in new:
                self.toast("Ad “/” içeremez")
                return
            try:
                g = ops.rename(f, new)
                GLib.timeout_add(200, lambda: (self.browser.select_name(g.get_basename()), False)[1])
            except GLib.Error as e:
                self.toast(e.message)
        dialog.connect("response", respond)
        dialog.present(self)
        stem = len(name) if select_all or "." not in name[1:] else name.rfind(".")
        GLib.idle_add(lambda: (entry.grab_focus(), entry.select_region(0, stem), False)[2])

    def _copy(self, cut):
        files = self._files()
        if not files:
            return
        app = self.get_application()
        app.clip = (files, cut)
        uris = "\n".join(f.get_uri() for f in files)
        gnome = ("cut\n" if cut else "copy\n") + uris
        provider = Gdk.ContentProvider.new_union([
            Gdk.ContentProvider.new_for_value(Gdk.FileList.new_from_array(files)),
            Gdk.ContentProvider.new_for_bytes("x-special/gnome-copied-files", GLib.Bytes.new(gnome.encode())),
            Gdk.ContentProvider.new_for_bytes("text/uri-list", GLib.Bytes.new((uris + "\r\n").encode())),
        ])
        self.get_clipboard().set_content(provider)
        self.toast(f"{len(files)} öğe {'kesildi' if cut else 'kopyalandı'}")

    def _paste(self):
        app = self.get_application()
        clip = self.get_clipboard()
        if clip.is_local() and app.clip:
            files, cut = app.clip
            if cut:
                app.clip = None
            self.transfer(files, self.browser.location, cut)
            return

        def got(c, res):
            try:
                value = c.read_value_finish(res)
            except GLib.Error:
                self.toast("Panoda dosya yok")
                return
            files = value.get_files() if hasattr(value, "get_files") else list(value)
            if files:
                self.transfer(files, self.browser.location, False)
        clip.read_value_async(Gdk.FileList, GLib.PRIORITY_DEFAULT, None, got)

    def transfer(self, files, dest, move):
        if not files:
            return
        self._job(f"{len(files)} öğe {'taşınıyor' if move else 'kopyalanıyor'}…")
        ops.transfer(files, dest, move, lambda errors: self._job_done(
            errors, f"{len(files)} öğe {'taşındı' if move else 'kopyalandı'}"))

    def _trash(self):
        if self.browser.location.get_uri().startswith("trash:"):
            self._delete()
            return
        files = self._files()
        if not files:
            return
        self._job("Çöpe atılıyor…")
        ops.trash(files, lambda errors: self._job_done(errors, f"{len(files)} öğe çöpe atıldı"))

    def _delete(self):
        files = self._files()
        if not files:
            return
        what = f"“{files[0].get_basename()}”" if len(files) == 1 else f"{len(files)} öğe"
        dialog = Adw.AlertDialog(heading="Kalıcı olarak silinsin mi?",
                                 body=f"{what} geri getirilemeyecek şekilde silinecek.")
        dialog.add_response("cancel", "Vazgeç")
        dialog.add_response("delete", "Kalıcı olarak sil")
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_close_response("cancel")

        def respond(_d, r):
            if r == "delete":
                self._job("Siliniyor…")
                ops.delete_forever(files, lambda errors: self._job_done(errors, f"{what} silindi"))
        dialog.connect("response", respond)
        dialog.present(self)

    def _restore(self):
        files = self._files()
        if files:
            ops.restore_from_trash(files, lambda errors: self._job_done(errors, f"{len(files)} öğe geri yüklendi"))

    def _empty_trash(self):
        dialog = Adw.AlertDialog(heading="Çöp kutusu boşaltılsın mı?",
                                 body="Çöp kutusundaki her şey kalıcı olarak silinecek.")
        dialog.add_response("cancel", "Vazgeç")
        dialog.add_response("empty", "Boşalt")
        dialog.set_response_appearance("empty", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_close_response("cancel")
        dialog.connect("response", lambda _d, r: r == "empty" and (
            self._job("Çöp kutusu boşaltılıyor…"),
            ops.empty_trash(lambda errors: (self._job_done(errors, "Çöp kutusu boşaltıldı"), self.browser.reload()))))
        dialog.present(self)

    def _copy_path(self):
        files = self._files() or [self.browser.location]
        text = "\n".join(f.get_path() or f.get_uri() for f in files)
        self.get_clipboard().set(text)
        self.toast("Yol kopyalandı")

    def _add_bookmark(self):
        f = (self._files() or [self.browser.location])[0]
        path = os.path.join(GLib.get_user_config_dir(), "gtk-3.0", "bookmarks")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a") as fh:
            fh.write(f.get_uri() + "\n")
        self.toast("Yer imlerine eklendi")

    def _properties(self):
        items = self.browser.selected_items()
        f = items[0].file if len(items) == 1 else self.browser.location
        try:
            info = f.query_info("standard::*,time::*,unix::*,owner::*,access::*", Gio.FileQueryInfoFlags.NONE, None)
        except GLib.Error as e:
            self.toast(e.message)
            return
        is_dir = info.get_file_type() == Gio.FileType.DIRECTORY
        rows = [("Tür", "Dosya klasörü" if is_dir else Gio.content_type_get_description(info.get_content_type() or "")),
                ("Konum", (f.get_parent().get_path() if f.get_parent() else "") or ""),
                ("Boyut", "hesaplanıyor…" if is_dir else human_size(info.get_size())),
                ("Değiştirme", human_date(info.get_modification_date_time().to_unix() if info.get_modification_date_time() else 0)),
                ("Sahip", info.get_attribute_string("owner::user") or ""),
                ("İzinler", oct(info.get_attribute_uint32("unix::mode") & 0o777)[2:] if info.has_attribute("unix::mode") else "")]
        body = Gtk.Grid(column_spacing=14, row_spacing=6)
        labels = {}
        for i, (k, v) in enumerate(rows):
            body.attach(Gtk.Label(label=k, xalign=0, css_classes=["dim-label"]), 0, i, 1, 1)
            lab = Gtk.Label(label=v, xalign=0, selectable=True, wrap=True, wrap_mode=Pango.WrapMode.CHAR)
            body.attach(lab, 1, i, 1, 1)
            labels[k] = lab
        dialog = Adw.AlertDialog(heading=info.get_display_name())
        dialog.set_extra_child(body)
        dialog.add_response("close", "Kapat")
        dialog.present(self)
        if is_dir and f.get_path():
            ops.folder_size(f, lambda r: labels["Boyut"].set_label(
                f"{human_size(r['size'])}  ·  {r['files']} dosya, {r['dirs']} klasör"))

    def _set_hidden(self, v):
        self.settings["show_hidden"] = v.get_boolean()
        self.settings.save()
        for i in range(self.tabs.get_n_pages()):
            self.tabs.get_nth_page(i).get_child().refilter()

    def _set_details(self, v):
        self.settings["details_pane"] = v.get_boolean()
        self.settings.save()
        self.details_revealer.set_reveal_child(v.get_boolean())
        self._sync_status()

    def _save_state(self, *_):
        if not self.is_maximized():
            self.settings["size"] = [self.get_width(), self.get_height()]
        self.settings["maximized"] = self.is_maximized()
        self.settings["sidebar"] = self.paned.get_position()
        self.settings.save()
        return False
