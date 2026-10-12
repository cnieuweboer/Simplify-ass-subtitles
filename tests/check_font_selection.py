#!/usr/bin/env python3
"""Exercise actual overrides, collection faces and variable instance geometry."""
import test_paths  # Resolve the repository for direct test execution.
from pathlib import Path
from io import BytesIO
import hashlib
import json
import tempfile
import shutil

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.designspaceLib import DesignSpaceDocument, AxisDescriptor, SourceDescriptor, InstanceDescriptor
from fontTools.varLib import build
from fontTools.ttLib import TTFont, TTCollection
from PIL import ImageFont
import simplify_ass as s

ROOT = Path(__file__).resolve().parents[1]
checks = []

def ok(name, condition):
    assert condition, name
    checks.append(name)

def master(path, family, weight=400, italic=0, subfamily='Regular', axis='ital'):
    fb = FontBuilder(1000,isTTF=True)
    fb.setupGlyphOrder(['.notdef','space','A','i'])
    fb.setupCharacterMap({32:'space',65:'A',105:'i'})
    width = 500+weight-400
    shift = 150*italic if axis == 'ital' else -10*italic
    glyphs = {}
    for char in ['.notdef','space','A','i']:
        pen = TTGlyphPen(None)
        if char != 'space':
            pen.moveTo((0,0));pen.lineTo((width-100,0))
            pen.lineTo((width-100+shift,700));pen.lineTo((shift,700));pen.closePath()
        glyphs[char] = pen.glyph()
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics({g:(250 if g=='space' else width,0) for g in glyphs})
    fb.setupHorizontalHeader(ascent=800,descent=-200)
    fb.setupNameTable({'familyName':family,'styleName':subfamily,
        'uniqueFontIdentifier':family+' '+subfamily,'fullName':family+' '+subfamily,
        'psName':family.replace(' ','')+'-'+subfamily.replace(' ','')})
    fb.setupOS2(sTypoAscender=800,sTypoDescender=-200,usWinAscent=800,
        usWinDescent=200,usWeightClass=weight,
        fsSelection=(32 if weight>=600 else 64 if not italic else 0) | (1 if italic else 0))
    fb.setupPost();fb.setupMaxp();fb.save(path)

def variable(folder, family, axis='ital'):
    folder.mkdir()
    doc = DesignSpaceDocument()
    for tag,name,low,default,high in [('wght','Weight',400,400,700),
            (axis,'Italic' if axis=='ital' else 'Slant',0 if axis=='ital' else -15,0,1 if axis=='ital' else 0)]:
        a = AxisDescriptor();a.tag=tag;a.name=name
        a.minimum=low;a.default=default;a.maximum=high;doc.addAxis(a)
    for weight,italic,label in [(400,0,'Regular'),(700,0,'Bold'),
                               (400,1 if axis=='ital' else -15,'Italic'),
                               (700,1 if axis=='ital' else -15,'Bold Italic')]:
        path = folder/(label.replace(' ','-')+'.ttf')
        master(path,family,weight,italic,label,axis)
        source = SourceDescriptor();source.path=str(path)
        source.name=label;source.familyName=family;source.styleName=label
        source.location={'Weight':weight,'Italic' if axis=='ital' else 'Slant':italic}
        if label=='Regular':
            source.copyInfo=True;source.copyLib=True;source.copyFeatures=True
        doc.addSource(source)
        instance = InstanceDescriptor();instance.familyName=family;instance.styleName=label
        instance.postScriptFontName=family.replace(' ','')+'-'+label.replace(' ','')
        instance.location=source.location.copy();doc.addInstance(instance)
    designspace = folder/'test.designspace';doc.write(designspace)
    font,_,_ = build(designspace)
    output = folder.parent/(family.replace(' ','')+'.ttf')
    font.save(output);font.close()
    return output

header = '''[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
[V4+ Styles]
Format: Name, Fontname, Fontsize, Bold, Italic, Alignment, Outline, Shadow
Style: Default,Arial,40,0,0,5,0,0
Style: Sign,TwintailsQR,40,0,0,5,0,0
Style: Ending,00243,40,-1,0,5,0,0
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''

with tempfile.TemporaryDirectory() as directory:
    folder = Path(directory)
    vf = variable(folder/'masters','Variant Test')
    slanted = variable(folder/'slant-masters','Slant Test','slnt')
    shutil.rmtree(folder/'masters');shutil.rmtree(folder/'slant-masters')
    regular,bold = folder/'regular.ttf',folder/'bold.ttf'
    master(regular,'Collection Test');master(bold,'Collection Test',700,subfamily='Bold')
    collection = TTCollection();collection.fonts=[TTFont(regular),TTFont(bold)]
    collection.save(folder/'faces.ttc');collection.close()
    regular.unlink();bold.unlink()
    # Malformed candidates must not prevent selection of valid attached fonts.
    (folder/'broken.ttf').write_text('not a font')
    before = {p:hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir() if p.is_file()}
    metric = s.FontMetrics([folder,ROOT/'fonts'])
    supplied = metric.matching_face('00243',0,False)
    ok('supplied font matches its actual internal name',supplied is not None and Path(supplied.path).name=='00243.TTF')
    ok('regular-only supplied font remains bold measurement fallback',
        metric.matching_face('00243',-1,False)==supplied)
    ok('supplied font is static, not variable',not supplied.coordinates)
    faces = {(b,i):metric.matching_face('Variant Test',b,i) for b in (0,-1) for i in (0,1)}
    ok('all four variable variants selected',all(faces.values()))
    ok('weight and italic coordinates reflect ASS requests',all(
        dict(face.coordinates)=={'wght':700 if b else 400,'ital':i}
        for (b,i),face in faces.items()))
    ok('variant cache identities are distinct',len({face.key for face in faces.values()})==4)
    widths = {key:metric.measure(face,'AA') for key,face in faces.items()}
    ok('bold measurements differ from regular',widths[-1,0] > 1.5*widths[0,0])
    ok('italic retains its own measured advance',abs(widths[0,1]-widths[0,0]) < .02)
    for b,i in faces:
        face = faces[b,i]
        data,index = metric.face_data(face)
        ok(f'{b}/{i} memory instance is a single face',index==0)
        with metric.open_face(face) as font:
            ok(f'{b}/{i} outline uses selected instance','fvar' not in font)
            expected = font['hmtx'].metrics['A'][0]*2*1024/font['head'].unitsPerEm
            ok(f'{b}/{i} shaped width agrees with instance advances',abs(widths[b,i]-expected)<.04)
            ok(f'{b}/{i} ASS sizing uses same instance',metric.ass_em_scale(face)==
                font['head'].unitsPerEm/(font['OS/2'].usWinAscent+font['OS/2'].usWinDescent))
        ok(f'{b}/{i} glyph fragmentation remains measurable',metric.fragmented_glyph(face,'i') is False)
    outlines = {key:metric.cubic_outline(face,'A') for key,face in faces.items()}
    ok('all variable outlines measurable',all(outlines.values()))
    ok('italic outline differs from upright',outlines[0,1]!=outlines[0,0])
    ok('bold outline differs from regular',outlines[-1,0]!=outlines[0,0])
    numeric = metric.matching_face('Variant Test',550,False)
    ok('numeric bold weights retain 550',dict(numeric.coordinates)['wght']==550)
    ok('numeric weight interpolates measured width',widths[0,0] < metric.measure(numeric,'AA') < widths[-1,0])
    ok('boolean bold requests agree',metric.matching_face('Variant Test',1,False)==faces[-1,0])
    ok('regular face PostScript name still accepts bold request',
        metric.matching_face('VariantTest-Regular',-1,False)==faces[-1,0])
    ok('regular face full name still accepts italic request',
        metric.matching_face('Variant Test Regular',0,True)==faces[0,1])
    ok('case and whitespace normalized',metric.matching_face(' VARIANT TEST ',0,False)==faces[0,0])
    named = metric.matching_face('VariantTest-BoldItalic',0,True)
    ok('PostScript instance name preserves bold with b0',dict(named.coordinates)=={'wght':700,'ital':1})
    ok('full instance name recognized',metric.matching_face('Variant Test Bold Italic',0,True)==named)
    slant = metric.matching_face('Slant Test',0,True)
    ok('named italic slant preferred over guessed angle',dict(slant.coordinates)['slnt']==-15)
    ok('slant upright resets slant to zero',dict(metric.matching_face('Slant Test',0,False).coordinates)['slnt']==0)
    c0 = metric.matching_face('Collection Test',0,False)
    c1 = metric.matching_face('Collection Test',-1,False)
    ok('collection regular and bold faces both indexed',c0.index==0 and c1.index==1)
    ok('OS2 variant flags recognized without head flags',metric.measure(c1,'A')>metric.measure(c0,'A'))
    ok('missing exact family remains unknown',metric.matching_face('No Such Family',0,False) is None)
    ok('no fabricated static italic face',metric.matching_face('Collection Test',0,True) is None)
    ok('bold-only full name remains usable with b0',metric.matching_face('Collection Test Bold',0,False)==c1)
    # Variable collection instances must use the selected TTC member before serialization.
    vc = TTCollection();vc.fonts=[TTFont(vf),TTFont(slanted)]
    vc.save(folder/'variable-faces.ttc');vc.close()
    vf.unlink();slanted.unlink()
    collection_metric = s.FontMetrics([folder])
    vcface = collection_metric.matching_face('Slant Test',-1,True)
    ok('variable collection resolves second member',vcface.index==1)
    ok('variable collection measurements use member axes',collection_metric.measure(vcface,'A')>700)
    # All geometry consumers, including caption ink bounds, must key on the variant.
    source = folder/'input.ass'
    source.write_text(header+'\n'.join(
        f'Dialogue: 0,0:00:01.00,0:00:04.00,Sign,,0,0,0,,{{\\fnVariant Test\\b{b}\\i{i}\\pos(500,100)}}AA'
        for b,i in faces)+'\n',encoding='utf-8')
    events = s.load_subtitle_events(source)[1]
    boxes = [s.caption_bounds(event,metric) for event in events]
    ok('all variant caption bounds known',all(boxes))
    ok('bold backdrop bounds expand with glyph advance',boxes[2][2]-boxes[2][0]>boxes[0][2]-boxes[0][0])
    ok('font overrides replace unused style fonts',all(e.defaults['fn']=='TwintailsQR' and
        e.state['fn']=='Variant Test' for e in events))
    frozen = [s.replace_event(e,text=s.simplify_visual_text(e.text,0,e.duration,e.defaults,e.styles,1)[0]) for e in events]
    ok('freezing preserves overridden fonts',all(e.state['fn']=='Variant Test' for e in frozen))
    ok('font measurements do not own missing-font reporting',not hasattr(metric,'missing'))
    # Axis-less styles and positive-only slant ranges remain conservative.
    ok('wght-only font cannot provide italic',s.FontMetrics.variable_coordinates({'wght':(400,400,700)},0,True) is None)
    ok('ital plus slnt uses one italic mechanism',dict(s.FontMetrics.variable_coordinates(
        {'ital':(0,0,1),'slnt':(-20,0,0)},0,True))=={'ital':1,'slnt':0})
    ok('positive-only slant supported',dict(s.FontMetrics.variable_coordinates({'slnt':(0,0,20)},0,True))['slnt']==12)
    # Test the portable shaping backend independently of RAQM when installed.
    if metric.capabilities.harfbuzz:
        for key,face in faces.items():
            data,index = metric.face_data(face)
            metric._loaded[face.key]=ImageFont.truetype(BytesIO(data),1024,index=index,layout_engine=ImageFont.Layout.BASIC)
            ok(str(key)+' HarfBuzz agrees with RAQM',abs(metric.measure(face,'AA')-widths[key])<.04)
    # Apart from deliberately created test inputs/collections, measurements produce no files.
    after = {p:hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir() if p.is_file()}
    ok('font measurement writes no replacement fonts',set(after)-set(before)=={source,folder/'variable-faces.ttc'})
    ok('original surviving attachments remain unchanged',all(after[p]==digest for p,digest in before.items() if p in after))

report = {'version':s.__version__,'checks_passed':len(checks),'checks':checks}
(ROOT/'validation').mkdir(exist_ok=True)
(ROOT/'validation/font-selection-checks.json').write_text(json.dumps(report,indent=2)+'\n')
print(len(checks),'font selection checks passed')
