"""Live source contours through reconstruction, timing and final phase handoffs."""
import test_paths
from copy import deepcopy
from pathlib import Path
import hashlib, json
import simplify_ass as s
from event_evidence_test_helpers import contour_independent_contract, event_comparison_fields

ROOT = Path(__file__).resolve().parents[1]
metrics = s.FontMetrics([ROOT/'fonts'])
assert metrics.matching_face('Volkhov',0,False), 'Missing exact Volkhov regular'
HEADER = '''[Script Info]
PlayResX: 640
PlayResY: 360
WrapStyle: 2
[V4+ Styles]
Format: Name, Fontname, Fontsize, Alignment, Outline, Shadow
Style: Default,Volkhov,40,5,0,0
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
checks = []
def check(label, condition):
    assert condition, label
    checks.append(label)
def record(word, x=320, start=1, end=4, tags='', kind='Dialogue'):
    return f'{kind}: 0,{s.format_time(start)},{s.format_time(end)},Default,,0,0,0,,{{\\pos({x:.8f},100){tags}}}{word}\n'
def parse(records):
    events = list(s._resolve_document_state(s.parse_subtitle_document(HEADER+''.join(records))).events.values())
    for e in events:
        e.lyric = e.kind == 'Dialogue'; e.row = 1
    return events
def visible(events):
    return {e.source_index:s.simplify_text(e.text,visible_only=True)[1] for e in events}
def snapshot(events):
    return deepcopy([event_comparison_fields(e) for e in events])
def paint(label, events, width, alpha, color):
    dialogues = [e for e in events if e.kind=='Dialogue']
    check(label+' visible captions present',bool(dialogues))
    for e in dialogues:
        obj = s.static_object_key(e,e.styles,allow_unpositioned=True)
        check(label+' static caption',obj is not None)
        for sig,drawing,literal in obj[-1]:
            state = dict(sig.formatting)
            check(label+' retained literal fill',not drawing and state['1c']=='FFFFFF')
            check(label+' retained authored contour',
                  state['3c']==color and state['3a']==alpha and
                  tuple(state.get(k,state['bord']) for k in ('xbord','ybord'))==(width,width))

for label,tags,width,alpha,color in [
    ('soft opaque',r'\1c&HFFFFFF&\3c&HDDDDDD&\bord.75',.75,0,'DDDDDD'),
    ('soft translucent',r'\1c&HFFFFFF&\3c&HDDDDDD&\3a&H60&\bord1.25',1.25,96,'DDDDDD'),
    ('intentional borderless',r'\1c&HFFFFFF&\bord0',0,0,'000000'),
]:
    # Complete-copy selection must hand off its own source contour, independently
    # of the old renderer's neutral contrast decision.
    events = parse([record('ABCD',tags=tags),record('AB CD',start=1.1,end=4.1,tags=tags)])
    before = snapshot(events); history = visible(events); saved = history.copy()
    result = s.collapse_full_lyric_copies(events,history)
    check(label+' complete copy reduced',result.removed_count==1 and len(result.events)==1)
    paint(label+' complete copy',result.events,width,alpha,color)
    check(label+' complete copy borrows source',snapshot(events)==before and history==saved)

    # Use actual exact-font glyph anchors, not a mock renderer or row service.
    seed = parse([record('ABCD',tags=tags)])[0]
    positions = s.authored_glyph_positions(metrics,seed.state,'ABCD',320,seed.unit)
    check(label+' exact glyph model available',positions is not None)
    events = parse([record(c,x,tags=tags) for c,x in positions]+[record('ABCD',kind='Comment')])
    glyphs = events[:4]
    pieces = [(e,c,s.get_pos(e.text)) for e,(c,x) in zip(glyphs,positions)]
    row = s.TextRow(glyphs[0],pieces,[glyphs],{},list(glyphs),True,False,(1.2,3.8))
    before = snapshot(events); history = visible(events); saved = history.copy()
    result = s.reconstruct_text_rows(events,history,{},metrics,set(history),
        source_events={e.source_index:e for e in events},source_rows=[row],font_report=s.FontProcessingReport())
    check(label+' row reconstructed',result.merged_count==3 and sum(e.kind=='Dialogue' for e in result.events)==1 and
          s.OVERRIDE_RE.sub('',result.events[0].text)=='ABCD')
    paint(label+' reconstructed row',result.events,width,alpha,color)
    check(label+' row borrows source',snapshot(events)==before and history==saved)

    # A confirmed authored row uses source-only paint normalization, without
    # assembling or retiming its fragment evidence.
    source_only = s.reconstruct_text_rows(events,history,{},metrics,set(history),
        source_rows=[row],source_only=True)
    paint(label+' source-only row',source_only.events,width,alpha,color)
    check(label+' source-only timing and core retained',
          [(e.start_s,e.end_s) for e in source_only.events]==[(1,4)]*5 and
          source_only.rows[0].phase_core==(1.2,3.8))
    check(label+' source-only evidence borrowed',snapshot(events)==before and row.pieces is pieces)

    # Entrance/held glyph phases use the same authored exact-font row evidence.
    entrances = [record(c,x,start=.9,end=1.1,tags=tags).replace(',100)',',104)')
                 for c,x in positions]
    held = [record(c,x,start=1.1,end=4,tags=tags) for c,x in positions]
    phased = parse(entrances+held+[record('ABCD',kind='Comment')])
    before_phases = snapshot(phased); phase_history = visible(phased); saved_phases = phase_history.copy()
    translated = s.collapse_translated_phase_rows(phased,phase_history,metrics,
        font_report=s.FontProcessingReport())
    check(label+' entrance/held phases reconstructed',translated.removed_count==7 and
          len(translated.rows)==1 and (translated.rows[0].base.start_s,translated.rows[0].base.end_s)==(.9,4))
    paint(label+' translated phases',translated.events,width,alpha,color)
    check(label+' translated phase evidence borrowed',snapshot(phased)==before_phases and
          phase_history==saved_phases)

    frames = parse([record('ABCD',start=1+i*.04,end=1+(i+1)*.04,
        tags=tags+rf'\fscx{100+i}\blur{i%3}') for i in range(12)])
    before_frames = snapshot(frames); frame_history = visible(frames)
    frozen,count = s.flatten_text_effect_sequences(frames,frame_history,frames[0].styles,
        set(frame_history),True,source_events={e.source_index:e for e in frames})
    check(label+' effect sequence reduced',count==11 and len(frozen)==1)
    paint(label+' frozen effect sequence',frozen,width,alpha,color)
    check(label+' effect sequence evidence borrowed',snapshot(frames)==before_frames and
          frame_history==visible(frames))

    # Feed a reconstructed caption into the real overlap and final join owners.
    caption = result.events[0]
    successor = s.replace_event(caption,start=s.format_time(3.8),start_s=3.8,
        end=s.format_time(7),end_s=7,source_index=100,text=caption.text.replace('ABCD','EFGH'))
    rows = [s.TextRow(caption,[(caption,'ABCD',s.get_pos(caption.text))],phase_core=(1.2,3.6)),
            s.TextRow(successor,[(successor,'EFGH',s.get_pos(successor.text))],phase_core=(4.2,6.8))]
    out,trimmed = s.trim_faded_cue_overlaps([caption,successor],rows,{})
    check(label+' readable handoff trimmed',trimmed==1 and out[0].end_s==out[1].start_s==3.9)
    paint(label+' overlap handoff',out,width,alpha,color)
    check(label+' handoff preserves exact paint and geometry',
          all(a.text==b.text and a.fields()[3:]==b.fields()[3:] for a,b in zip([caption,successor],out)))
    phases = [s.replace_event(out[0],end=s.format_time(2.5),end_s=2.5),
              s.replace_event(out[0],start=s.format_time(2.5),start_s=2.5)]
    joined,count = s.merge_static_timed_copies(phases,caption.styles,font_metrics=metrics,text_only=True)
    check(label+' final matching phases joined',count==1 and len(joined)==1 and
          joined[0].start_s==1 and joined[0].end_s==3.9)
    paint(label+' final phase',joined,width,alpha,color)
    check(label+' final join repeat stable',
          s.merge_static_timed_copies(joined,caption.styles,font_metrics=metrics,text_only=True)==(joined,0))
    other = s.replace_event(phases[1],text=phases[1].text.replace('}',r'\bord1.5\3a&H40&}',1))
    check(label+' intentional contour phases remain separate',
          s.merge_static_timed_copies([phases[0],other],caption.styles,font_metrics=metrics,text_only=True)[1]==0)

# Verify the historical projection is narrowly bounded. It may exclude contour
# paint, but must detect changes to content, fill, timing, geometry and evidence.
seed = event_comparison_fields(parse([record('ABCD',tags=r'\3c&HDDDDDD&\bord.75')])[0])
changed = deepcopy(seed); changed['state']['3c']='888888'; changed['text']=changed['text'].replace('DDDDDD','888888')
check('historical projection excludes deliberate contour change',
      contour_independent_contract(seed)==contour_independent_contract(changed))
for field,value in [('text',seed['text']+'E'),('start_s',1.1),('layer','2'),('source_index',999)]:
    changed = deepcopy(seed); changed[field]=value
    check('historical projection retains '+field,
          contour_independent_contract(seed)!=contour_independent_contract(changed))
for field,value in [('1c','123456'),('pos',(321,100)),('fn','Other Font'),('1a',80)]:
    changed = deepcopy(seed); changed['state'][field]=value
    check('historical projection retains '+field,
          contour_independent_contract(seed)!=contour_independent_contract(changed))

(ROOT/'validation/current-paint-handoff-checks.json').write_text(json.dumps(dict(
    version=s.__version__,checks_passed=len(checks),checks=checks,
    runtime_sha256=hashlib.sha256((ROOT/'simplify_ass.py').read_bytes()).hexdigest()),indent=2)+'\n')
print(len(checks),'current paint handoff checks passed; actual renderer and exact font geometry')
