#!/usr/bin/env bash
# ./install.sh            launcher in ~/.local/bin and the app menu
# ./install.sh --default  also the default file manager (folders, "show in folder" from browsers)
# ./install.sh --undo-default  Nautilus again
set -euo pipefail
cd "$(dirname "$0")"
APP=io.github.himuraw.GlassFiles
BIN="$HOME/.local/bin/glass-files"
APPS="$HOME/.local/share/applications"
DBUS="$HOME/.local/share/dbus-1/services/org.freedesktop.FileManager1.service"

mkdir -p "$HOME/.local/bin" "$APPS"
ln -sfn "$PWD/bin/glass-files" "$BIN"
sed "s|^Exec=glass-files|Exec=$BIN|" "data/$APP.desktop" > "$APPS/$APP.desktop"
update-desktop-database -q "$APPS" || true

case "${1:-}" in
--default)
    xdg-mime default "$APP.desktop" inode/directory
    mkdir -p "$(dirname "$DBUS")"
    sed "s|@BIN@|$BIN|" data/org.freedesktop.FileManager1.service > "$DBUS"
    echo "Default file manager: Glass Files"
    ;;
--undo-default)
    xdg-mime default org.gnome.Nautilus.desktop inode/directory
    rm -f "$DBUS"
    echo "Default file manager: Nautilus"
    ;;
esac
echo "Installed: $BIN"
