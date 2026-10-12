"""Exact-font ASS fixtures shared by lyric-layer checks and diagnostics."""
import simplify_ass as s

FONT = 'Volkhov'
OTHER_FONT = 'FOT-MatisseMinori Pro-En B'
TEXT = 'The sky shines'
HEADER = r'''[Script Info]
ScriptType: v4.00+
PlayResX: 640
PlayResY: 360
WrapStyle: 2
ScaledBorderAndShadow: yes
Kerning: no
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Lyric,Volkhov,40,&H00FFFFFF,&H00FFFFFF,&H00403020,&H00000000,0,0,0,0,100,100,0,0,1,2,0,7,0,0,0,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''

def event(text, x, layer, interval, tags=''):
    return (f'Dialogue: {layer},{s.format_time(interval[0])},{s.format_time(interval[1])},'
            f'Lyric,,0,0,0,,{{\\pos({x:.6f},100){tags}}}{text}\n')


def make_case(name, metrics, destination, *, pieces='letters', offset=1, ordinary=False,
              full_time=(1, 4), fragment_time=(1.05, 3.95), shift=0,
              size=40, font=FONT, fragment_text=TEXT, oracle='redundant copies'):
    # Two paint layers at each of two nearby anchors model a slight shadow/
    # jitter stack. No lyric/row flags are assigned by the test.
    source = HEADER
    if ordinary:
        source += event(TEXT, 100, 0, full_time)
    else:
        for x in (100, 100 + offset):
            source += event(TEXT, x, 0, full_time, r'\1a&HFF&\bord3\3c&H403020&')
            source += event(TEXT, x, 1, full_time)
    tags = f'\\fs{size}'
    if font != FONT:
        tags += f'\\fn{font}\\b1'
    doc = s._resolve_document_state(s.parse_subtitle_document(HEADER + event(fragment_text, 100 + shift, 2, fragment_time, tags)))
    model = next(iter(doc.events.values()))
    glyphs = s.authored_glyph_positions(metrics, model.state, fragment_text, 100 + shift, model.unit)
    assert glyphs is not None, name
    if pieces == 'letters':
        fragments = glyphs
    elif pieces == 'words':
        fragments = []
        cursor = 0
        for word in fragment_text.split():
            fragments.append((word, glyphs[cursor][1]))
            cursor += len(word)
    else:
        # An actual word split into syllables, with spaces authored between words.
        tokens = ['The', 'sky', 'shi', 'nes']
        fragments, cursor = [], 0
        for token in tokens:
            fragments.append((token, glyphs[cursor][1]));cursor += len(token)
    for literal, x in fragments:
        source += event(literal, x, 2, fragment_time, tags)
        source += event(literal, x, 3, fragment_time, tags + r'\bord3')
    path = destination / (name + '.source.ass');path.write_text(source)
    return dict(name=name, source=path, oracle=oracle, fragments=len(fragments),
                settings=dict(pieces=pieces, offset=offset, ordinary=ordinary,
                              full_time=full_time, fragment_time=fragment_time,
                              shift=shift, size=size, font=font, fragment_text=fragment_text))
