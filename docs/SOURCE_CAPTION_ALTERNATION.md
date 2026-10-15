# Complete-caption source alternation — v207

A caption may switch from a whole-line paint stack to words or individually
positioned gradient letters. Freezing each original event independently can make
both phases visible together. Source alternation already removes mutually
exclusive, complete layered phases; its collection now recognizes the caption
across different fragmentations with exact-font geometry.

## Source proof and paint selection

The source collector can include complete, two-piece and three-piece layouts in
an alternating family. Each literal fragment is expanded into its authored glyph
anchors at the held font size and alignment. Corresponding non-space characters
must agree within the existing 1.5-script-unit tolerance. Authored spaces supply
their actual advance even though the visible-word map trims edge whitespace.
There is no new size fit, tolerance increase or show-specific recognition.

Mixed fragmentations use the same complete layered visibility proof: at least
two paint layers per phase, complete literal coverage and exclusive contiguous
opaque spans over the cue. Independent outline/shadow visibility cannot borrow
a fill-only profile. Original events and parser caches remain read-only. Missing
exact measurements, contextual shaping, inline formatting within a fragment,
layout changes and incomplete/overlapping phases retain the uncertain family.
Ordinary stable-row and particle matching keep their existing admission rules.

The existing source-row clearance check rejects independent intervening paint
that could change compositing when the selected phase is held across the cue.
Distant measured peers remain eligible. The retained phase has the greatest
fully readable exposure; its number of words or letters does not multiply that
exposure. Equal-duration measured alternations prefer the earlier phase. Within
a chosen profile, fragment detail and paint-layer order still choose the row
representation. All selected gradient fill/outline spans pass through existing
stack ownership, row reconstruction, color normalization and outline policy.

## Shared lyric-boundary evidence

The text-stage owner captures surrounding-row signatures before glyph reduction.
`LyricBoundaryIndex` owns those pass-local dictionaries and sets; all consumers
borrow them read-only. It also includes ordinary neighboring text in an
established lyric lane: eligibility to merge a fragment does not limit context.

The existing glyph coalescer retains its established touching/fade rules.
Later frame and text-effect sequence mergers require a stronger boundary: a
complete row changes its literal text together and no letter continues through
the handoff. Paint layers share one caption lane; moving a caption between
planes, or changing its word/letter fragmentation, does not itself prove a new
lyric.
This distinction matters for staggered letters, where a changing subset is a
legitimate phase rather than a new caption. The same index is carried through
exact-position, scale-trail and final consolidation recursion. It prevents an
identical letter in consecutive lyrics from acquiring their union lifetime
before row reconstruction. Genuine same-caption phases remain mergeable.

The frame merger also consumes this evidence because identical paint can expose
the same timing error there before text-effect sequence merging runs. This is a
shared proof at the responsible producers, rather than a repair of reconstructed
caption times. No new Event history flags, serialized tags, pass or counter were
added. The index expires after these consumers finish; reconstructed rows inherit
the correctly bounded fragments.

## Validation

```sh
python validation/run_backend_check.py --backend windows tests/check_source_caption_alternation.py
python validation/run_backend_check.py --backend windows tests/check_source_caption_alternation_render.py
python validation/run_review_checks.py
python validation/run_source_alternation_corpus.py
python validation/check_source_alternation_scene.py
```

The focused checks exercise whole/word/glyph segmentation, two/three fragments,
a longer whole-line phase, equal exposure, enumeration order, exact geometry,
source immutability, visibility gaps/overlaps, independent paint, missing fonts,
intervening content, frame splitting, staggered subsets and repeated letters at
a real next-cue boundary. Both layered and single-plane next captions are
covered. Native checks compare an independently authored gradient caption and
its next cue on black, gray and white backgrounds, including boundary samples.

The real-scene diagnostic verifies the English ending caption at
21:59.01–22:04.26, its gradient fill/outline and the following complete caption.
It binds source/runtime/output hashes, checks native rendering with the embedded
Planewalker Bold font, and verifies full-file repeat conversion. The corpus
runner compares fresh outputs against the hash-bound v206 conversions with the
same exact fonts. Local fonts, subtitles and generated reports remain ignored.

## v207 results and follow-up evaluation

The focused check passed 130 behavioral/ownership assertions; synthetic native
rendering passed 80 checks. All 11 fresh exact-font corpus conversions completed
without missing fonts. Nine outputs and their statistics are unchanged from
v206. Demon Slayer has 470 → 467 dialogue events (477 → 474 parsed records),
with output peak concurrency 5 → 4. The target English cue becomes one gradient
caption over 21:59.01–22:04.26 instead of four overlapping paint fragments/copies.
Its following cue keeps complete text and its original interval; only its static
tag spelling changes. Other styles and cues are unchanged.

The only other corpus change is Overlord's 21:46.08–21:46.16 “If” phase: two
letter events become one word, reducing dialogue output by one. Fill, outline,
font and interval are unchanged. Exact Clearface SSi Bold measurements differ
from the old individual anchors by at most 0.84 script pixels, within the
existing 1.5-unit row tolerance. Native samples confirm that other pixels and
the surrounding timing remain unchanged. Thirteen real native samples cover
these two scenes; Demon Slayer's full-file repeat is byte-identical.

The work also corrected the same boundary loss in frame-animation merging and
included single-plane neighboring cues in complete-caption context. Regression
experiments exposed false boundaries from staggered subsets and paint-layer
changes; the final producer distinguishes those from a complete literal change
across the whole caption lane. No show-specific exceptions or late timing
repairs were introduced. No dedicated follow-up review is needed for this
change; the separately planned API and pass-local index reviews remain separate.

The complete 89-script Windows-backend regression suite passed with unchanged
runtime/harness inputs. The MKV extraction, simplification, remux/extraction and
font-sync smoke test also passed. Fresh reports are under
`validation/source-alternation-corpus` and `validation/backend-runs/windows`.
