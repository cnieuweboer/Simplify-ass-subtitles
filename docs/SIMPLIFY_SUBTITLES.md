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
ASS/SSA tracks. Individual qualification requires an extracted subtitle strictly
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
With interactive use, a settings summary and confirmation precede writing outputs.

The wrapper extracts ASS/SSA tracks together, then skips extracted tracks carrying
the engine's generated header marker. It extracts embedded fonts once per MKV
under numeric filenames. Per-file modes run one engine process for eligible
tracks; filtered add mode has an assessment phase and, when needed, a later
conversion phase for smaller members of selected groups. First-phase results
are reused; no track is converted twice.

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
