# Complete boundary-glyph matching — v246

The boundary assessed in
[BOUNDARY_GLYPH_EXTRACTION_ASSESSMENT.md](BOUNDARY_GLYPH_EXTRACTION_ASSESSMENT.md)
now lives in `_simplify_ass/boundary_glyphs.py`. Twelve functions and two existing
frozen records moved unchanged: 211 definition lines including decorators.
The existing twelve-line `_parse_simple_source_fade()` has moved unchanged to
`effect_validation.py`, shared with the caption-color-phase producer. Engine names
remain direct aliases, preserving signatures, canonical identity and historical
root record lookup. Runtime version: `2026.10.21.246`.

## Responsibility and ownership

The module owns rotating-entrance/flying-exit classification, complete ordered
literal matching, exact-font anchor fitting, protected absorbed holds and unique
removal authorization. It keeps brief independent holds, closest-anchor selection,
tracking allowance and rejection of duplicate, partial or ambiguous groups. Source
fade, movement, transform and boundary tolerances are unchanged. Departing-glyph
processing stays separate because it consumes reconstructed rows and different
outline/layer/trajectory proofs.

Working events, visibility, original source maps, styles/defaults and metrics remain
borrowed. Initial evaluation creates local formatting/continuation and shallow
source views. Caption/effect indexes, candidate deduplication, sorted peers,
protected IDs, proposals and ownership counts belong to one invocation. The two
frozen records retain their intentionally shallow mutable payloads. Font discovery,
shaping and measurement caches stay with the supplied FontMetrics. No persistent
cache, font handle, diagnostic owner or result type was introduced.

The result remains a fresh set of removable source IDs. Protected absorbed glyphs
can prove a slot without becoming removable. Captions retain independent entrance
and exit ownership; effects must have unique ownership. Original source timing and
geometry remain distinct from the retained caption's extended lifetime.

`remove_covered_fragment_effects()` retains source gating, stage order relative to
departing/staggered glyph matching, ID aggregation/application, later shadow/fragment
proofs, row timing successors, output construction and reporting.

The shared fade parser still requires exactly one `fad`, no `fade` and two finite
nonnegative values, returning a fresh list without changing tokens. It does not
validate cue duration or choose a core. Boundary profiling keeps its own phase
bounds; `_caption_phase_source()` keeps readable-core decisions. Neither producer
imports the other, and the helper does not become new fade policy.

The private graph is acyclic and has no reverse engine imports, callbacks or
production forwarding. All outgoing dependencies already have private owners.
No path-sensitive code moves; the production wrapper and delivery scripts are
unchanged.

## Validation and delivery

Nine new module tests protect aliases/annotations/historical lookup; read-only
maps and unresolved-source immutability; complete, partial, ambiguous and gapped
families; independent entrance/exit ownership; absorbed holds; shallow frozen
records; missing metrics, failed fits and failure isolation; strict shared parsing
and caption-core policy; and cold installed exact-font supported/refused processing
from an unrelated path containing spaces, followed by owned uninstall.

Interpreter observers include the defining boundary consumer. The existing
effect-continuation check installs its recording/failed-fit double at the imported
fit binding, scoped to boundary scenarios. The shrinking-row module check also
observes the shared query at its defining boundary consumer. Production needs no
observer adapters.
The historical boundary-stage harness remains archived: its builders supply cases
without imposing obsolete single-file helper counts or historical timing policy.

Fresh v245/v246 direct comparisons cover 3,915 cases across 87 scenarios, three
working-event orders, three source-map orders and five measurement modes.
Removal decisions and recorded fit calls match; borrowed input values and working
formatting dictionary identity remain unchanged. Both focused whole conversions
retain identical output hashes, complete statistics and font reports under the
actual current paint/timing policy.

Native libass checks use the actual covered-fragment caller for accepted entrance,
exit and combined families, plus partial, ambiguous and absorbed cases. All 54 frame
pairs match with exact Arial regular, including entrance/exit boundaries. Bounded
repeat processing retains output. These checks are not a claim of general whole-file
idempotence.

All 118 current regression scripts pass using Windows BASIC plus real HarfBuzz on
Linux. Runtime and harness manifests remain fixed throughout that run. All thirteen
strict-font corpus tracks retain identical output bytes and complete statistics;
all 124 recorded font hashes are verified, with no missing required fonts.

The unchanged recursive installer/updater deliver the new module without a filename
list. The shipped v214 updater is exercised against a v245 installation, including
rollback when either the new module or changed validation owner is locked, successful
retry, preserved launcher choices/user files, cold installed processing and owned
uninstall. Python and PowerShell recursive manifests agree on all 33 runtime sources.
Installer tests pass 32 with two native Windows skips; updater tests pass ten with
one native Windows skip. The MKV extraction/simplification/remux/font-sync smoke
check also passes, preserving sources. Native Windows filesystem and launcher
behavior remain unverified in this Linux environment.

Fresh reports, generated subtitles, fonts, native frames and the pinned v245
baseline remain ignored under `validation/boundary-glyph-extraction/`.

## After-release evaluation

The extraction preserves one owner from phase classification through final removal
authorization, while its caller still applies IDs, constructs row successors and
reports counts. Both shared-parser consumers retain distinct policy. No production
adapter, duplicated proof, local exception or conflicting evidence lifetime was
introduced or uncovered. No new dedicated corrective review is indicated. The
existing scrolling iterator contract and global API/pass-local-index reviews remain
separate.
