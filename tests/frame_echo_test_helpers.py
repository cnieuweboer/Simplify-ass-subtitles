"""Current-policy frame-echo fixtures; no historical production substitutes."""
from dataclasses import replace

from _simplify_ass import subtitle_document as document
from _simplify_ass.caption_geometry import get_pos
from _simplify_ass.event_operations import replace_event

HEADER = '''[Script Info]
PlayResX: 1920
PlayResY: 1080
[V4+ Styles]
Format: Name, Fontname, Fontsize, Bold, Alignment, ScaleX, ScaleY, Spacing, Outline, Shadow
Style: Default,Arial,40,0,5,100,100,0,1,0
[Events]
'''


def echo_events(flat=False, frames=1, duration=.05, offsets=3):
    """An opaque hold followed by translated, evenly spaced exit copies."""
    lines = []
    for frame in range(frames + 1):
        start, end = (1., 2.) if not frame else (2. + (frame-1)*duration, 2. + frame*duration)
        points = [500.] if not frame else [500. + 20*frame + 2*(i-(offsets-1)/2) for i in range(offsets)]
        for x in points:
            for layer in ([5] if flat else [0, 1]):
                paint = r'\1c&HFFFFFF&\bord1' if flat or layer else r'\1c&H000000&\bord3'
                if frame:
                    paint += r'\1a&H80&'
                tags = rf'\pos({x:g},100)\an5\fs40\shad0' + paint
                lines.append(f'Dialogue: {layer},{document.format_time(start)},{document.format_time(end)},Default,,0,0,0,,{{{tags}}}Hello\n')
    parsed = document._resolve_document_state(document.parse_subtitle_document(HEADER + ''.join(lines)))
    events = list(parsed.events.values())
    for event in events:
        event.row = 8 if event.start_s == 1. else 3
        event.lyric = event.start_s == 1.
    return events


def add_tags(event, tags):
    end = event.text.index('}')
    return replace_event(event, text=event.text[:end] + tags + event.text[end:])


def moving_sources(events, endpoint=400):
    """Original move events correspond to each already-positioned working copy."""
    sources = {}
    for event in events:
        if event.start_s < 2.:
            continue
        x, y = get_pos(event.text)
        tags = rf'\move({x-30:g},{y:g},{x+30:g},{y:g},0,{endpoint:g})'
        raw = HEADER + f'Dialogue: {event.layer},{event.start},{event.end},Default,,0,0,0,,{{{tags}}}Hello\n'
        parsed = document._resolve_document_state(document.parse_subtitle_document(raw))
        original = next(iter(parsed.events.values()))
        sources[event.source_index] = replace(original, source_index=event.source_index)
    return sources
