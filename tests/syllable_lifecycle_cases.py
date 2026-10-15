"""Independent source construction for whole-syllable replacement checks."""
from pathlib import Path
import simplify_ass as s
ROOT=Path(__file__).resolve().parents[1]
FONT_DIR=ROOT/'test-data/Solo-Leveling-S01E02-fonts'
SOURCE=ROOT/'test-data/Solo-Leveling-S01E02-source.ass'
HEADER='''[Script Info]
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, Outline, Shadow, Alignment, ScaleX, ScaleY, MarginL, MarginR, MarginV
Style: Default,Century Gothic,50,&H00FFFFFF,&H00000000,0,0,5,100,100,0,0,0
Style: Other,Century Gothic,50,&H00FFFFFF,&H00000000,0,0,5,100,100,0,0,0
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
LITERAL='Some calm lyrics'
def metric():
    owner=s.FontMetrics([FONT_DIR])
    face=owner.matching_face('Century Gothic',0,False)
    assert face is not None and Path(face.path).name=='GOTHIC.TTF','Restore the supplied Century Gothic font'
    return owner
def parse(text):
    return s._resolve_document_state(s.parse_subtitle_document(text)).events
def record(layer,a,b,body,effect='fx',style='Default'):
    return f'Dialogue: {layer},{s.format_time(a)},{s.format_time(b)},{style},,0,0,0,{effect},{body}\n'
def fixture(*,edges=True,effect='fx',x=960,y=120,start=1,paint='D8DFE1',scale=130,split_tags=False):
    owner=metric();defaults=s.parse_styles(HEADER.splitlines())['Default']
    model=s.authored_glyph_positions(owner,defaults,LITERAL,x,.01);assert model
    parts=['Some','calm','ly','rics'];cursor=0;result=[];end=start+3
    for i,part in enumerate(parts):
        subset=model[cursor:cursor+len(part)];cursor+=len(part)
        begin=start if edges and i==0 else start+.4+i*.4
        duration=end-begin+.1 if edges and i==len(parts)-1 else .5
        finish=round(begin+duration,6);return_at=round(finish-.1,6)
        relative=s.authored_glyph_positions(owner,defaults,part,0,.01);assert relative
        anchor=subset[0][1]-relative[0][1]
        for layer in (0,1):
            for char,gx in subset:
                layout=fr'\an5\pos({gx:.12g},{y})\bord{1 if layer==0 else 0}\shad0'
                if begin>start:
                    before='FFFFFF' if layer==0 else 'D0CFCA'
                    result.append(record(layer,start,begin,'{'+layout+fr'\c&H{before}&\3c&H001122&\fad(100,0)'+'}'+char,effect))
                if return_at<end:
                    after='FFFFFF' if layer==0 else paint
                    result.append(record(layer,return_at,end,'{'+layout+fr'\c&H{after}&\3c&H001122&\fad(0,100)'+'}'+char,effect))
        timing=round(duration*1000)
        body=fr'\pos({anchor:.12g},{y})\an5\fscx{scale}\fscy{scale}\alpha&H10&\c&HFFFFFF&\3c&H88DDCC&\bord5\shad0\blur5'
        body+=fr'\t(0,50,)\t(100,{timing},\fscx100\fscy100)\t({timing-100},{timing},\alpha&ff&)'
        body=('{'+body+'}') if not split_tags else ''.join('{'+part+'}' for part in (body[:body.index('\\t')],body[body.index('\\t'):]))
        result.append(record(3,begin,finish,body+part,effect))
    return HEADER+''.join(result)
