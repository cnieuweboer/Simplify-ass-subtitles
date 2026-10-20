"""Complete backed-glyph row proof and pulse replacement.

Caller inputs remain borrowed; indexes, evidence and edits belong to one call.
Source-fragment orchestration and later text-row assembly keep their owners.
"""
from __future__ import annotations

from dataclasses import dataclass, replace as dataclass_replace
import math
import unicodedata

from .ass_overrides import (
    OverrideContinuation, OverrideEvaluation, apply_override, DEFAULT_STATE,
)
from .event_model import Event
from .event_operations import event_evaluation, event_override_tokens, replace_event
from .effect_validation import parse_effect_transform
from .font_metrics import FontMetrics
from .caption_geometry import inline_layout_key, text_height, text_layout_key
from .caption_rendering import SourceCaptionPaint, render_simplified_caption
from .caption_paint_sampling import _settled_caption_paint_samples, _pool_source_caption_paint
from .subtitle_document import format_time


@dataclass(frozen=True)
class BackedPulseContext:
    """Original glyph maps and parsed effect/backing indexes for one pulse pass."""
    words: dict[int,str]
    positions: dict[int,tuple[float,float] | None]
    allowed: set[str]
    indexed: dict[tuple,list[Event]]
    backing: dict[tuple,list[Event]]
    details: dict[int,tuple]
    continuations: dict[int,OverrideContinuation]


@dataclass(frozen=True)
class BackedPulseRow:
    """A complete backing row with foreground peers and common held-pose evidence."""
    key: tuple
    layer: str
    start: float
    end: float
    y: float
    backing: list[tuple]
    glyphs: list[tuple]
    common: set[tuple]


def _eligible_backed_glyph_state(e: Event, word: str, pos: tuple[float,float] | None) -> OverrideEvaluation | None:
    """Require one stationary finite glyph with supported unclipped geometry."""
    if (e.kind != 'Dialogue' or len(word) != 1 or word.isspace() or
            unicodedata.combining(word) or pos is None or e.duration <= 0 or
            not e.layer.lstrip('-').isdigit() or inline_layout_key(e)):
        return None
    evaluated = event_evaluation(e)
    state = evaluated.formatting
    if (not all(math.isfinite(v) for v in pos) or
            any(not math.isfinite(state.get(k,0)) or state.get(k,0) <= 0
                for k in ('fs','fscx','fscy')) or
            state.get('p',0) or state.get('borderstyle',1) != 1 or
            any(k in state for k in ('clip','iclip','org')) or
            any(abs(state.get(k,0)) > .001 for k in ('frz','frx','fry','fax','fay')) or
            any(abs(state.get(k,state.get('shad',0))) > .001 for k in ('xshad','yshad'))):
        return None
    return evaluated


def _parse_backed_glyph_effects(e: Event, state: dict, allowed: set[str], *,
                                continuation: OverrideContinuation) -> tuple[list[tuple],tuple] | None:
    """Validate allowed transform destinations and finite nonnegative fade timings."""
    tokens = event_override_tokens(e)
    if any(tag in {'move','fade','k','kf','ko'} for tag,value in tokens):
        return None
    transforms = []
    safe = True
    final = state.copy()
    final_continuation = continuation
    for tag,value in tokens:
        if tag == 't':
            transform = parse_effect_transform(value,e.duration,allowed)
            if transform is None:
                safe = False; break
            begin,end,changes = transform
            for name,argument in changes:
                final_continuation = apply_override(final,name,argument,e.styles,e.defaults,final_continuation)
            transforms.append((begin,end,final.copy()))
    if not safe:
        return None
    fades = [value for tag,value in tokens if tag == 'fad']
    try:
        fade = tuple(float(v) for v in fades[0].strip('()').split(',')) if fades else (0,0)
    except ValueError:
        return None
    if (len(fades) > 1 or len(fade) != 2 or
            not all(math.isfinite(v) and v >= 0 for v in fade)):
        return None
    return transforms,fade


def _prepare_backed_glyph_pulses(events: list[Event], words: dict[int,str], positions: dict[int,tuple[float,float] | None]) -> BackedPulseContext:
    """Index eligible original glyph states and translucent backing candidates once."""
    allowed = {'c','1c','3c','4c','alpha','1a','3a','4a','blur','be','fscx','fscy'}
    indexed, backing = {}, {}
    details,continuations = {}, {}
    for e in events:
        word,pos = words.get(e.source_index,''),positions.get(e.source_index)
        evaluated = _eligible_backed_glyph_state(e,word,pos)
        if evaluated is None:
            continue
        state = evaluated.formatting
        effects = _parse_backed_glyph_effects(e,state,allowed,continuation=evaluated.continuation)
        if effects is None:
            continue
        transforms,fade = effects
        sample = dataclass_replace(e,state=state,continuation=evaluated.continuation)
        layout = tuple((k,v) for k,v in text_layout_key(sample) if k not in {'fscx','fscy'})
        key = (e.style,e.name,e.margin_l,e.margin_r,e.margin_v,layout)
        details[e.source_index] = (state,transforms,fade)
        continuations[e.source_index] = evaluated.continuation
        indexed.setdefault(key,[]).append(e)
        if (0 < state.get('1a',0) < 255 and
                all(final.get('1c') == state.get('1c') and 0 < final.get('1a',0) < 255
                    for _,_,final in transforms)):
            backing.setdefault((key,e.layer,pos,word,state.get('1c')),[]).append(e)
    return BackedPulseContext(words,positions,allowed,indexed,backing,details,continuations)


def _group_backed_glyph_rows(context: BackedPulseContext) -> dict[tuple,list[tuple]]:
    """Group touching translucent phases by exact anchor and their complete cue interval."""
    rows = {}
    for (key,layer,pos,word,colour),phases in context.backing.items():
        phases.sort(key=lambda e:(e.start_s,e.end_s,e.source_index))
        runs = []
        for e in phases:
            if not runs or abs(runs[-1][-1].end_s-e.start_s) > .011:
                runs.append([])
            runs[-1].append(e)
        for run in runs:
            if run[-1].end_s-run[0].start_s > .25:
                rows.setdefault((key,layer,run[0].start_s,run[-1].end_s,pos[1]),[]).append(
                    (pos,word,run))
    return rows


def _backed_glyph_pose(state: dict) -> tuple:
    """Name the shared foreground paint, outline and size used by the pulse proof."""
    return tuple(state.get(k,DEFAULT_STATE.get(k)) for k in
                 ('1c','3c','bord','xbord','ybord','fscx','fscy'))


def _backed_frames_converge(context: BackedPulseContext, frames: list[Event], base: dict, *, clipped: bool = False) -> bool:
    """Require monotonic return to held paint/size, with stronger proof for clipped tails."""
    distances = []
    for frame in frames:
        state = context.details[frame.source_index][0]
        if any(state.get(k,DEFAULT_STATE.get(k)) != base.get(k,DEFAULT_STATE.get(k))
               for k in ('3c','bord','xbord','ybord')):
            return False
        distances.append((sum(abs(int(state['1c'][i:i+2],16)-
                                  int(base['1c'][i:i+2],16)) for i in (0,2,4)),
                          abs(state.get('fscx',100)-base.get('fscx',100)),
                          abs(state.get('fscy',100)-base.get('fscy',100))))
    if any(any(b > a+.02 for a,b in zip(left,right))
           for left,right in zip(distances,distances[1:])):
        return False
    # A pulse cut short by the recorded cue boundary still needs a
    # substantial return toward a pose held elsewhere in this glyph's cue.
    return (not clipped or len(frames) >= 2 and any(distances[0]) and
            all(b <= .5*a+.02 for a,b in zip(distances[0],distances[-1])))


def _collect_backed_row_holds(context: BackedPulseContext, row_key: tuple, row: list[tuple]) -> BackedPulseRow | None:
    """Collect aligned foreground peers and held poses shared by every backed glyph."""
    key,layer,start,end,y = row_key
    glyphs,common = [], None
    for pos,word,run in row:
        height = text_height(dataclass_replace(run[0],state=context.details[run[0].source_index][0],
            continuation=context.continuations[run[0].source_index]))
        peers = [e for e in context.indexed[key] if context.words[e.source_index] == word and
                 int(e.layer) > int(layer) and e.start_s >= start-.001 and
                 e.end_s <= end+.001 and math.dist(context.positions[e.source_index],pos) <= .12*height]
        holds = {}
        for e in peers:
            state,transforms,fade = context.details[e.source_index]
            if (not transforms and fade == (0,0) and state.get('1a',0) == 0 and
                    e.duration >= .02 and math.dist(context.positions[e.source_index],pos) <= e.unit):
                holds.setdefault(_backed_glyph_pose(state),[]).append(e)
        common = set(holds) if common is None else common & set(holds)
        glyphs.append((pos,word,run,peers,holds,height))
    if not common:
        return None
    return BackedPulseRow(key,layer,start,end,y,row,glyphs,common)


def _backed_row_has_conflicts(context: BackedPulseContext, cue: BackedPulseRow) -> bool:
    """Reject peers with ambiguous glyph ownership and competing persistent neighbors."""
    if any(sum(context.words[e.source_index] == word and
               math.dist(context.positions[e.source_index],pos) <= .12*height
               for pos,word,run,peers,holds,height in cue.glyphs) != 1
           for *_,peers,holds,height in cue.glyphs for e in peers):
        return True
    height = min(glyph[-1] for glyph in cue.glyphs)
    if any(e.start_s < cue.end and e.end_s > cue.start and
           min(e.end_s,cue.end)-max(e.start_s,cue.start) > .02 and
           cue.backing[0][0][0]-height <= context.positions[e.source_index][0] <= cue.backing[-1][0][0]+height and
           abs(context.positions[e.source_index][1]-cue.y) <= .12*height and
           int(e.layer) >= int(cue.layer) and
           not any(context.words[e.source_index] == word and
                   math.dist(context.positions[e.source_index],pos) <= .12*height
                   for pos,word,run in cue.backing)
           for e in context.indexed[cue.key]):
        return True
    return False


def _select_backed_row_pose(cue: BackedPulseRow) -> tuple | None:
    """Choose the duration-dominant common held pose and reject similarly sustained alternatives."""
    ranked = sorted(cue.common,key=lambda p:-sum(sum(e.duration for e in holds[p])
                                             for *_,holds,height in cue.glyphs))
    target = ranked[0]
    # Two similarly sustained common paints do not identify a base pose.
    scores = [sum(sum(e.duration for e in holds[p]) for *_,holds,height in cue.glyphs)
              for p in ranked[:2]]
    if len(scores) > 1 and scores[0] < 2*scores[1]:
        return None
    return target


def _backed_sizes_are_positive(context: BackedPulseContext, run: list[Event], peers: list[Event]) -> bool:
    """Require finite positive size at every original and transformed phase."""
    # The common opaque hold and return trajectory prove the base
    # size. Large excursions are still pulses; flipped or degenerate
    # sizes cannot establish the same readable pose.
    if any(not math.isfinite(sample.get(k,100)) or sample.get(k,100) <= 0
           for e in run+peers
           for sample in [context.details[e.source_index][0]]+
                         [final for _,_,final in context.details[e.source_index][1]]
           for k in ('fscx','fscy')):
        return False
    return True


def _backed_foreground_coverage(peers: list[Event], start: float, end: float) -> list[Event] | None:
    """Prove one top foreground event covers every boundary interval, retaining identity."""
    boundaries = sorted({start,end}|{t for e in peers for t in (e.start_s,e.end_s)})
    foreground = []
    for a,b in zip(boundaries,boundaries[1:]):
        covering = [e for e in peers if e.start_s <= a+.001 and e.end_s >= b-.001]
        if not covering:
            return None
        top = max(int(e.layer) for e in covering)
        top_events = [e for e in covering if int(e.layer) == top]
        if len(top_events) != 1:
            return None
        e = top_events[0]
        if not foreground or foreground[-1] is not e:
            foreground.append(e)
    return foreground


def _backed_transform_returns(context: BackedPulseContext, e: Event, base: dict, target: tuple, *,
                              continuation: OverrideContinuation) -> bool:
    """Validate every transform component returns to the same opaque held destination."""
    valid = True
    # Separate colour and size transforms may share a pulse,
    # but none may introduce another destination or a cycle.
    for tag,value in event_override_tokens(e):
        if tag != 't':
            continue
        changes = parse_effect_transform(value,e.duration,context.allowed)[2]
        for name,argument in changes:
            sample = base.copy()
            apply_override(sample,name,argument,e.styles,e.defaults,continuation)
            if _backed_glyph_pose(sample) != target or sample.get('1a',0) != 0:
                valid = False; break
    return valid


def _prove_backed_foreground_pulses(context: BackedPulseContext, foreground: list[Event], base: dict, target: tuple, end: float, *,
                                    continuation: OverrideContinuation) -> list[float] | None:
    """Prove opaque transform and frame pulses return to the held pose across the cue."""
    valid = True
    pending = []
    pulse_times = []
    for e in foreground:
        state,transforms,fade = context.details[e.source_index]
        if state.get('1a',0) != 0:
            valid = False; break
        if _backed_glyph_pose(state) == target:
            if pending:
                # A frame pulse must approach the held paint and size
                # monotonically, then return to an exact authored hold.
                if not _backed_frames_converge(context,pending,base):
                    valid = False; break
                pending = []
            if not transforms:
                continue
        if transforms:
            if (e.end_s == end and fade[0] == 0 and fade[1] > 0 and
                    state.get('1c') == base.get('1c') and
                    all(final.get('1c') == base.get('1c') for _,_,final in transforms)):
                continue
            final = transforms[-1][2]
            if _backed_glyph_pose(final) != target or final.get('1a',0) != 0:
                valid = False; break
            if not _backed_transform_returns(context,e,base,target,continuation=continuation):
                valid = False; break
            if _backed_glyph_pose(state) != target:
                pulse_times.append(e.start_s)
        else:
            if e.duration > .1 or fade != (0,0):
                valid = False; break
            pending.append(e)
            if _backed_glyph_pose(state) != target:
                pulse_times.append(e.start_s)
    if pending and pending[-1].end_s == end and _backed_frames_converge(context,pending,base,clipped=True):
        pending = []
    if not valid or pending:
        return None
    return pulse_times


def _extend_backed_pulse_tails(context: BackedPulseContext, cue: BackedPulseRow, members: set[int], kept: list[Event]) -> list[Event]:
    """Extend only a complete backing/foreground exit fading to one shared boundary."""
    # A simultaneous final colour flash/fade is an exit, not another
    # lyric. Extend only when the complete backing and foreground
    # both fade at every recorded anchor to one shared boundary.
    tails = []
    for pos,word,run,peers,holds,height in cue.glyphs:
        fading = [e for e in context.indexed[cue.key] if context.words[e.source_index] == word and
                  e.start_s == cue.end and int(e.layer) >= int(cue.layer) and
                  math.dist(context.positions[e.source_index],pos) <= e.unit and
                  context.details[e.source_index][2][0] == 0 and
                  context.details[e.source_index][2][1] > 0 and
                  context.details[e.source_index][1] and
                  context.details[e.source_index][1][-1][2].get('1a',0) >= 254]
        if (not fading or not any(e.layer == cue.layer for e in fading) or
                not any(int(e.layer) > int(cue.layer) for e in fading)):
            tails = []; break
        tails.extend(fading)
    if tails and len({e.end for e in tails}) == 1:
        members.update(e.source_index for e in tails)
        finish = tails[0].end_s
        kept = [replace_event(e,end=tails[0].end,end_s=finish) for e in kept]
    return kept


def _proved_backed_row_paint(context: BackedPulseContext, cue: BackedPulseRow,
                            target: tuple, metric: FontMetrics | None) -> SourceCaptionPaint | None:
    """Use an owned, common settled backing without weakening pulse/coverage proofs."""
    if metric is None:
        return None
    samples,palettes = [],set()
    for pos,word,run,peers,holds,height in cue.glyphs:
        # The existing run proof supplies cue coverage. Reject overlapping
        # backing phases rather than compositing copies with ambiguous ownership.
        if any(a.end_s > b.start_s+.011 for a,b in zip(run,run[1:])):
            return None
        foreground = max(holds[target],key=lambda e:e.duration)
        base = context.details[foreground.source_index][0]
        settled = [e for e in run if not context.details[e.source_index][1] and
                   context.details[e.source_index][2] == (0,0) and e.duration >= .02 and
                   all(context.details[e.source_index][0].get(k,100) == base.get(k,100)
                       for k in ('fscx','fscy'))]
        if not settled:
            return None
        # Compare backing paint at the held size, excluding transient pulse frames.
        # A changing resting backing is not one representative static paint.
        palettes.update(tuple(context.details[e.source_index][0].get(k,DEFAULT_STATE.get(k))
                              for k in ('1c','1a','blur','fscx','fscy')) for e in settled)
        if len(palettes) != 1:
            return None
        backing = max(settled,key=lambda e:e.duration)
        def resolved(e):
            return dataclass_replace(e,state=context.details[e.source_index][0],
                                     continuation=context.continuations[e.source_index])
        backing,foreground = resolved(backing),resolved(foreground)
        if backing.state.get('blur',0) <= foreground.state.get('blur',0):
            return None
        sample = _settled_caption_paint_samples(foreground,[backing,foreground],metric)
        if sample is None:
            return None
        samples.append(sample)
    return _pool_source_caption_paint(samples)


def _propose_backed_pulse_row(context: BackedPulseContext, cue: BackedPulseRow, target: tuple, metric: FontMetrics | None = None) -> tuple[set[int],list[Event]] | None:
    """Build a complete held glyph row only after coverage and ordered pulse activation prove it."""
    changed,activation,kept,members = 0,[],[],set()
    for pos,word,run,peers,holds,height in cue.glyphs:
        chosen = max(holds[target],key=lambda e:e.duration)
        base = context.details[chosen.source_index][0]
        if not _backed_sizes_are_positive(context,run,peers):
            return None
        foreground = _backed_foreground_coverage(peers,cue.start,cue.end)
        if foreground is None:
            return None
        pulse_times = _prove_backed_foreground_pulses(context,foreground,base,target,cue.end,
                                                     continuation=context.continuations[chosen.source_index])
        if pulse_times is None:
            return None
        if pulse_times:
            changed += 1;activation.append(min(pulse_times))
        members.update(e.source_index for e in run+peers)
        kept.append(replace_event(chosen,start=format_time(cue.start),end=format_time(cue.end),
                    start_s=cue.start,end_s=cue.end,text=render_simplified_caption(base,word,
                    pos=pos,an=int(base.get('an',5)),measurement=chosen.measurement),layer='0'))
    kept = _extend_backed_pulse_tails(context,cue,members,kept)
    if (changed >= 3 and
            (all(a <= b for a,b in zip(activation,activation[1:])) or
             all(a >= b for a,b in zip(activation,activation[1:])))):
        paint = _proved_backed_row_paint(context,cue,target,metric)
        if paint is not None:
            # The first render only standardizes layout. Its fallback paint is
            # replaced here after the whole row has supplied source evidence.
            kept = [replace_event(e,text=render_simplified_caption(
                e.state,word,source_paint=paint,pos=pos,measurement=e.measurement))
                for e,(pos,word,*_) in zip(kept,cue.glyphs)]
        return members,kept
    return None


def _apply_backed_pulse_proposals(events: list[Event], proposals: list[tuple[set[int],list[Event]]]) -> tuple[list[Event],int]:
    """Reject every competing proposal before applying replacements at original event slots."""
    owners = {}
    for members,kept in proposals:
        for index in members:
            owners[index] = owners.get(index,0)+1
    removed,replacements = set(),{}
    for members,kept in proposals:
        if any(owners[index] != 1 for index in members):
            continue
        removed.update(members)
        replacements.update((e.source_index,e) for e in kept)
    if not removed:
        return events,0
    output = [replacements.get(e.source_index,e) for e in events
              if e.source_index not in removed or e.source_index in replacements]
    return output,len(events)-len(output)


def collapse_backed_glyph_pulses(events: list[Event], words: dict[int,str],
                                  positions: dict[int,tuple[float,float] | None],
                                  font_metrics: FontMetrics | None = None) -> tuple[list[Event],int]:
    """Freeze complete glyph rows proven by a continuous stationary backing.

    A translucent copy supplies exact anchors and cue bounds. Every glyph
    needs an opaque held foreground pose and uninterrupted foreground coverage.
    Colour and size pulses must return to that shared pose; frame jitter must
    converge to it. Pulse magnitude is unrestricted, but sizes must remain
    finite, positive and unflipped. Partial rows, gradients, ambiguous copies
    and moving labels stay.
    Text spacing remains the responsibility of the existing row reconstruction.
    """
    context = _prepare_backed_glyph_pulses(events,words,positions)
    rows = _group_backed_glyph_rows(context)
    proposals = []
    for row_key,row in rows.items():
        row.sort(key=lambda item:item[0][0])
        if len(row) < 4 or len({pos[0] for pos,word,run in row}) != len(row):
            continue
        cue = _collect_backed_row_holds(context,row_key,row)
        if cue is None or _backed_row_has_conflicts(context,cue):
            continue
        target = _select_backed_row_pose(cue)
        if target is None:
            continue
        proposal = _propose_backed_pulse_row(context,cue,target,font_metrics)
        if proposal is not None:
            proposals.append(proposal)
    return _apply_backed_pulse_proposals(events,proposals)
