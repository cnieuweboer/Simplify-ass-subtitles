#!/bin/sh
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd) || exit 2
script="$script_dir/subtitle_flags.py"
status=0
if [ ! -f "$script" ]; then
    printf 'Missing Python script: %s\n' "$script"
    status=2
else
    if [ "$#" -eq 0 ]; then set -- "$script_dir"; fi
    for folder in "$@"; do
        if [ ! -d "$folder" ]; then
            printf 'Drop a folder containing MKVs: %s\n' "$folder"
            status=2
            break
        fi
    done
    if [ "$status" -eq 0 ]; then
        for folder in "$@"; do
            python3 "$script" "$folder" || status=1
        done
    fi
fi
if [ -t 0 ]; then
    printf '\nPress Enter to close: '
    read -r answer || true
fi
exit "$status"
