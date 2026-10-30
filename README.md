# Glass Files

A file manager for GNOME, written in Python with GTK 4 and libadwaita, laid out like Windows 11 Explorer: tabs on top, an address bar with breadcrumbs, a command bar, a sidebar and a details pane.

<!-- screenshot: Glass Files window on Downloads in dark mode, grouped by date ("Today", "Yesterday", ...), two tabs open, sidebar with Quick access and a drive usage bar on the left, details pane open on the right with a selected file -->

Part of [himura-desktop](https://github.com/HIMURAw/himura-desktop), but it works on its own.

## Features

- **Tabs** in the title bar, with **+** for a new tab. Middle-click a folder to open it in a new tab.
- **Address bar** with clickable breadcrumbs. Click the empty part, or press `Ctrl+L`, to type a path.
- **Search** filters the current folder by name as you type.
- **Command bar** with a **New** menu (folder, text document, Markdown document, empty file, and every file in your Templates folder), cut, copy, paste, rename, delete, sort and view menus.
- **Two views:** a details list (name, date modified, type, size; click a column header to sort) or large icons with thumbnails from your thumbnail cache.
- **Grouping** by date (Today, Yesterday, Earlier this week, Last week, Earlier this month, Last month, Earlier this year, A long time ago) or by kind (Folders, Documents, Pictures, Videos, Music, Archives, Programs, Other). Downloads is grouped by date, newest first, until you change it.
- **Sidebar** with Quick access (Home, Desktop, Downloads, Documents, Pictures, Music, Videos), your bookmarks, "This PC" (the system drive and mounted drives, each with a free-space bar) and the trash.
- **Details pane** showing the selected item, or the folder; **status bar** with item count and size of the selection.
- **Safe by default.** Delete moves to the trash; permanent deletion asks first. Copying never overwrites: a name that is taken becomes `name (2)`. Files are copied or moved in the background with a spinner in the status bar.
- **Trash** has Restore and Empty trash.
- **Drag and drop** of files into the list or onto a folder: a drop moves the files when source and target are on the same filesystem, and copies otherwise.
- **Live updates:** the list follows changes on disk.
- **Clipboard** shared with Nautilus and other apps, in the usual GNOME formats.
- **Remembers** window size, sidebar width, hidden-files and details-pane settings, and the view, grouping and sort you picked for each folder.
- **Default file manager** option, including the `org.freedesktop.FileManager1` D-Bus service, so "Show in folder" in browsers and other apps opens Glass Files.

## Keyboard shortcuts

| Keys | What it does |
| --- | --- |
| `Ctrl+T` / `Ctrl+W` | New tab / close tab |
| `Ctrl+N` | New window |
| `Ctrl+L` or `Alt+D` | Edit the path |
| `Ctrl+F` or `Ctrl+E` | Search this folder |
| `Alt+Left` / `Alt+Right` / `Alt+Up` | Back / forward / up |
| `Backspace` | Back (in the file list) |
| `F5` or `Ctrl+R` | Refresh |
| `Ctrl+Shift+N` | New folder (then type its name) |
| `Ctrl+X` / `Ctrl+C` / `Ctrl+V` | Cut / copy / paste (in the file list) |
| `Ctrl+A` | Select all (in the file list) |
| `F2` | Rename |
| `Delete` | Move to trash (permanent in the trash) |
| `Shift+Delete` | Delete permanently, after a confirmation |
| `Ctrl+Enter` | Open the selected folder in a new tab |
| `Alt+Enter` | Properties |
| `Ctrl+Shift+C` | Copy the path |
| `Ctrl+H` | Show or hide hidden items |
| `Alt+Shift+P` | Show or hide the details pane |

The mouse's back and forward buttons also go back and forward. The "More" menu (three dots) has Select all, Copy path, Open in Terminal, Add to bookmarks, New window, Empty trash and Properties.

## Requirements

- Python 3 with PyGObject
- GTK 4 and libadwaita (the code uses `Gtk.CssProvider.load_from_string`, from GTK 4.12, and `Adw.AlertDialog`, from libadwaita 1.5, so those are the minimums)
- `desktop-file-utils` and `xdg-utils` for the installer
- Made for GNOME 50; other desktops with GTK 4 and libadwaita are untested

## Install

### 1. With the himura-desktop installer

```bash
curl -fsSL https://raw.githubusercontent.com/HIMURAw/himura-desktop/main/install.sh | bash -s -- files
```

To also make it your default file manager:

```bash
curl -fsSL https://raw.githubusercontent.com/HIMURAw/himura-desktop/main/install.sh | bash -s -- files --default-file-manager
```

### 2. From source

| Distro | Packages |
| --- | --- |
| Fedora | `sudo dnf install git python3 python3-gobject gtk4 libadwaita desktop-file-utils xdg-utils` |
| Ubuntu / Debian | `sudo apt install git python3 python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 desktop-file-utils xdg-utils` |
| Arch | `sudo pacman -S git python python-gobject gtk4 libadwaita desktop-file-utils xdg-utils` |

```bash
git clone https://github.com/HIMURAw/glass-files
cd glass-files
./install.sh
```

This links `~/.local/bin/glass-files` to the checkout and adds an app-menu entry named **Files**. Make sure `~/.local/bin` is in your `PATH`. Update with `git pull`.

You can also run it without installing: `./bin/glass-files [folder ...]`.

### Make it the default file manager

```bash
./install.sh --default        # folders open in Glass Files
./install.sh --undo-default   # back to Nautilus
```

`--default` sets Glass Files as the handler for `inode/directory` and installs a D-Bus service file for `org.freedesktop.FileManager1` in `~/.local/share/dbus-1/services`, so "Show in folder" and "Open containing folder" from browsers and other apps start Glass Files. `--undo-default` hands folders back to Nautilus and removes the service file.

### Uninstall

```bash
./install.sh --undo-default
rm ~/.local/bin/glass-files ~/.local/share/applications/io.github.himuraw.GlassFiles.desktop
rm -r ~/.config/glass-files    # optional: forget window size and per-folder views
```

If you used the himura-desktop installer, this does the same:

```bash
curl -fsSL https://raw.githubusercontent.com/HIMURAw/himura-desktop/main/uninstall.sh | bash -s -- files
```

## Usage

```bash
glass-files                 # open your home folder
glass-files ~/Pictures      # open a folder
glass-files ~/a ~/b         # several folders open as tabs of one window
glass-files ~/notes.txt     # open the folder with the file selected
```

## Configuration

There is no settings window. Glass Files keeps its state in `~/.config/glass-files/settings.json`; edit it while the app is closed.

| Key | Meaning |
| --- | --- |
| `size` | Window width and height, `[1180, 720]` by default |
| `maximized` | Start maximized |
| `sidebar` | Sidebar width in pixels, 230 by default |
| `details_pane` | Details pane shown |
| `show_hidden` | Hidden items shown |
| `default_view` | `details` or `icons`, for folders you have not set up yet |
| `folders` | Per-folder view, grouping and sort, saved automatically |

Other places it reads: bookmarks come from `~/.config/gtk-3.0/bookmarks` (shared with Nautilus and other GTK file choosers; "Add to bookmarks" writes there), and the New menu lists files from your Templates folder (`xdg-user-dir TEMPLATES`, usually `~/Templates`). The app asks for the dark style (`PREFER_DARK`).

## Colour themes

On its own, Glass Files is violet. With the Mor theme from [himura-desktop](https://github.com/HIMURAw/himura-desktop), `tema-rengi` recolours it live: the app watches `~/.config/tema/current.json` and reloads its stylesheet when it changes, no restart needed. Known themes: `turkuaz` (turquoise), `yesil` (green), `mavi` (blue), `mor` (violet), `gri` (grey) and `cam` (glass, which also rounds the corners).

```bash
tema-rengi mavi
```

## Troubleshooting

**`glass-files: command not found`.** Add `~/.local/bin` to your `PATH`, or run `./bin/glass-files` from the checkout.

**`ValueError: Namespace Adw not available`** (or Gtk 4.0). The libadwaita or GTK 4 typelib is missing; install the packages from the table above.

**"Show in folder" still opens Nautilus.** Run `./install.sh --default`, then log out and in so the session picks up the new D-Bus service file. Check `xdg-mime query default inode/directory`; it should print `io.github.himuraw.GlassFiles.desktop`.

**Open in Terminal does nothing.** It starts `ptyxis` (the GNOME terminal on recent Fedora), so that terminal has to be installed.

**Thumbnails are missing.** Large-icon view shows thumbnails that already exist in your thumbnail cache; it does not generate them itself. Browse the folder in another app, or install the thumbnailers for your file types.

**Something looks wrong or crashes.** Start it from a terminal (`glass-files`) and read the output.

## Contributing

Issues and pull requests are welcome. The code is in `glassfiles/`: `window.py` (window, menus, actions, shortcuts), `browser.py` (one tab: listing, views, drag and drop), `sidebar.py`, `ops.py` (copy, move, trash, run off the UI thread), `model.py` (file items and date groups), `style.css` and `style-cam.css`, and `tint.py` (colour themes). Keep the UI text in English.

## License

GPL-3.0. See [LICENSE](LICENSE).
