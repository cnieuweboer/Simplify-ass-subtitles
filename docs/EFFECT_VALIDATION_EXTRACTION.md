# v232 — Shared source-effect proof helpers

`parse_effect_transform()` and `parse_effect_move()` now live in
`_simplify_ass/effect_validation.py`. `event_override_tokens()` now lives in the
existing `_simplify_ass/event_operations.py` owner. All three remain direct
engine aliases with unchanged signatures/defaults and implementation. This is a
structural extraction of 44 definition lines shared by 48 engine consumers.

## Responsibilities and dependency direction

The validators import only `math` and the canonical override tokenizer. Event
operations adds that same tokenizer import, borrowing its existing `Event` and
`OVERRIDE_RE` bindings. Neither owner imports the engine or a processing pass.
There is no callback adapter, duplicate policy, new context or global cache.

Raw event-token access reads the supplied event's original override blocks in
order and returns a new flat mutable list. It does not resolve formatting,
substitute a reconstructed descendant, install a cache or alter continuation.
The existing `OutlineStripEvidence.tokens_for()` family owns its exact-object
identity cache and tuple conversion. That cache remains in the engine, including
its original source lifetimes; equal source indices cannot share cached parsing.

Transform validation borrows each caller's allowed-tag set. When a caller lends
already-parsed changes, it validates and returns the same list without copying,
mutating, retaining or retokenizing it. Otherwise the existing tokenizer creates
the changes. Move validation returns the same source coordinate/timing list.
`None` refusals and malformed-input policy are unchanged.

Preserve all timing forms, finite/forward timing and positive acceleration,
existing transform endpoint rounding, explicit instant/after-end opt-ins and
caller-selected move slack. These strict source-effect proofs remain distinct
from the general freezer/sampler parser. Each caller retains effect-family
admission, source maps, geometry/paint evidence, caches, diagnostic ownership,
counters, stage placement and reporting.

Frame-echo processing and its five frozen records remain in the engine. This
preparation makes their remaining shared dependencies privately importable
without making general source-effect policy belong to echoes. The next larger
extraction still deserves its own assessment. `simplify_subtitles.py`, CLI policy
and installer/updater implementations are unchanged.

## Validation

The historical `validation/check_effect_validation_extraction.py` audit checks
all three moved definitions against v231, including unchanged remaining engine
AST except imports/version. Event operations gains only the raw reader and
canonical tokenizer import; all other private sources are byte-identical.
This release audit is excluded from routine checks and does not constrain future
implementations.

Eight new validator-module checks cover canonical aliases, annotations/defaults,
historical root lookup, four transform forms, finite/timing/tag refusals,
independent endpoint/instant/after-end bounds, borrowed changes and move slack.
Existing event-operations checks are retained and extended to eleven: raw reads
preserve order and leave resolved/unresolved events untouched, while outline
families retain exact source-identity caching. Existing outline parsing reuse
checks also retain their producer/consumer coverage.

Cold source and installed checks run from an unrelated working directory and an
installation path with spaces, before importing the engine or optional font
backends. Actual source-token and timing behavior is exercised, with canonical
owner identities and owned module/cache cleanup preserving a user file.

Acceptance requires the full 107-script Windows BASIC plus real HarfBuzz suite
on Linux, including native rendering, and fresh paired v231/v232 conversions of
all 13 corpus tracks with identical bytes and complete statistics. Required-font
guards reject missing exact fonts. Runtime/harness manifests and the 124 recorded
font hashes must stay unchanged during validation.

Delivery checks exercise the actual shipped v214 updater from a v231 installation.
Both the new validator module and modified event-operations owner are separately
simulated as locked, requiring exact rollback before a successful retry. Installed
source-effect proofs, launcher choices/user files and owned uninstall are checked.
Python/PowerShell recursive manifests, installer/updater suites and the MKV
extraction/conversion/remux/font-sync smoke workflow complete Linux validation.
Native Windows filesystem/launcher checks remain distinct limitations. Fresh
reports and private corpus artifacts stay under ignored
`validation/effect-validation-extraction/`.

Completed validation against the final 20-source runtime: all 107 regression
scripts passed, including eight validator-module and eleven event-operations
checks and all native rendering checks. Existing assertions and observer bindings
were retained. All 13 fresh v231/v232 corpus pairs were byte-identical with
identical complete statistics; all 124 font hashes were verified without missing
required-font diagnostics. Runtime and harness inputs stayed unchanged.

Installer checks passed 32 with two native Windows skips; updater checks passed
10 with one native Windows skip. Actual shipped-updater rollback for each affected
owner, retry, installed proofs/uninstall, Python/PowerShell manifest agreement and
the MKV smoke test passed. Native Windows filesystem and launcher behavior remains
unverified on this Linux host.

## After-release evaluation

The validators and raw reader retain their existing responsibilities while
consumers retain proof state, caches and reporting. No new workaround, local
exception, duplicated proof or ownership redesign was needed. The frame-echo
subsystem is a candidate for the next bounded assessment; this release does not
commit to a broader hierarchy or API/index redesign.

The existing scrolling single-use iterator exhaustion remains a separate
follow-up. Production supplies lists and is unaffected. Its behavior is unchanged
here; it is not a prerequisite for this preparation.
