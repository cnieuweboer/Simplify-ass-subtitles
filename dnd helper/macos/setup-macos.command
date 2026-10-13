#!/bin/sh
set -eu
source_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
for tool in subtitle_flags remove_subtitles sync_fonts; do
    app="$source_dir/$tool.app"
    if [ -e "$app" ]; then
        printf 'Already exists: %s\n' "$app"
        continue
    fi
    /usr/bin/osacompile -o "$app" "$source_dir/$tool.applescript"
    printf 'Created: %s\n' "$app"
done
printf '\nDrop MKV folders onto the new apps. Press Enter to close: '
read -r answer || true
