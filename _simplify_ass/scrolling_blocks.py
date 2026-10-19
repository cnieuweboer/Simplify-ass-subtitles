"""Coherent residual scrolling-block proofs and optional concurrency removal.

Borrow caller events and measurements; keep tracking and diagnostic buffers local.
The engine retains pipeline placement, configuration and aggregate reporting.
"""
from __future__ import annotations

import math
import re
from bisect import bisect_right
from dataclasses import dataclass, replace as dataclass_replace
from .ass_overrides import OVERRIDE_RE, tokenize_override
from .caption_geometry import caption_bounds, get_pos, text_height
from .event_model import Event
from .event_operations import state_key
from .font_metrics import FontMetrics
from .subtitle_document import peak_concurrent_events

@dataclass(frozen=True)
class ScrollingBlockMatch:
    """Participating profile indices and the unchanged common motion-proof interval."""
    indices: list[int]
    start: float
    end: float


def collect_scrolling_tracks(events, resx, resy):
    """Track baked text frames; never join overlapping spatial instances.

    Paint-only inline spans and coincident effect copies may describe the same
    line. Font/layout spans, live animation, drawings and non-frame cues cannot.
    Ambiguous nearest-neighbour assignments start new tracks instead of guessing.
    """
    paint = {'alpha', 'c', 'bord', 'xbord', 'ybord', 'shad', 'xshad', 'yshad',
             'blur', 'be'} | {f'{c}{kind}' for c in range(1, 5) for kind in 'ca'}
    pose = {'pos', 'org', 'fscx', 'fscy', 'frz', 'frx', 'fry', 'fax', 'fay'}
    groups = {}
    for e in events:
        if (e.kind != 'Dialogue' or not 0 < e.duration <= .16+1e-6 or
                e.state.get('p', 0) or e.effect.strip() or
                re.search(r'\\(?:move|t|fad|fade|[kK])(?=[(\d])', e.text)):
            continue
        pos = get_pos(e.text)
        literal = OVERRIDE_RE.sub('', e.text)
        if pos is None or not literal.strip() or any(x in literal for x in (r'\N', r'\n')):
            continue
        seen_text = False
        safe = True
        for part in re.split(r'(\{[^}]*\})', e.text):
            if part.startswith('{'):
                if seen_text and any(k not in paint for k, v in tokenize_override(part[1:-1])):
                    safe = False
            elif part:
                seen_text = True
        values = (*pos, *e.state.get('org', pos), *(e.state.get(k, 0) for k in
                  ('fscx', 'fscy', 'frz', 'frx', 'fry', 'fax', 'fay')))
        if not safe or not all(math.isfinite(v) for v in values):
            continue
        key = (e.style, e.name, e.layer, literal, e.margin_l, e.margin_r, e.margin_v,
               state_key(e, paint | pose),
               tuple(k for k in ('xbord', 'ybord', 'xshad', 'yshad') if k in e.state))
        # Equal interval/pose copies are one spatial line, not extra votes.
        frame_key = (e.start_s, e.end_s, tuple(e.state.get(k) for k in sorted(pose)), pos)
        groups.setdefault(key, {}).setdefault(frame_key, []).append(e)
    tracks = []
    max_step = .08*min(resx, resy)
    for frames in groups.values():
        buckets = {}
        for copies in frames.values():
            e = copies[0]
            buckets.setdefault(e.start_s, []).append(copies)
        family = []
        for start, nodes in sorted(buckets.items()):
            active = [t for t in family if abs(t[-1][0].end_s-start) <= .011+1e-6]
            distances = {(i, j): math.dist(get_pos(t[-1][0].text), get_pos(n[0].text))
                         for i, t in enumerate(active) for j, n in enumerate(nodes)}
            def nearest(options):
                ranked = sorted(options)
                if not ranked or ranked[0][0] > max_step:
                    return None
                if len(ranked) > 1 and ranked[1][0]-ranked[0][0] <= max(2*nodes[0][0].unit, .2*ranked[0][0]):
                    return None
                return ranked[0][1]
            forward = {i: nearest([(distances[i, j], j) for j in range(len(nodes))])
                       for i in range(len(active))}
            reverse = {j: nearest([(distances[i, j], i) for i in range(len(active))])
                       for j in range(len(nodes))}
            for j, node in enumerate(nodes):
                i = reverse[j]
                if i is not None and forward[i] == j:
                    active[i].append(node)
                else:
                    family.append([node])
        tracks.extend(family)
    return tracks


def scroll_track_crosses_canvas(track, axis, sign, resx, resy, metric):
    """Strong edge evidence from measured text, with a wide uncertainty margin.

    This is a bounded near-front-facing estimate, not a projective glyph box.
    Steep perspective, distant origins, unknown fonts and clips cannot prove an
    edge crossing. Anchors outside the viewport alone are never sufficient.
    """
    extent = (resx, resy)[axis]
    def box(node):
        e = node[0]
        st = e.state
        pos = get_pos(e.text)
        origin = st.get('org', pos)
        angles = [abs(math.remainder(st.get(k, 0), 360)) for k in ('frx', 'fry')]
        if (max(angles) > 5 or math.dist(pos, origin) > .25*min(resx, resy) or
                'clip' in st or 'iclip' in st):
            return None
        prefix = re.match(r'(?:\{[^}]*\})*', e.text).group()
        flat = dataclass_replace(e, text=prefix+OVERRIDE_RE.sub('', e.text),
                                 state={**st, 'frx': 0, 'fry': 0},continuation=e.continuation)
        bounds = caption_bounds(flat, metric)
        if bounds is None:
            return None
        radius = math.dist(pos, origin)+math.hypot(bounds[2]-bounds[0], bounds[3]-bounds[1])
        margin = .10*extent + radius*sum(abs(math.sin(math.radians(a))) for a in angles)
        return bounds[axis]-margin, bounds[axis+2]+margin
    first, last = box(track[0]), box(track[-1])
    if first is None or last is None:
        return False
    # One endpoint's whole expanded box must be inside the scrolling axis;
    # the other must be wholly beyond the corresponding edge.
    if sign > 0:
        return (0 < first[0] and first[1] < extent and last[0] > extent or
                first[1] < 0 and 0 < last[0] and last[1] < extent)
    return (0 < first[0] and first[1] < extent and last[1] < 0 or
            first[0] > extent and 0 < last[0] and last[1] < extent)


def _scrolling_pose_is_translational(track: list, extent: float,
                                     resx: float, resy: float) -> bool:
    """Require stable near-front-facing scale/rotation and an origin that cannot cancel anchor travel."""
    # Large rotations/scale swings are not a translational scrolling line.
    states = [node[0].state for node in track]
    if any(abs(math.remainder(st.get(k, 0), 360)) > 5
           for st in states for k in ('frx', 'fry')):
        return False
    offsets = [tuple(st.get('org', pos)[k]-pos[k] for k in range(2))
               for st, pos in zip(states, [get_pos(node[0].text) for node in track])]
    if any(st.get(k, 0) for st in states for k in ('frz', 'frx', 'fry')) and (
            max(math.hypot(*d) for d in offsets) > .25*min(resx, resy) or
            any(max(d[k] for d in offsets)-min(d[k] for d in offsets) > .05*extent
                for k in range(2))):
        # A changing rotation origin can cancel the movement of pos.
        # Such anchors cannot establish a translating text track.
        return False
    if any(min(st.get(k, 100) for st in states) <= 0 or
           max(st.get(k, 100) for st in states) > 1.3*min(st.get(k, 100) for st in states)
           for k in ('fscx', 'fscy')):
        return False
    if any(max(abs(math.remainder(st.get(k, 0)-states[0].get(k, 0), 360)) for st in states) > 2
           for k in ('frz', 'frx', 'fry')):
        return False
    return True


def _profile_scrolling_track(track: list, resx: float, resy: float) -> dict | None:
    """Prove sustained directional travel, allowing the original bounded entrance prefix."""
    if len(track) < 8 or track[-1][0].end_s-track[0][0].start_s < 1:
        return None
    points = [get_pos(node[0].text) for node in track]
    delta = tuple(points[-1][k]-points[0][k] for k in range(2))
    axis = max(range(2), key=lambda k: abs(delta[k])/(resx, resy)[k])
    extent = (resx, resy)[axis]
    if abs(delta[axis]) < .5*extent:
        return None
    sign = 1 if delta[axis] > 0 else -1
    # A brief zoom/entrance may precede the sustained scroll. Ignore at
    # most the first 20% (and never more than one second) for its motion
    # proof, but keep the whole continuous track as the removal unit.
    cutoff = track[0][0].start_s+min(1, .2*(track[-1][0].end_s-track[0][0].start_s))
    initial = [i for i, node in enumerate(track) if node[0].start_s <= cutoff]
    first = min(initial, key=lambda i: sign*points[i][axis])
    proof = track[first:]
    points = points[first:]
    delta = tuple(points[-1][k]-points[0][k] for k in range(2))
    if proof[-1][0].end_s-proof[0][0].start_s < 1 or abs(delta[axis]) < .5*extent:
        return None
    steps = [(b[0]-a[0], b[1]-a[1]) for a, b in zip(points, points[1:])]
    distance = math.hypot(*delta)
    total = sum(math.hypot(*d) for d in steps)
    if (distance < .92*total or
            sum(max(0, -sign*d[axis]) for d in steps) > .05*abs(delta[axis]) or
            abs(delta[1-axis]) > .25*abs(delta[axis])):
        return None
    if not _scrolling_pose_is_translational(track,extent,resx,resy):
        return None
    return {'track': track, 'axis': axis, 'sign': sign,
            'start': proof[0][0].start_s, 'end': proof[-1][0].end_s,
            'delta': delta, 'points': points,
            'times': [node[0].start_s for node in proof]}


def _scrolling_profile_position(p: dict, at: float) -> tuple:
    """Interpolate the existing proof points, clamping to their sampled interval."""
    i = max(0, min(len(p['times'])-2, bisect_right(p['times'], at)-1))
    a, b = p['times'][i:i+2]
    fraction = max(0, min(1, (at-a)/(b-a)))
    return tuple(p['points'][i][k]*(1-fraction)+p['points'][i+1][k]*fraction for k in range(2))


def _scrolling_profiles_are_coherent(a: dict, b: dict, lo: float, hi: float,
                                      resx: float, resy: float) -> bool:
    """Compare five progress samples over one common interval using the original relative tolerance."""
    if (a['axis'], a['sign']) != (b['axis'], b['sign']):
        return False
    extent = (resx, resy)[a['axis']]
    samples = [lo+(hi-lo)*i/4 for i in range(5)]
    ap, bp = [_scrolling_profile_position(a, t) for t in samples], [_scrolling_profile_position(b, t) for t in samples]
    da, db = [p[-1][a['axis']]-p[0][a['axis']] for p in (ap, bp)]
    if min(a['sign']*da, a['sign']*db) < .05*extent:
        return False
    tolerance = max(.02*extent, .25*max(abs(da), abs(db)))
    if abs(da-db) > tolerance:
        return False
    # Compare progress throughout the shared interval, not just endpoints.
    return all(math.dist((x[0]-ap[0][0], x[1]-ap[0][1]),
                         (y[0]-bp[0][0], y[1]-bp[0][1])) <= tolerance
               for x, y in zip(ap, bp))


def _scrolling_profiles_are_distinct(a: dict, b: dict, at: float) -> bool:
    """Require spatial separation so shadows and paint copies cannot become extra votes."""
    pa, pb = _scrolling_profile_position(a, at), _scrolling_profile_position(b, at)
    ea, eb = a['track'][0][0], b['track'][0][0]
    # Effect shadows/paint copies of one word cannot vote as extra lines.
    return math.dist(pa, pb) > max(4*ea.unit, .75*max(text_height(ea), text_height(eb)))


def _match_scrolling_block(i: int, profiles: list[dict], resx: float, resy: float,
                           metric: FontMetrics | None) -> ScrollingBlockMatch | None:
    """Prove distinct voters and measured edge travel, then associate their near-coincident paint copies."""
    seed = profiles[i]
    # Require every pair to agree on one common interval; no transitive
    # chaining of unrelated neighbouring animations into a large block.
    group = [i]
    lo, hi = seed['start'], seed['end']
    for j, candidate in enumerate(profiles):
        if j == i:
            continue
        start, end = max(lo, candidate['start']), min(hi, candidate['end'])
        if end-start < 1:
            continue
        if all(_scrolling_profiles_are_coherent(profiles[k], candidate, start, end, resx, resy) and
               _scrolling_profiles_are_distinct(profiles[k], candidate, (start+end)/2) for k in group):
            group.append(j); lo, hi = start, end
    if len(group) < 3 or not any(scroll_track_crosses_canvas(profiles[k]['track'], seed['axis'],
                                                       seed['sign'], resx, resy, metric)
                                 for k in group):
        return None
    # Paint variants of a participating line are members but never extra
    # votes toward the three-line minimum. Match their literal identity
    # and near-coincident trajectory over this same proved interval.
    voters = list(group)
    for j, candidate in enumerate(profiles):
        if j in group or candidate['start'] > lo or candidate['end'] < hi:
            continue
        ce = candidate['track'][0][0]
        for k in voters:
            p = profiles[k]; pe = p['track'][0][0]
            if ((ce.style, ce.name, ce.layer, OVERRIDE_RE.sub('', ce.text),
                 ce.state.get('fn'), ce.state.get('fs'), ce.state.get('an')) !=
                (pe.style, pe.name, pe.layer, OVERRIDE_RE.sub('', pe.text),
                 pe.state.get('fn'), pe.state.get('fs'), pe.state.get('an'))):
                continue
            if _scrolling_profiles_are_coherent(p, candidate, lo, hi, resx, resy) and all(
                    math.dist(_scrolling_profile_position(p, at), _scrolling_profile_position(candidate, at)) <=
                    .25*max(text_height(pe), text_height(ce))
                    for at in (lo, (lo+hi)/2, hi)):
                group.append(j); break
    return ScrollingBlockMatch(group,lo,hi)


def drop_overloaded_scrolling_blocks(events, resx, resy, metric, *, concurrency_limit=32):
    """Last-resort removal of proved scrolling blocks after ordinary reduction.

    At least three spatially distinct tracks must share >=1s of coherent
    movement. Each travels >=50% of the relevant screen dimension. At least
    one line has strong measured edge evidence. Removal also requires the
    block's own remaining concurrency to exceed the explicit policy limit.
    Total event count and unrelated captions cannot trigger this fallback.
    """
    if concurrency_limit < 0:
        raise ValueError('Scrolling concurrency limit must be nonnegative.')
    profiles = []
    for track in collect_scrolling_tracks(events,resx,resy):
        profile = _profile_scrolling_track(track,resx,resy)
        if profile is not None:
            profiles.append(profile)

    removed,report,confirmed = set(),[],set()
    for i,seed in enumerate(profiles):
        if i in confirmed:
            continue
        block = _match_scrolling_block(i,profiles,resx,resy,metric)
        if block is None:
            continue
        confirmed.update(block.indices)

        members, block_events = [], []
        for k in block.indices:
            p = profiles[k]
            ids = {e.source_index for node in p['track'] for e in node}
            block_events.extend(e for node in p['track'] for e in node)
            members.append({'text': OVERRIDE_RE.sub('', p['track'][0][0].text),
                            'start': p['start'], 'end': p['end'], 'events': len(ids),
                            'travel': round(abs(p['delta'][p['axis']]), 2)})
        block_ids = {e.source_index for e in block_events}

        # Apply the policy to this block's unique remaining source events.
        peak = peak_concurrent_events({e.source_index: e for e in block_events}.values())
        drop = concurrency_limit > 0 and peak > concurrency_limit
        if drop:
            removed.update(block_ids)
        # Retained blocks are reported too; zero disables removal only.
        report.append({'start': block.start, 'end': block.end, 'axis': 'xy'[seed['axis']],
                       'direction': seed['sign'], 'tracks': members,
                       'peak_concurrent': peak, 'concurrency_limit': concurrency_limit,
                       'action': 'removed' if drop else 'retained'})
    return [e for e in events if e.source_index not in removed], report
