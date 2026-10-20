"""Independent rectangular glyph and authored mask for module-boundary checks."""
from dataclasses import replace

from _simplify_ass import subtitle_document as document

FAMILY = 'Masked Module Test'
HEADER = '''[Script Info]
PlayResX: 1920
PlayResY: 1080
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, Outline, Shadow, Alignment
Style: Default,Masked Module Test,40,&H00224466,&H00000000,0,0,5
[Events]
'''
# A 400x700 glyph, 600-unit advance, 1000/em, ascent 800/descent 200,
# at fs40/an5/pos(160,100). This mask is authored independently of the matcher.
MASK = 'm 148 112 l 164 112 164 84 148 84'


def make_font(path):
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(['.notdef', 'A', 'X'])
    builder.setupCharacterMap({65:'A', 88:'X'})
    glyphs = {}
    for name in ('.notdef', 'A', 'X'):
        pen = TTGlyphPen(None)
        pen.moveTo((0,0)); pen.lineTo((400,0)); pen.lineTo((400,700)); pen.lineTo((0,700)); pen.closePath()
        glyphs[name] = pen.glyph()
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({name:(600,0) for name in glyphs})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupNameTable(dict(familyName=FAMILY, styleName='Regular',
                               uniqueFontIdentifier='MaskedModuleTest', fullName=FAMILY,
                               psName='MaskedModuleTest'))
    builder.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
    builder.setupPost(); builder.setupMaxp(); builder.save(path)


def mask_inputs(*, identical=False, mask=MASK):
    literal = 'A' if identical else 'X'
    raw = HEADER + r'Dialogue: 0,0:00:01.00,0:00:05.00,Default,,0,0,0,,{\pos(160,100)\1a&H80&}A' + '\n'
    raw += f'Dialogue: 2,0:00:01.00,0:00:05.00,Default,,0,0,0,,{{\\pos(160,100)\\clip({mask})}}{literal}\n'
    raw += r'Dialogue: 0,0:00:06.00,0:00:07.00,Default,,0,0,0,,{\pos(160,100)}A' + '\n'
    doc = document._resolve_document_state(document.parse_subtitle_document(raw))
    events = [replace(e, row=8, lyric=True) for e in doc.events.values()]
    return events, {e.source_index:('A' if i != 1 else literal) for i,e in enumerate(events)}
