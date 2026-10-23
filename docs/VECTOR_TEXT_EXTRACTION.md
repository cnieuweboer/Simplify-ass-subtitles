# Vector-caption recovery — v254

The complete vector-caption recovery subsystem now lives in
`_simplify_ass/vector_text.py`: fourteen functions and the existing frozen
`VectorTextFitContext`. Definitions, signatures, decorators, defaults and
matching policy moved unchanged. The engine retains direct aliases for all
fifteen names. Its version is `2026.10.23.254`.

## Boundary and responsibilities

The module owns authored and inferred cue discovery, stationary drawing-run
admission, exact-font contour and fragment-order proofs, representative paint,
caption reconstruction and unique source-claim arbitration. Uncertain,
incomplete, competing and already text-backed families retain their current
refusal behavior. Internal inferred comments remain cue evidence; they are not
emitted as new output comments.

The engine's `_prepare_source_text()` retains level gating, configuration,
invocation order, source/timing handoffs and aggregate reporting. Its remaining
executable AST is unchanged apart from imports and version. Existing private
modules are byte-identical. The batch wrapper, CLI options and report catalogs
are unchanged.

Dependencies point from engine to vector recovery to the existing private event,
override, font, fitting, sampling, freezing, geometry and rendering owners.
Time formatting remains in the document module. There are no engine imports,
callback adapters, new contexts or result hierarchies. No resource paths or
`__file__` behavior moved. Standalone import requires neither the engine nor
optional font backends. The existing delivery contract discovers the new file.

## Data, caches and diagnostics

Input events, styles, defaults, metrics, optional matcher and report remain
borrowed. Resolved source views pair formatting with parser continuation without
installing partial caches on borrowed events. Drawing indexes, run groups,
decoded cues, proposals and source claims remain local to recovery.

| Resource or result | Preserved owner and contract |
| --- | --- |
| Font resources and measurements | The supplied `FontMetrics`, including exact-face, contour and shaping caches. |
| Decoder profiles | `FontOutlineMatcher`, borrowed for batch reuse or constructed locally when omitted. Profiles contain no source-event evidence. Preserve the metric-owner identity check. |
| Source/text outline fits | The per-call `VectorTextFitContext.cache`, including positive Event results and negative `None` results. Frozen bindings retain a mutable cache; no source fits survive into another recovery call. |
| Missing-font findings | The existing selective vector producer writes to the caller's optional `FontProcessingReport`. Lifetime and batch accumulation remain caller choices. |
| Source ownership | Accept only uniquely claimed complete families. Retain ambiguous sources and independently accepted proposals. |
| Output | The same event-map/count tuple. Refusal returns the original map; untouched events retain identity. Accepted output preserves source IDs and existing dictionary insertion order. Count recovered captions, including captions consuming multiple drawing frames. |

## Behavioral coverage and provenance

The active outline-matcher check now directly protects source/text cache reuse,
refusal caching, call isolation, frozen context bindings, unique versus competing
claims, retained event/map identity, dictionary order and recovered-caption
counts. It also checks direct aliases, resolvable annotations and independent
imports. The former live-source ownership AST equality check is replaced by
these behavioral assertions. The historical full harness and its exact helper
counts are not reactivated.

Interpreter observers and row-fit doubles follow the defining vector consumer.
Pipeline observers continue using the engine entry alias. Production has no
forwarding for test spies. Local one-release AST evidence independently verifies
that every moved definition and the remaining engine algorithm are unchanged.

Fresh manifests and results are kept under `validation/vector-text-extraction/`.
The runtime comprises 38 Python sources. Baselines are the verified v253 corpus
outputs, bound to their runtime, input, output and exact-font hashes.

Fresh final results:

- All 121 regression scripts passed, including the native libass checks.
  Complete runtime and covered harness hashes remained unchanged throughout.
- The active outline check passed 1,276 assertions, including 91 decoder search
  cases, 249 vector integration cases, two focused conversions and the new
  cache/ownership/module contracts. All 4,936 geometry/reporting checks and
  179,958 effect-continuation checks also passed.
- All 13 corpus outputs are byte-identical to v253, with identical complete
  statistics, unchanged source files and exact fonts, and no missing families.
- The batch wrapper is byte-identical to v253. Installer/module checks include
  the new source through automatic discovery without delivery-code changes.

These results exercise the Windows font backend (Pillow BASIC plus real
HarfBuzz) on Linux; they do not claim native Windows filesystem or PowerShell
validation. `final-regression-checks.json`, `corpus-summary.json` and
`release-verification.json` retain the fresh evidence.

## After-release evaluation

The extraction moves one cohesive proof/reconstruction subsystem with its own
call-local evidence and ownership application. Shared caches, diagnostics and
pipeline responsibilities retain their established owners. No new workaround,
duplicated proof, local exception or dedicated behavioral follow-up is needed.
Previously recorded unrelated second-conversion issues remain outside this
structural release.
