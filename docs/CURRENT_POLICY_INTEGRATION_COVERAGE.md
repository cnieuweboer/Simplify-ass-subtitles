# Current-policy integration coverage — v199

This is a test release. The production engine and its v198 version string remain
unchanged; generated subtitles and statistics must match the saved v198 outputs.
No simplification bounds, pose selection, inline paint policy or outline budget
change in this release.

## Historical contracts and current paint

All 16 checks that substituted the v197 renderer now run the actual renderer and
source-paint selection. The substitution helper is removed. Historical parser,
selection and ownership comparisons remain useful, but their old neutral contour
paint is not a specification for the current engine.

`contour_independent_contract()` excludes only outline color, opacity and widths
(`3c`, `3a`, `bord`, `xbord`, `ybord`) from those cross-version comparisons. Fill,
content, timing, geometry, source history, visibility updates and identity decisions
remain compared. Borrowed-input snapshots and same-version checks retain their
complete values. This projection never patches a production function. Its focused
checks verify that fill, opacity, font, placement, text, timing, layers and source
identity differences remain detectable.

Existing targeted geometry/timing doubles and immutable historical scope audits
are retained where they answer their original, distinct questions. This release
removes the paint substitution, rather than claiming every historical test is an
unmodified full-pipeline integration test. The full-lyric trace now compares static
selection; renderer argument spelling and replacement call details are no longer
cross-version requirements.

The live `check_current_paint_handoffs.py` independently asserts soft opaque,
translucent and deliberately absent contours through complete-copy selection,
confirmed animated row assembly, source-only row normalization, translated
entrance/held phases, text-effect freezing, overlap trimming and final phase joins.
It uses exact Volkhov font geometry, checks source immutability, and requires
intentional contour differences to block a phase join. The v198 source-paint and
v197 measured-backing/glow checks remain active.

## Native compositing and phase coverage

The Overlord late-phase check compares the current full pipeline with its final
join enabled and disabled. Both sides retain current paint, final serialization
and earlier passes. It requires identical paint/multiplicity at every boundary,
equivalent final records, accounted-for merge counters, stable concurrency and
pixel-identical renders where active record order changes. The fixture's current
31 joins are evidence of useful reduction, not a fixed future admission count.

The Sword caption/backdrop check retains its historical placement/layer oracle.
It now proves visible caption contribution by rendering the current output with
and without that caption, and requires identical first/second/third current
renders. An old opaque contour is no longer its pixel specification. Existing
independent-mask and ownership counterexamples remain exact checks.

For historical handoff/second-pass comparisons, a contour-independent visibility
timeline accommodates identical touching phases coalescing. It retains literal
fill/layout multiplicity at every boundary. Same-version native checks provide
the complementary compositing-order proof.

The staggered-fade check's unrelated second-pass comparison now uses a current
pipeline control with staggered-core derivation disabled. v179's old paint also
produces different second-pass layer assignments, so requiring those unrelated
layers would test obsolete rendering behavior. The current control comparison
retains exact contour paint, geometry and layers; all first-pass literal fill,
placement and layers remain checked against the historical timing fixture.

## Reproduction

From the repository root with restored fonts/fixtures and the prepared tools:

```sh
python validation/run_review_checks.py
python validation/run_current_policy_corpus.py
```

The corpus runner requires the verified current-engine v198 results under
`validation/contrast-fallback-corpus/windows`, or an explicit `--baseline` folder
saved before test changes. It validates all ten source, engine and baseline
checksums before regenerating outputs under `validation/current-policy-corpus/windows`.
Output checksums and statistics must match exactly; missing fonts fail validation.
Generated reports, fonts and subtitle files remain local ignored assets.
The suite report hashes shared Python test helpers as well as checks and runner
files, and fails if runtime or harness inputs change during validation.

## Release evaluation

The implementation restores live paint coverage without changing runtime policy
or adding another compatibility renderer. Historical comparisons have an explicit
limited purpose; current contour behavior has direct assertions and native
integration coverage. No additional runtime defect was identified during the
migration. The extra historical-fixture phase join was already v198 behavior.

The broader historical harness still contains implementation/scope audits and
some targeted timing/geometry adaptations. A wholesale harness redesign is not
required to complete this release. Future feature work should extend current
behavioral checks rather than add new substitutions. The planned pose-evidence
handoff (v200), whole-span paint ownership (v201), and thick-outline decision
(v202) remain separate work.

The pose-evidence handoff is now implemented in v200; see
[REPRESENTATIVE_FRAME_POSES.md](REPRESENTATIVE_FRAME_POSES.md). Whole-span paint
ownership and thick-outline policy remain separate follow-ups.

Whole-span paint ownership is now implemented in v201; see
[INLINE_PAINT_OWNERSHIP.md](INLINE_PAINT_OWNERSHIP.md). Thick-outline policy remains
the next separate follow-up.

## Completed validation

All 76 Windows-backend regression scripts pass, including 177 new live-paint
handoff assertions, 107 caption/backdrop assertions, 1,798 late-phase assertions
and 36 pixel-identical phase order/boundary samples. The 96 source-contrast,
253 proved-backing and 309 glow-paint checks also pass. Runtime and test/helper
hashes were stable throughout the final suite run.

All ten freshly regenerated corpus files and their statistics match the verified
v198 results exactly; no exact fonts are missing. All 37 Python wrapper/batch,
worker and flag checks pass. The MKV extraction, font shaping, simplification,
remuxing and font-sync smoke test passes. Native Windows/PowerShell and macOS
execution are outside this Linux validation.
