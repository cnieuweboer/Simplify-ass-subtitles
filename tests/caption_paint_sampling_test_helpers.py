"""Exact synthetic font and authored paint planes for sampling contracts."""
from _simplify_ass.event_operations import replace_event
from _simplify_ass.subtitle_document import _resolve_document_state, parse_subtitle_document

FAMILY = 'Paint Sampling Test'
HEADER = f'''[Script Info]
PlayResX: 640
PlayResY: 360
[V4+ Styles]
Format: Name,Fontname,Fontsize,Alignment,Outline,Shadow
Style: Default,{FAMILY},40,5,0,0
[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
'''


def make_font(path):
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    builder = FontBuilder(1000,isTTF=True)
    builder.setupGlyphOrder(['.notdef','A'])
    builder.setupCharacterMap({ord('A'):'A'})
    empty = TTGlyphPen(None)
    pen = TTGlyphPen(None)
    pen.moveTo((80,0)); pen.lineTo((580,0)); pen.lineTo((580,700)); pen.lineTo((80,700)); pen.closePath()
    builder.setupGlyf({'.notdef':empty.glyph(),'A':pen.glyph()})
    builder.setupHorizontalMetrics({'.notdef':(650,0),'A':(650,80)})
    builder.setupHorizontalHeader(ascent=800,descent=-200)
    builder.setupNameTable(dict(familyName=FAMILY,styleName='Regular',
                               uniqueFontIdentifier='PaintSamplingTest',
                               fullName=FAMILY,psName='PaintSamplingTest'))
    builder.setupOS2(sTypoAscender=800,sTypoDescender=-200,usWinAscent=800,usWinDescent=200)
    builder.setupPost(); builder.setupMaxp(); builder.save(path)


def paint_inputs(*, transformed=True, same_layer=False):
    foreground = (r'\1c&H334455&\1a&H10&\blur1\t(0,100,\1c&HABCDEF&\1a&H20&\blur.5)'
                  if transformed else r'\1c&HABCDEF&\1a&H20&\blur.5')
    raw = HEADER + r'Dialogue: 1,0:00:01.00,0:00:04.00,Default,,0,0,0,,{\pos(320,100)\1c&H102030&\1a&H60&\blur5}AAA'+'\n'
    raw += f'Dialogue: {1 if same_layer else 2},0:00:01.00,0:00:04.00,Default,,0,0,0,,{{\\pos(320,100){foreground}}}AAA\n'
    events = list(_resolve_document_state(parse_subtitle_document(raw)).events.values())
    return events[1],events
