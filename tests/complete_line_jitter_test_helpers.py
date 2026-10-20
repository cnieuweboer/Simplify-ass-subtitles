"""Explicit complete-caption frames using current document and evidence owners."""
from dataclasses import replace

from _simplify_ass import subtitle_document as document
from _simplify_ass.event_model import EventEvidence
from _simplify_ass.frame_pose import _frame_pose_intervals

HEADER = '''[Script Info]
PlayResX: 1920
PlayResY: 1080
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, Outline, Shadow, Alignment
Style: Default,Arial,40,&H00FFFFFF,&H00000000,1,0,5
[Events]
'''


def jitter_text(*, layer=0, start=1., count=12, color='FFFFFF', literal='A complete line'):
    positions = (0., .7, -.4, .6, -.3, .8, -.5, .5, -.4, .6, -.2, .4)
    lines = []
    for i in range(count):
        x = 960 + positions[i % len(positions)]
        tags = rf'\pos({x:g},74)\1c&H{color}&\3c&H000000&\bord1\shad0'
        lines.append(f'Dialogue: {layer},{document.format_time(start+i*.04)},'
                     f'{document.format_time(start+(i+1)*.04)},Default,,0,0,0,,{{{tags}}}{literal}\n')
    return ''.join(lines)


def jitter_inputs(*, stacked=False, sentinel=False):
    text = jitter_text()
    if stacked:
        text += jitter_text(layer=1, start=1.04, count=10, color='335577')
    if sentinel:
        text += 'Dialogue: 0,0:00:05.00,0:00:06.00,Default,,0,0,0,,Unrelated caption\n'
    doc = document._resolve_document_state(document.parse_subtitle_document(HEADER + text))
    events = [replace(e, row=8, lyric=True,
                      evidence=EventEvidence(frame_pose_intervals=_frame_pose_intervals(e)))
              for e in doc.events.values()]
    visible = {e.source_index: 'Unrelated caption' if e.start_s == 5. else 'A complete line'
               for e in events}
    return events, visible, doc.styles
