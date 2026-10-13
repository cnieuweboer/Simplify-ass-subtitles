# MKV simplification wrapper

`simplify_subtitles.py` replaces the end-user BAT/PowerShell orchestration.
`simplify_ass.py` remains the conversion engine. The wrapper uses the active
Python interpreter and MKVToolNix, with no imports from the engine or other tools.

```console
python simplify_subtitles.py
python simplify_subtitles.py -i media -o cleaned -f fonts --recursive
python simplify_subtitles.py -i media --replace-originals --process-all-tracks --yes
python simplify_subtitles.py -i media --report run.json
```

Input defaults to the script's folder; output defaults to INPUT/output. Additional
font folders (`-f`, repeatable) supplement embedded fonts. Optional recursion
preserves relative paths and excludes output folders. Existing outputs are skipped.

The two menus choose adding versus replacing tracks and filtered versus all
ASS/SSA tracks. Filtering requires an extracted subtitle strictly larger than
50,000 bytes and an event-count reduction strictly greater than 10%. Thresholds
are configurable. `--yes` uses add/filtered defaults unless options override them.
With interactive use, a settings summary and confirmation precede writing outputs.

The wrapper extracts ASS/SSA tracks together, then skips extracted tracks carrying
the engine's generated header marker. It extracts embedded fonts once per MKV
under numeric filenames and runs one engine process for all eligible tracks.
This keeps the engine's font index shared within that MKV. Unsupported subtitle
formats remain untouched. MKVs with no eligible replacements are copied unchanged.
An unmarked original can still be simplified when its file also contains an older
simplified copy; marker checks apply to each track's contents.

Scrolling concurrency defaults to **0**, explicitly disabling that text-dropping
fallback. `--scroll-concurrency-limit 32` enables it. The engine's own default is
unchanged. Deprecated level 2 remains available through `--level 2`.

Added tracks follow their originals, receive ` (Simplified)` (or `Simplified`
for unnamed originals), and have default/forced flags cleared. Replacement tracks
occupy the original positions and inherit names, language tags, and flags. Other
tracks retain their order and identities. Fonts and other attachments remain.

Outputs use temporary files. Before publishing a remux, verification checks track
count/order, codec, names, language tags, flags, retained track UIDs, attachment
metadata, and chapter/global-tag counts. MKVToolNix's removal of directory
components from attachment names is accepted. These are metadata checks, not
complete payload comparisons. Source size/modification time is checked before
publishing; failures discard partial files and processing continues. Copies use
a temporary file too. Source MKVs and existing outputs are never intentionally
overwritten. MKVToolNix warning exit code 1 is reported and results are verified;
engine conversion must exit successfully.

`--report` retains the previous wrapper's JSON fields and counter aliases, adding
per-file outcomes. Missing counters remain missing. Scrolling-drop warnings appear
per track and in the final run summary. Exit status is nonzero for failures,
including report-writing errors. A Windows no-argument console launch pauses at
the end; other invocations do not pause.

```sh
python tests/check_simplify_subtitles.py
```

The focused checks cover menus, cancellation, threshold boundaries, marker
encodings, codec detection, report aliases, recursive exclusions, and safeguards.
With MKVToolNix and the Python font dependencies, real tests build temporary MKVs
using DejaVu Sans regular, subtitles, audio, attachments, chapters, and video when
FFmpeg is available. They exercise both remux modes, rejected thresholds, repeated
marked input, explicit scrolling limits, existing-output skips, and failure cleanup.
The synthetic font defaults to `/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf`;
`SIMPLIFY_SUBTITLES_TEST_FONT` can supply it elsewhere. An alternate engine can be
selected with `SIMPLIFY_SUBTITLES_TEST_ENGINE`. No user media is modified.
