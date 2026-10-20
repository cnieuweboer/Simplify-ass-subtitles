"""Authored fragment sweeps for source/installed karaoke-completion checks.

Only nominal layout keys are used: these proofs do not open or substitute fonts.
"""
from _simplify_ass.ass_overrides import OVERRIDE_RE
from _simplify_ass.event_operations import replace_event
from _simplify_ass.subtitle_document import (
    _resolve_document_state, format_time, parse_subtitle_document,
)

HEADER = '''[Script Info]
PlayResX: 640
PlayResY: 360
[V4+ Styles]
Format: Name, Fontname, Fontsize, Alignment, Outline, Shadow
Style: Default,Arial,40,5,0.75,0
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
BEFORE = '112233'
AFTER = '445566'
OUTLINE = '667788'


def karaoke_record(word, x, start, end, paint, *, y=80):
    return (f'Dialogue: 0,{format_time(start)},{format_time(end)},Default,,0,0,0,,'
            f'{{\\pos({x},{y}){paint}}}{word}\n')


def karaoke_inputs(*, sentinel=True, reverse=False, incomplete=False):
    sources = []
    retained = []
    for i, word in enumerate(('A', 'B', 'C')):
        x = 100 + i*80
        begin = 2 + i*.2
        before = rf'\1c&H{BEFORE}&\3c&H000000&\bord.75'
        after = rf'\1c&H{AFTER}&\3c&H{OUTLINE}&\bord1.5'
        sources.extend([
            karaoke_record(word, x, 1, begin, before),
            karaoke_record(word, x, begin, begin+.2,
                           before+rf'\t(0,200,{after})'),
            karaoke_record(word, x, begin+.2, 5, after),
        ])
        retained.append(karaoke_record(word, x, 1, 5, before))
    def parse(records):
        return list(_resolve_document_state(
            parse_subtitle_document(HEADER+''.join(records))).events.values())
    originals = parse(sources)
    events = [replace_event(e, source_index=originals[i*3].source_index,
                            lyric=True, row=7) for i,e in enumerate(parse(retained))]
    if sentinel:
        other = parse([karaoke_record('Unrelated', 320, 6, 7, r'\1c&HABCDEF&', y=280)])[0]
        events.insert(1, replace_event(other, source_index=99999))
    visible = {e.source_index:OVERRIDE_RE.sub('',e.text) for e in events}
    source_map = {e.source_index:e for e in originals}
    if incomplete:
        del source_map[originals[4].source_index]
    if reverse:
        events.reverse()
        source_map = dict(reversed(list(source_map.items())))
    return events, visible, source_map
