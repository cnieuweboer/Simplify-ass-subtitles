# Source-backed fade timing and handoffs — v259

Complete faded-cue processing lives in `_simplify_ass/cue_fades.py`: sixteen
functions and the existing frozen `FadedCueContext`, `FadedCueEvidence` and
`CueFadeFamily` records, about 687 definition lines. All nineteen definitions
moved unchanged, including signatures, defaults, fields, decorators and bodies.
The engine retains direct aliases for every moved name. Its version is
`2026.10.24.259`.

## Boundary, preparation and benefit

The module owns source-backed readable fade cores, complete cue-family discovery,
collision-boundary evidence, safe cutoff selection, cross-lane synchronization
and timing trims to proved owned backing captions. These are cooperating parts
of one timing proof, so they stay together. Family discovery supplies evidence;
only the trimming stage applies timing changes. Existing ambiguity, geometry,
compositing and protected-frame requirements remain unchanged.

`_select_readable_core_handoff()` retains its second consumer in whole-caption
color-phase processing. Both consumers use the same centisecond-representable
cutoff policy. The cue-specific wrapper still adds its row-extent proof; no
duplicated selector or callback is introduced.

Moving `without_inert_spacing_tail()` unchanged into the existing `text_freezing`
module is the small preparation included in this release. The normalizer is
shared by stack preparation and fade proofs. It removes only non-painted trailing
tracking resets, preserving painted inline changes and all other trailing tags.
It borrows the source and uses canonical event replacement for accepted edits;
refusals return the original Event. Visible-text interpretation remains with the
existing freezer. Dependencies remain acyclic without moving text parsing into
the lower-level event-operations owner.

One processing module now contains the complete fade timing algorithm, reducing
unrelated engine code without separating its closely cooperating proofs. The
engine retains pipeline order, source selection, evidence handoffs and reporting.
No new contexts, records, adapters, persistent caches or ownership rules are
introduced. No resource paths, configuration, CLI options, batch wrapper or
counter catalogs change. Delivery discovers the new private source automatically.

## Dependencies and ownership

The engine imports cue processing; cue processing imports existing event,
override, geometry, effect-validation, static-selection, row-evidence,
text-freezing and time-formatting owners. The shared normalizer depends on event
replacement and the existing interpreter. No private module imports the engine.
Cold importing the new module needs neither the engine nor optional font backends.

| Resource | Preserved responsibility |
| --- | --- |
| Events, rows and source maps | Borrowed from callers, including original formatting, continuation, source identity and historical evidence. Source normalization creates successors rather than editing borrowed caches. |
| Fade cores | Derived only from complete matching source evidence. Accepted rows are shallow successors; unchanged rows retain identity and pieces remain borrowed. Existing stronger cores are retained. |
| Proof caches and indexes | Successful/refused source proofs, provenance, slots, family groups, collision pairs and synchronization components remain local to a call. |
| Records | Frozen bindings retain shallow sharing of their existing dictionaries, sets, tuples and Events. No new default containers or result hierarchy. |
| Timing application | The pass owns its replacement buffer. Backing trimming changes only that buffer after complete ownership proof; input events and rows remain borrowed. |
| Results | Existing list/count and evidence returns are unchanged. Untouched Events retain identity and original list order; no-collision trimming returns the original list. Handoff counts count successful cue transitions, not changed events. |
| Fonts and diagnostics | No measurement owner, font handles, font caches or diagnostic/report lifetime moves into the subsystem. |

`_consolidate_text_events()` retains core derivation, family collection, trimming
and aggregate counts. `_finalize_text_layout()` retains its later trimming call.
`_caption_phase_runs()` retains color-phase reconstruction and uses the direct
alias of the shared cutoff selector. These caller bodies are unchanged.

## Validation

The active cue-family test covers staggered entrances/exits, incomplete source
correspondence, paint transforms, repeated fades, reconstructed provenance,
unrepresentable cutoffs, ambiguous ownership and actual source phases. Added
checks protect direct aliases, resolved annotations, frozen/shallow record
contracts, source immutability, no-collision identity, trailing-spacing behavior
and independent imports. It now passes 80 checks.

Existing staggered-core, synchronization, whole-caption crossfade, backing-paint,
conversion and native-rendering checks continue to exercise the real algorithms.
Interpreter observers and historical timing mocks target the defining consumer;
pipeline spies still target engine entry aliases. Historical AST scope audits
remain historical rather than constraining the new module structure.

One-release AST evidence verifies all twenty moved definitions and the unchanged
remaining engine/text-freezing algorithms. Every other private runtime source
and `simplify_subtitles.py` remains byte-identical to v258. Fresh runtime manifests
cover all 45 Python sources. Local evidence is kept under
`validation/cue-fade-extraction/` and is not published with fixtures or fonts.

Required validation uses the Windows font backend (Pillow BASIC plus real
HarfBuzz) on Linux, including native libass rendering. It does not claim native
Windows filesystem or PowerShell validation.

All 121 regression scripts passed, including native rendering. All thirteen
full-track outputs and complete statistics records match the hash-bound v258
baseline. Required exact fonts and source bytes are unchanged, with no missing
families. Runtime and covered harness inputs remained unchanged throughout the
full run.

Final housekeeping removed one extra empty line at the end of the new module.
The full-suite and corpus manifests remain recorded exactly as tested; the saved
tested source and `final-formatting-check.json` prove this sole difference
produces identical compiled code. The final 80-check cue-family run, independent
imports and structural audit passed against the final 45-source manifest.
`final-regression-checks.json`, `corpus-summary.json`, `structure-checks.json`
and `release-verification.json` retain the local release evidence.

## After-release evaluation

The boundary preserves the existing timing and backing-ownership proof, including
the selector shared with color phases. The small shared normalizer has an existing
owner, and both pipeline placements remain with their callers. No workaround,
duplicated proof, local exception or new dedicated behavioral review was needed.
Previously documented unrelated issues remain outside this structural release.
