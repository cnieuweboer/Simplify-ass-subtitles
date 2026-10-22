#!/usr/bin/env python3
"""Verify borrowed visibility, sparse deltas, pending reads and failure isolation."""
import test_paths  # Resolve the repository for direct test execution.
import inspect
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import MappingProxyType
import json
import simplify_ass as s
from event_evidence_test_helpers import event_comparison_fields

ROOT=Path(__file__).resolve().parents[1]
checks=[]
def check(name,condition):
    assert condition,name
    checks.append(name)
HEADER='''[Script Info]
PlayResX: 1920
PlayResY: 1080
[V4+ Styles]
Format: Name, Fontname, Fontsize, Alignment, Outline, Shadow
Style: Default,Arial,40,5,2,0
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
def load(lines):
    doc=s._resolve_document_state(s.parse_subtitle_document(HEADER+''.join(lines)))
    events=list(doc.events.values())
    for e in events:e.lyric=True;e.row=0
    visible={e.source_index:s.simplify_text(e.text,visible_only=True)[1] for e in events}
    visible[999999]='historical removed source'
    return events,visible
def record(body,start,end,effect=''):
    return f'Dialogue: 0,{s.format_time(start)},{s.format_time(end)},Default,,0,0,0,{effect},{body}\n'
def copies(*,chain=False,accepted=True):
    if chain:
        events,visible=load([record(r'{\pos(100,100)}ABCD',1.5,4.5,'fx'),
            record(r'{\pos(100,100)}AB CD',1,4),record(r'{\pos(100,100)}ABCD',2,5)])
        events[0],events[1]=events[1],events[0]
        return events,visible
    return load([record(r'{\pos(100,100)}ABCD',1,4),
        record(r'{\pos('+('100' if accepted else '200')+r',100)}AB CD',1.1,4.1)])
def reveal(*,gaps=False,accepted=True,two=False):
    lines=[]
    for x,offset in [(100,0)]+([(300,3)] if two else []):
        for phase,prefix in enumerate((1,2,3,4) if accepted else (4,)):
            start=1+offset+phase*(.12 if gaps else .1)
            end=start+.1 if prefix<4 else 2+offset+(0.06 if gaps else 0)
            word='abcd';body=r'{\pos('+str(x)+',100)}'+word[:prefix]
            if prefix<4:body+=r'{\alpha&HFF&}'+word[prefix:]
            lines.append(record(body,start,end))
    return load(lines)
def snapshot(events,visible):return deepcopy(([event_comparison_fields(e) for e in events],dict(visible)))

for name,make,fn in [('full copies',copies,s.collapse_full_lyric_copies),
                     ('progressive reveal',reveal,s.collapse_progressive_text_reveals)]:
    for mode in ('accepted','rejected'):
        events,visible=make(accepted=mode=='accepted');before=snapshot(events,visible)
        result=fn(events,visible)
        check(name+' '+mode+' inputs unchanged',snapshot(events,visible)==before)
        check(name+' '+mode+' result explicit',isinstance(result,s.TextVisibilityResult) and
            isinstance(result.visibility_updates,dict))
        check(name+' '+mode+' delta sparse',999999 not in result.visibility_updates and
            set(result.visibility_updates)<=set(visible))
        check(name+' '+mode+' historical entries retained',visible[999999]=='historical removed source' and
            all(key in visible for key in before[1]))
        check(name+' '+mode+' accepted changes only',bool(result.visibility_updates)==(mode=='accepted'))
        if mode=='rejected':
            check(name+' rejected retained event identity',len(events)==len(result.events) and
                all(a is b for a,b in zip(events,result.events)))
        else:
            check(name+' accepted count explicit',result.removed_count==len(events)-len(result.events))
            visible.update(result.visibility_updates)
            applied=deepcopy(visible);result.visibility_updates.clear()
            check(name+' caller application independently owned',visible==applied)
        again=fn(events,MappingProxyType(before[1]))
        check(name+' read-only map accepted',again.removed_count==result.removed_count)
        check(name+' separate deltas per invocation',again.visibility_updates is not result.visibility_updates)
        try:again.events=[]
        except FrozenInstanceError:check(name+' immutable result bindings',True)
        else:raise AssertionError('result bindings should be immutable')

class LookupOnly(Mapping):
    """Reading individual entries is allowed; copying/iterating history is not."""
    def __init__(self,values):self.values=values
    def __getitem__(self,key):return self.values[key]
    def __len__(self):return len(self.values)
    def __iter__(self):raise AssertionError('whole visibility map traversed')

for name,make,fn in [('full copies',copies,s.collapse_full_lyric_copies),
                     ('progressive reveal',reveal,s.collapse_progressive_text_reveals)]:
    events,visible=make();result=fn(events,LookupOnly(visible))
    check(name+' does not copy or traverse input history',bool(result.visibility_updates))
    check(name+' delta values agree with accepted captions',all(
        result.visibility_updates[e.source_index]==s.simplify_text(e.text,visible_only=True)[1]
        for e in result.events if e.source_index in result.visibility_updates))

events,visible=copies(chain=True);before=snapshot(events,visible)
result=s.collapse_full_lyric_copies(events,visible)
check('later full-copy cluster sees pending spaced caption',result.removed_count==2 and
    len(result.events)==1 and s.simplify_text(result.events[0].text,visible_only=True)[1]=='AB CD')
check('cluster overlay leaves caller text original',snapshot(events,visible)==before and
    visible[result.events[0].source_index]=='ABCD' and
    result.visibility_updates[result.events[0].source_index]=='AB CD')

events,visible=reveal(gaps=True);before=snapshot(events,visible)
result=s.collapse_progressive_text_reveals(events,visible)
check('zero-count reveal returns visibility updates',result.removed_count==0 and len(result.visibility_updates)==4)
check('zero-count reveal preserves authored gaps',[(e.start_s,e.end_s) for e in result.events]==
    [(1.,1.1),(1.12,1.22),(1.24,1.34),(1.36,2.06)])
check('zero-count reveal does not mutate caller map',snapshot(events,visible)==before)
check('zero-count reveal emits complete captions',all(s.simplify_text(e.text,visible_only=True)[1]=='abcd'
    for e in result.events))

events,visible=reveal(accepted=False);result=s.collapse_progressive_text_reveals(events,visible)
check('ineligible reveal keeps early-return list identity',result.events is events and not result.visibility_updates)

def two_copy_families():
    events,visible=copies()
    second=[s.replace_event(e,source_index=e.source_index+100,
        start_s=e.start_s+10,end_s=e.end_s+10,
        start=s.format_time(e.start_s+10),end=s.format_time(e.end_s+10)) for e in events]
    return events+second,{**visible,**{e.source_index+100:visible[e.source_index] for e in events}}

for name,make,fn,helper in [
    ('full copies',two_copy_families,s.collapse_full_lyric_copies,'render_simplified_caption'),
    ('progressive reveal',lambda:reveal(two=True),s.collapse_progressive_text_reveals,'_select_progressive_reveal_caption'),
]:
    events,visible=make();before=snapshot(events,visible);owner=inspect.getmodule(fn);original=getattr(owner,helper);calls=[]
    def fail_after_first(*args,**kwargs):
        calls.append(1)
        if len(calls)==2:raise RuntimeError('injected failure after first accepted caption')
        return original(*args,**kwargs)
    setattr(owner,helper,fail_after_first)
    try:fn(events,visible)
    except RuntimeError as error:check(name+' failure occurs after first caption',len(calls)==2 and str(error).startswith('injected'))
    else:raise AssertionError('expected failure')
    finally:setattr(owner,helper,original)
    check(name+' failed pass leaves shared inputs untouched',snapshot(events,visible)==before)

(ROOT/'validation/text-visibility-ownership-checks.json').write_text(json.dumps(dict(
    version=s.__version__,count=len(checks),checks=checks),indent=2)+'\n')
print(len(checks),'text visibility ownership checks passed')
