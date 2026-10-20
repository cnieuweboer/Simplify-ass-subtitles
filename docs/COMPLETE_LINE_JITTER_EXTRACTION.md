# Complete-line jitter processing — v235

The seven processing functions and two existing frozen records assessed in
[the v234 assessment](COMPLETE_LINE_JITTER_EXTRACTION_ASSESSMENT.md) now live in
`_simplify_ass/complete_line_jitter.py`. Their definition ASTs are unchanged;
all nine engine names remain direct aliases. Other production definitions,
signatures/defaults and the processing pipeline are unchanged. The runtime
version is `2026.10.20.235`.

## Boundary and ownership

The module contains complete-caption frame admission, bounded-reversal and
readable-core proofs, corresponding paint-layer ownership, representative
caption construction and ordered replacement application. `JitterTextFamily`
and `CompleteLineJitterResult` retain their existing shallow freezing and field
identities. Their defining module changes naturally; engine aliases retain
historical root pickle lookup.

Working events, visibility, styles and original sources remain borrowed. Buckets,
ordered families, readable intervals, layer groups, removal IDs and replacements
remain local to each invocation. The family median anchor still serves grouping;
representative placement still uses original source-pose support. Existing event
replacement, static-state selection, source-paint rendering and pose-support
owners retain their policies and caches.

The output list borrows retained events and owns new caption successors.
`result.captions` contains the same successor objects as the output list.
`_consolidate_text_events()` still passes that exact tuple to the separate
word-echo proof immediately afterward, and retains original-source selection,
configuration and aggregate reporting. Frame reductions still contribute to
`text_effect_sequences_frozen`; stack reductions still contribute to
`stacked_text_copies_flattened`.

The new module imports only established private owners and standard-library
services. The graph is acyclic, with no reverse engine import, callback adapter,
new shared context, duplicate proof or font-resource owner. Frame-exit echoes
remain a separate operation with their distinct source/paint admission.

## Validation

Seven new boundary tests protect canonical aliases and resolved annotations,
root pickle lookup, shallow record freezing, retained/caption identity, borrowed
source/cache immutability, paint/timing/layer/row flags, source-pose support,
source refusals, independent invocations and inert repeated simplification.
Complete-pipeline observers check that both single-layer and stacked examples
hand the exact accepted-caption tuple to word-echo removal and report frame/stack
contributions correctly. Observers target the existing caller and defining owner;
production forwarding is unnecessary.

Cold source and installed children run from an unrelated directory with spaces
in the installation path. Both caption paths execute before importing the engine
or optional Pillow/fontTools/HarfBuzz backends. They verify unchanged inputs,
retained identity, accepted paint/timing/pose evidence and repeat behavior.
Owned uninstall removes the new source and compiled cache while preserving a
user file.

Acceptance uses the full 109-script Windows BASIC plus real HarfBuzz suite on
Linux, including native libass rendering, and fresh paired v234/v235 conversions
of all 13 corpus tracks. Required-font guards and all 124 recorded font hashes
protect corpus prerequisites. Complete runtime and harness hashes must remain
unchanged throughout validation. The shipped updater is exercised against a
v234 installation, including a locked new-module rollback, retry, preserved
launcher/user choices, isolated installed processing and uninstall. Recursive
Python/PowerShell manifest agreement and the MKV extraction/conversion/remux/font
sync smoke workflow complete delivery checks.

All 13 fresh v234/v235 corpus pairs are byte-identical with identical complete
statistics. All 124 recorded font hashes were verified with no missing
required-font diagnostic.

Completed validation against the final 22-source runtime: all 109 regression
scripts passed, including seven new module-boundary tests and every native
rendering check. Runtime and harness inputs stayed unchanged throughout the run.
Installer checks passed 32 with two native Windows skips; updater checks passed
ten with one native Windows skip. Actual shipped-updater rollback/retry,
isolated installed jitter proofs, owned uninstall, Python/PowerShell manifest
agreement and the MKV smoke workflow all passed. Production batch-wrapper and
delivery code bytes remain unchanged from v234.

Fresh reports and private outputs remain under ignored
`validation/complete-line-jitter-extraction/`. Native Windows filesystem and
launcher behavior requires separate Windows validation.

## After-release evaluation

The operation moved with its existing responsibilities and data flow intact.
No preparatory production release, workaround, local runtime exception, duplicated
proof or downstream repair was needed. No new dedicated follow-up was identified.
The previously reproduced masked-font initialization cleanup failure and scrolling
single-use iterator contract remain independent work; neither is changed here.
