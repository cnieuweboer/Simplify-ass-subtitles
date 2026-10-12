import test_paths  # Resolve the repository for direct test execution.
from event_evidence_test_helpers import event_comparison_fields
#!/usr/bin/env python3
"""Differential checks for complete-row proof and foreground paint recovery."""
from pathlib import Path
from copy import deepcopy
import ast, contextlib, importlib.util, io, json, random, sys, tempfile, trace
import simplify_ass as current
from font_geometry_test_helpers import font_test_report, measurement_fonts, row_test_call, adapt_reference_font_api, install_row_test_doubles
install_row_test_doubles(current, historical_fade_timing=True)

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('full_line_reference', ROOT/'test-data/simplify_ass-v152-reference.py')
previous = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = previous
spec.loader.exec_module(previous)
adapt_reference_font_api(previous)
HEADER = '''[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
ScaledBorderAndShadow: yes
[V4+ Styles]
Format: Name, Fontname, Fontsize, Alignment, Outline, Shadow
Style: Sign,Arial,40,5,0,0
Style: Other,Arial,40,5,0,0
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
FULL = r'\an5\pos(300,150)\bord0\1a&HFE&\3a&HFE&\4a&HFE&\xshad-.01\yshad.01'
GLYPH = r'\an5\bord2\1c&HCFC9F5&\3c&H3F29CA&\1a&H00&\3a&H00&'

def snapshot(value):
    if type(value).__name__ == "Event":return snapshot(event_comparison_fields(value))
    if isinstance(value, dict): return tuple((k,snapshot(v)) for k,v in value.items())
    if isinstance(value, (list,tuple)): return tuple(snapshot(v) for v in value)
    if isinstance(value, set): return frozenset(snapshot(v) for v in value)
    if isinstance(value, (current.FontMetrics,previous.FontSpacing)): return 'font-metric'
    if hasattr(value, '__dict__'): return snapshot(vars(value))
    return value

def row(literal='Colorful row', full=FULL, pieces=None, copies=1):
    result = [dict(text='{'+full+'}'+literal,layer='0')]
    pieces = list(literal.replace(' ','')) if pieces is None else pieces
    step = 160/max(1,len(pieces)-1)
    for i,piece in enumerate(pieces):
        for copy in range(copies):
            result.append(dict(text='{'+GLYPH+fr'\pos({220+step*i:g},150)'+'}'+piece,layer=str(4+copy)))
    return result

def change(data, predicate=lambda i,d: i>0, **updates):
    result = deepcopy(data)
    for i,d in enumerate(result):
        if predicate(i,d): d.update({k:v(i,d) if callable(v) else v for k,v in updates.items()})
    return result

def tags(data, extra, predicate=lambda i,d:i>0):
    return change(data,predicate,text=lambda i,d:d['text'].replace('}',extra+'}',1))

BASE = row()
SHADOW = row(full=FULL.replace(r'\4a&HFE&',r'\4a&H00&'),pieces=['Col','orf','ul','row'])
CASES = []
def case(name,data=BASE,**options): CASES.append(dict(name=name,data=data,**options))
case('opaque foreground replaces transparent scaffold',removed=11,fill='CFC9F5')
case('solid full line retains its authored paint',row(full=r'\an5\pos(300,150)\bord2\1c&HFFFFFF&\3c&H000000&'),removed=11,fill='FFFFFF')
case('shadow-only full line proves four fragments',SHADOW,removed=4,fill='CFC9F5')
case('ordinary four fragments lack minimum copies',row(pieces=['Col','orf','ul','row']),removed=0)
case('eight copies can prove four columns',row(pieces=['Col','orf','ul','row'],copies=2),removed=8)
case('seven fragments below ordinary threshold',row('Abc defg'),removed=0)
case('eight fragments at ordinary threshold',row('Abcd efgh'),removed=8)
case('fewer than four spatial columns',row(pieces=['Colo','rful','row'],copies=3),removed=0)
case('missing final glyph',BASE[:-1],removed=0)
case('wrong literal glyph',change(BASE,lambda i,d:i==1,text=lambda i,d:d['text'][:-1]+'Z'),removed=0)
case('different text in same column',BASE+[dict(text=BASE[1]['text'][:-1]+'Z',layer='6')],removed=0)
case('highest layer supplies foreground',BASE+tags(BASE[1:],r'\1c&H123456&',lambda i,d:True),removed=22)
case('negative and nonnumeric layers',change(BASE,layer=lambda i,d:'-2' if i%2 else 'invalid'))
case('full anchor outside row',change(BASE,lambda i,d:i==0,text=lambda i,d:current.POS_RE.sub(lambda m:r'\pos(500,150)',d['text'])),removed=0)
case('fragment beyond vertical tolerance',change(BASE,lambda i,d:i==1,text=lambda i,d:current.POS_RE.sub(lambda m:r'\pos(220,155)',d['text'])),removed=0)
case('font mismatch falls back to full paint',tags(BASE,r'\fs41',lambda i,d:i==1),removed=11,fill='FFFFFF')
case('unknown fragment font',tags(BASE,r'\fnMissingFont',lambda i,d:i==1))
case('transparent fragment does not supply paint',tags(BASE,r'\1a&H01&',lambda i,d:i==1),removed=11,fill='FFFFFF')
case('rotated full scaffold falls back',tags(BASE,r'\frz10',lambda i,d:i==0),removed=11,fill='FFFFFF')
case('clipped full scaffold falls back',tags(BASE,r'\clip(0,0,600,300)',lambda i,d:i==0),removed=11,fill='FFFFFF')
case('origin full scaffold falls back',tags(BASE,r'\org(300,150)',lambda i,d:i==0),removed=11,fill='FFFFFF')
case('fragment clip falls back',tags(BASE,r'\clip(0,0,600,300)',lambda i,d:i==1),removed=11,fill='FFFFFF')
case('fragment inline layout falls back',change(BASE,lambda i,d:i==1,text=lambda i,d:d['text']+r'{\fsp2}'),removed=11,fill='FFFFFF')
case('authored wrapping retained',tags(BASE,r'\q2',lambda i,d:i==0),removed=11)
case('casefold proof cannot borrow different literal paint',change(BASE,lambda i,d:i>0,text=lambda i,d:d['text'][:-1]+d['text'][-1].swapcase()),removed=11,fill='FFFFFF')
case('shadow proof requires exact case',change(SHADOW,lambda i,d:i==1,text=lambda i,d:d['text'][:-3]+'col'),removed=0)
case('shadow fragment opacity required',tags(SHADOW,r'\1a&H01&',lambda i,d:i==1),removed=0)
case('shadow fragment geometry required',tags(SHADOW,r'\fs41',lambda i,d:i==1),removed=0)
case('shadow border style prevents special proof',tags(SHADOW,r'\bord0\shad0\xshad0\yshad0',lambda i,d:i==0),removed=0)
case('long fragment geometry proof',row(pieces=['Color','f','ul','row'],copies=2),removed=8)
case('long fragment wrong font rejected',tags(row(pieces=['Color','f','ul','row'],copies=2),r'\fs41',lambda i,d:i in (1,2)),removed=0)
case('long fragment clip rejected',tags(row(pieces=['Color','f','ul','row'],copies=2),r'\clip(0,0,600,300)',lambda i,d:i in (1,2)),removed=0)
case('different style does not join group',change(BASE,lambda i,d:i==1,style='Other'),removed=0)
case('different speaker does not join group',change(BASE,lambda i,d:i==1,name='Other'),removed=0)
case('different margin does not join group',change(BASE,lambda i,d:i==1,margin_l='1'),removed=0)
case('different raw timing does not join group',change(BASE,lambda i,d:i==1,start='0:00:01.000'),removed=0)
case('different end does not join group',change(BASE,lambda i,d:i==1,end='0:00:03.99'),removed=0)
case('different logical row does not join group',change(BASE,lambda i,d:i==1,row=1),removed=0)
case('unpositioned fragment retained',change(BASE,lambda i,d:i==1,text=lambda i,d:current.POS_RE.sub('',d['text'])),removed=0)
case('full line without a word separator retained',row('Colorfulrow'),removed=0)
case('tracking spans preserve authored payload',change(BASE,lambda i,d:i==0,text=lambda i,d:'{'+FULL+'}'+r'Colorful r{\fsp-10}o{\fsp0}w'),removed=11,payload=r'Colorful r{\fsp-10}o{\fsp0}w')
case('tracking with font mismatch falls back',tags(CASES[-1]['data'],r'\fs41',lambda i,d:i==1),removed=11,fill='FFFFFF')
case('inline nontracking scaffold',change(BASE,lambda i,d:i==0,text=lambda i,d:d['text'].replace('row',r'r{\fs41}ow')))
case('tracking with nonuniform foreground',tags(CASES[-3]['data'],r'\1c&H123456&',lambda i,d:i==1))
case('preowned fragment cannot prove row',preowned='fragment',removed=1)
case('preowned full line skipped',preowned='full',removed=1)
case('external matcher ownership count retained',preowned='external',removed=12)
case('failed merged renderer does not consume fragments',render_failure=True,removed=0)
case('two competing full lines preserve input ownership',BASE+[deepcopy(BASE[0])])
case('independent second interval',BASE+change(BASE,lambda i,d:True,start='0:00:05.00',end='0:00:07.00'))
case('proved foreground retains matching wrapping',tags(BASE,r'\q2',lambda i,d:True),removed=11,fill='CFC9F5')

def inputs(module,c,order):
    lines=[]
    for d in c['data']:
        fields=[d.get(k,v) for k,v in [('layer','0'),('start','0:00:01.00'),('end','0:00:04.00'),('style','Sign'),('name',''),('margin_l','0'),('margin_r','0'),('margin_v','0'),('effect',''),('text','')]]
        lines.append('Dialogue: '+','.join(fields)+'\n')
    document=module._resolve_document_state(module.parse_subtitle_document(HEADER+''.join(lines)))
    events=list(document.events.values())
    for e,d in zip(events,c['data']):
        e.row=d.get('row',0)
        # Direct callers can supply equivalent times with different raw spellings.
        if 'start' in d:e.start=d['start']
        if 'end' in d:e.end=d['end']
    if order=='reverse':events.reverse()
    if order=='shuffle':random.Random(135).shuffle(events)
    return events

NAMES=('match_nested_glyph_copies','match_staggered_full_line_copies','match_authored_lyric_rows','render_merged_caption','render_simplified_caption')
@contextlib.contextmanager
def recording(module,c,events,calls,isolate):
    originals={name:getattr(module,name) for name in NAMES}
    full=next(e.source_index for e in events if module.OVERRIDE_RE.sub('',e.text).startswith('Colorful row')) if c.get('preowned') else None
    fragment=min(e.source_index for e in events if e.source_index!=full) if full is not None else None
    owned={'full':full,'fragment':fragment,'external':999999}.get(c.get('preowned'))
    def wrap(name,original):
        def run(*args,**kwargs):
            calls.append((name,snapshot((args,kwargs))))
            if name=='render_merged_caption' and c.get('render_failure'):return None
            if name=='match_nested_glyph_copies' and owned is not None:return {owned}
            if isolate and name.startswith('match_'):return (set(),[]) if name=='match_authored_lyric_rows' else set()
            return original(*args,**kwargs)
        return run
    for name,original in originals.items():setattr(module,name,wrap(name,original))
    try:yield
    finally:
        for name,original in originals.items():setattr(module,name,original)

metrics={module:module.FontMetrics([ROOT/'fonts']) for module in (previous,current)}
tracer=trace.Trace(count=True,trace=False,ignoredirs=[sys.base_prefix])
checks=[]
for c in CASES:
    for order in ('original','reverse','shuffle'):
        for isolate,options in ((True,'none'),(False,'none'),(False,'rows'),(False,'source-and-rows')):
            compared=[]
            for module in (previous,current):
                events=inputs(module,c,order); before=snapshot(events)
                visible={e.source_index:module.OVERRIDE_RE.sub('',e.text) for e in events}
                sources=deepcopy({e.source_index:e for e in events}) if options=='source-and-rows' else None
                evidence=[] if options!='none' else None
                calls=[]
                with recording(module,c,events,calls,isolate):
                    args=(events,visible,sources,evidence)
                    kwargs=dict(font_metrics=metrics[module])
                    result=tracer.runfunc(module.remove_letters_over_full_lines,*args,**kwargs) if module is current and order=='original' and options=='none' and isolate else module.remove_letters_over_full_lines(*args,**kwargs)
                assert snapshot(events)==before,(c['name'],'input mutation')
                identities=[any(e is original for original in events) for e in result[0]]
                compared.append((snapshot(result),snapshot(evidence),snapshot(sources),calls,identities))
                if isolate and order=='original' and module is previous:
                    if 'removed' in c:assert result[1]==c['removed'],(c['name'],result[1],c['removed'])
                    if 'fill' in c:assert result[0][0].state['1c']==c['fill'],(c['name'],result[0][0].state)
                    if 'payload' in c:assert result[0][0].text.endswith(c['payload'])
            assert compared[0]==compared[1],(c['name'],order,options,isolate)
            checks.append(dict(case=c['name'],order=order,options=options,isolated_matchers=isolate,identical=True))

fixtures=[('Full-line-scaffold-source.ass',BASE),('Full-line-shadow-source.ass',SHADOW),('Full-line-tracking-source.ass',CASES[40]['data'])]
for name,data in fixtures:
    events=inputs(current,dict(data=data),'original')
    (ROOT/'test-data'/name).write_text(HEADER+''.join('Dialogue: '+','.join(e.fields())+'\n' for e in events))
focused=[]
for fixture in [name for name,_ in fixtures]+['Overlord-22m06-source.ass','Overlord-opening-fades-source.ass']:
    compared=[]
    for module in (previous,current):
        calls=[];original=module.remove_letters_over_full_lines
        def wrapped(*args,**kwargs):
            before=snapshot((args,kwargs));result=original(*args,**kwargs)
            calls.append((before,snapshot(result),snapshot((args,kwargs))));return result
        module.remove_letters_over_full_lines=wrapped
        try:
            with tempfile.TemporaryDirectory() as temp:
                output=Path(temp)/'output.ass';metric=module.FontMetrics([ROOT/'fonts'])
                with contextlib.redirect_stdout(io.StringIO()) as log:
                    stats=module.simplify_ass(ROOT/'test-data'/fixture,output,module.SimplifyConfig(),font_metrics=metric, font_report=font_test_report(metric))
                compared.append((output.read_bytes(),stats,log.getvalue(),calls,font_test_report(metric).rows_joined,set(font_test_report(metric).missing_families)))
        finally:module.remove_letters_over_full_lines=original
    assert compared[0]==compared[1],(fixture,'complete conversion')
    focused.append(dict(fixture=fixture,statistics=compared[0][1],target_calls=len(compared[0][3]),identical=True))

tree=ast.parse((ROOT/'simplify_ass.py').read_text());coverage={}
hit={line for (filename,line),count in tracer.results().counts.items() if count and Path(filename).resolve()==(ROOT/'simplify_ass.py').resolve()}
for name in ('_prove_full_line_fragment_copies','_render_proven_full_line_caption'):
    fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
    statements={n.lineno for n in ast.walk(fn) if isinstance(n,ast.stmt) and n is not fn}
    statements.discard(fn.body[0].lineno)
    coverage[name]=dict(statement_lines=sorted(statements),executed_statement_lines=sorted(statements&hit),uncovered_statement_lines=sorted(statements-hit))
    assert statements<=hit,(name,statements-hit)
report=dict(version=current.__version__,reference=previous.__version__,scenarios=len(CASES),direct_comparisons=len(checks),focused_conversions=focused,helper_statement_coverage=coverage,comparisons=checks)
(ROOT/'validation/full-line-copy-checks.json').write_text(json.dumps(report,indent=2)+'\n')
print(len(checks),'direct comparisons across',len(CASES),'scenarios;',len(focused),'focused complete conversions')
print('Both extracted helpers covered; events, ownership, row evidence and paint match v148')
