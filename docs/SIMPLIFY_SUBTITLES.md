# MKV simplification wrapper

`simplify_subtitles.py` replaces the end-user BAT/PowerShell orchestration.
`simplify_ass.py` remains the conversion engine. The wrapper uses the active
Python interpreter and MKVToolNix, with no imports from the engine or other tools.

```console
python simplify_subtitles.py
python simplify_subtitles.py -i media -o cleaned -f fonts --recursive
python simplify_subtitles.py -i media --replace-originals --process-all-tracks --yes
python simplify_subtitles.py -i media --report run.json
python simplify_subtitles.py -i media --workers 4
```

Input accepts a folder or one MKV and defaults to the script's folder. A single
file processes only that MKV, even with `--recursive`. Folder scans stay
nonrecursive unless `-r` / `--recursive` is supplied. Output defaults to
`output/` beside each source MKV. Explicit `-o` / `--output` preserves paths
relative to the input folder, without including that folder's own name. Additional
font folders (`-f`, repeatable) supplement embedded fonts. Optional recursion
excludes output folders. Existing outputs are skipped.

Individual track qualification requires an extracted subtitle strictly
larger than 50,000 bytes and an event-count reduction strictly greater than 10%.
Thresholds are configurable.

In **filtered add mode**, qualification selects groups across the entire batch.
Groups use exact track name, language tag, and source subtitle format. If any
member qualifies, every unmarked member of that group gets a simplified copy,
including smaller or less-reduced tracks. Groups with no qualifying members
remain original-only. Absent tracks are not created. Existing outputs and files
that fail assessment do not contribute to qualifying groups. **Filtered replace
mode** retains per-track qualification; **all-tracks mode** retains its previous behavior.

Filtered add mode reads metadata before the existing confirmation. It warns
when the first five letters of filenames differ (ignoring case and stripping
leading bracketed release-group blocks), or when subtitle-group sets differ.
It lists differing groups with their presence counts. These checks are advisory,
not proof of a single show, and never block a confirmed batch. Recursive input
is still one batch; cancel and split unrelated shows when necessary. `--yes`
prints the checks but bypasses the confirmation. `--yes` uses add/filtered defaults unless options override them.
One settings menu offers **Use default settings** or **Adjust settings** for
original-track handling, ASS/SSA processing policy, scrolling concurrency, and
minimum caption color hold. Defaults keep originals and use filtered tracks:
press `1`, then `y` at confirmation to start. The editor lists all current values;
select a setting to change it or `0` to finish. Numeric input accepts Enter to keep
the current value. Command-line values are fixed; supplying all four skips the menu.
`--yes` uses defaults or supplied values without prompting.
The optional color-change rate cap is CLI-only: `--color-phase-change-interval`
defaults to `0` (unlimited); use a positive value to enable it.
A settings summary and confirmation precede writing outputs. Menu choices accept
single keypresses; new numeric values require Enter. `q` cancels, and confirmation
accepts `y` or `n`. Redirected input requires Enter after each answer.

The wrapper extracts ASS/SSA tracks together, then skips extracted tracks carrying
the engine's generated header marker. It extracts embedded fonts once per MKV
under numeric filenames. Subtitle tracks within one MKV run in separate engine
processes, using half the logical CPU count by default (minimum one), capped at
the number of eligible tracks. `--workers N` overrides the limit; `--workers 1`
uses one engine process for all eligible tracks and shares its font cache.
MKVs stay sequential, and diagnostics and summaries appear in track order.
Failure or cancellation stops active children before temporary data is removed.
Filtered add mode simplifies all original ASS/SSA tracks during
assessment, including small tracks. The displayed count includes all these
tracks. Size and reduction thresholds still determine which groups qualify;
writing reuses the assessed results without simplifying any track twice.

For batch assessment, all extracted subtitles are retained until group decisions
are made. Only subtitle files, fonts, statistics, and small option files live in
temporary storage. Videos remain at their original paths. Writing remuxes or
unchanged copies happens one MKV at a time; each episode's temporary data is
deleted afterward, and the remaining run data is cleaned on failure/cancellation.
This retains one combined subtitle extraction pass and one remux/copy pass per
source, with metadata and attachment operations in addition. `--temp-dir` chooses
an existing parent folder for temporary data (default: system temporary folder). Unsupported subtitle
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

Normal console output shows the current file/stage, extraction counts such as
`Extracting fonts... [9/9]`, and one event/peak-concurrency summary per converted
track. Detailed filter counters remain in `--report` JSON. Child-process chatter
is captured; missing-font warnings, other diagnostics, and failures remain visible.

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
per-file outcomes. Filtered add reports also include `GroupConsistency`, group
presence/qualification counts in `Groups`, and `QualifiedIndividually` alongside
`SelectedForRemux` for converted tracks. Missing counters remain missing. Scrolling-drop warnings appear
per track and in the final run summary. Exit status is nonzero for failures,
including report-writing errors. A Windows no-argument console launch pauses at
the end; other invocations do not pause.

```sh
python tests/check_simplify_subtitles.py
python tests/check_simplify_batch.py
python tests/check_simplify_workers.py
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

Batch checks use real MKVToolNix with a deterministic test engine to exercise the
A/B/C episode scenario, smaller forced members, absent groups, unchanged replace
and all-tracks policies, extraction/conversion reuse, advisories before confirmation,
and temporary-file cleanup after verification failures. The original focused
suite separately exercises the production simplification engine.

Whole-caption color phases use `--color-phase-min-hold` (default 1 second) and
`--color-phase-change-interval` (default 2 seconds of caption duration per allowed
change). Zero disables the corresponding restriction; both zero allow all
structurally proved phases. Reports identify affected captions, removed changes
and the limiting reason. See [CAPTION_COLOR_PHASES.md](CAPTION_COLOR_PHASES.md).
