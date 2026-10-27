# Glass Files

A file manager for GNOME in the Mor / Dynamic Island look, laid out like Windows 11 Explorer.
Python + GTK 4 + libadwaita.

- Tabs always on top, **+** for a new tab (Ctrl+T, Ctrl+W, middle-click a folder)
- Address bar with breadcrumbs (click the empty part or Ctrl+L to type), search in the folder (Ctrl+F)
- Command bar: **Yeni** (folder, text, Markdown, empty file, templates), cut / copy / paste / rename / delete, sort, view
- Details list with compact rows, or large icons with thumbnails
- Groups by date (Today, Yesterday, Earlier this week, Last week, Earlier this month, Last month, Earlier this year, A long time ago) — Downloads is grouped by date by default — or by kind
- Sidebar: quick access, bookmarks, drives with a usage bar, trash
- Details pane (Alt+Shift+P), status bar with item count and selection size
- Delete goes to the trash; Shift+Delete asks first. Copying never overwrites: same name becomes "name (2)"
- Live folder updates, drag and drop, clipboard shared with Nautilus and other apps
- `org.freedesktop.FileManager1` on D-Bus, so "show in folder" from browsers opens it

Install: `./install.sh` (add `--default` to make it the default file manager, `--undo-default` to go back).

## License

GPL-3.0
