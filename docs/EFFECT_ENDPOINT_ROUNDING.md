# Effect endpoint rounding — v234

The source-effect validators rejected some authored endpoints exactly at the
existing limit. A cue from 2.0 to 2.4 seconds subtracts to
`0.3999999999999999` seconds; its duration plus the 50 ms allowance becomes
`449.9999999999999` ms, rejecting an authored endpoint of 450 ms. The same issue
affects timed moves with zero slack and strict transform validation.

## Responsibility and policy

`_simplify_ass/effect_validation.py` owns the correction. Both upper-endpoint
comparisons receive the same absolute `1e-6` ms allowance: one nanosecond. This
absorbs floating-point arithmetic error, including cancellation when subtracting
later cue timestamps, without introducing duration-relative tolerance. Authored
slack remains zero for ordinary timed moves, caller-supplied for opted-in moves,
and 50 ms for strict transforms. Values returned to callers are unchanged.

Finite values, nonnegative starts, endpoint ordering, acceleration, allowed tags,
instant-transform and after-end opt-ins retain their existing rules. Supplied
parsed-change lists retain their identity. No frame-echo exception, late repair,
new cache or pipeline change is needed; both echo proof paths consume the fixed
shared validation.

## Validation

The new cases first failed against v233. The validator checks exercise exact
endpoints with subtracted cue times through 24 hours, unchanged returned values
and borrowed list identity. They reject real overruns down to `0.00001` ms on
both short and 24-hour cues, guarding against an unintended relative tolerance.
Negative starts and equal move endpoints remain invalid.

Both stacked and flattened source-backed echo fixtures now use the exact 450 ms
boundary rather than the temporary 449 ms interior example. Existing source,
paint, geometry, lifetime and refusal checks remain active. Cold source/installed
checks cover the corrected endpoints from unrelated directories and paths with
spaces, without requiring optional rendering libraries during private imports.

All 13 fresh v233/v234 corpus comparisons are byte-identical with identical
complete statistics. All 124 recorded font hashes were verified; there were no
missing required-font diagnostics. Fresh regression, corpus and delivery evidence
remains local under ignored `validation/effect-endpoint-rounding/`.

Completed validation against the final 21-source runtime: all 108 regression
scripts passed on Linux using Windows BASIC plus real HarfBuzz, including native
libass rendering, ten validator module checks and eleven echo module checks.
Runtime and harness inputs stayed unchanged throughout the run.

Installer checks passed 32 with two native Windows skips; updater checks passed
ten with one native Windows skip. The actual shipped updater passed rollback,
retry, isolated installed endpoint proofs and uninstall. Recursive Python and
PowerShell manifests agreed, and the MKV extraction/conversion/remux/font-sync
smoke workflow passed. Native Windows filesystem and launcher behavior remains
unverified on this Linux host.

## After-release evaluation

The fix is shared at the existing validator owner. It introduces no workaround,
duplicate proof, downstream repair or new ownership boundary. No additional
dedicated review was identified by this change. The previously recorded scrolling
single-use iterator contract and deferred global API/pass-local index reviews
remain independent work.
