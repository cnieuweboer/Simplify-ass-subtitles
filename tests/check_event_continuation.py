#!/usr/bin/env python3
"""Check cache, replacement and reparse ownership against immutable v160."""
import test_paths  # Resolve the repository for direct test execution.
from copy import deepcopy
from dataclasses import replace,FrozenInstanceError
from pathlib import Path
import ast,importlib.util,json,random,sys
import simplify_ass as current
from event_evidence_test_helpers import event_comparison_fields,override_comparison_state
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('event_continuation_reference',ROOT/'test-data/simplify_ass-v160-reference.py')
previous=importlib.util.module_from_spec(spec);sys.modules[spec.name]=previous;spec.loader.exec_module(previous)
PRIVATE={'_canvas','_script_wrap_mode','_reset_style','_alignment_set'}
HEADER='''[Script Info]
PlayResX: 640
PlayResY: 360
WrapStyle: 1
[V4+ Styles]
Format: Name, Fontname, Fontsize, Alignment, Outline, Shadow
Style: Default,Arial,40,5,2,0
Style: Other,Other Font,60,7,4,3
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
checks=[]
def check(name,condition):
 assert condition,name
 checks.append(name)
def snap(event):return event_comparison_fields(event)
def parse(module,text):
 return module._resolve_document_state(module.parse_subtitle_document(HEADER+f'Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,{text}\n'))
bodies=['Plain',r'{\rOther}{\fn\fs}Text',r'{\an0}{\rOther}{\an2}Text',r'{\rMissing}A{\r}B',r'{\rOther\an0}A{\r\an7}B']
rng=random.Random(161);tags=[r'\r',r'\rOther',r'\rMissing',r'\fn',r'\fs',r'\fs+2',r'\an0',r'\an7',r'\q2']
bodies+=[''.join('{'+''.join(rng.choices(tags,k=3))+'}'+rng.choice(['A','B','']) for _ in range(4)) for i in range(100)]
for text in bodies:
 old_doc= parse(previous,text);doc=parse(current,text);old=next(iter(old_doc.events.values()));event=next(iter(doc.events.values()))
 before=deepcopy(vars(event));check('resolved cache parity',snap(event)==snap(old))
 check('all formatting clean',all(not PRIVATE & st.keys() for st in [event.state,event.defaults,*event.styles.values()]))
 evaluation=current.event_evaluation(event)
 check('resolved evaluation borrows formatting/context',evaluation.formatting is event.state and evaluation.continuation is event.continuation)
 unresolved=replace(event,state={},continuation=current.OverrideContinuation('Other',True))
 fresh=current.event_evaluation(unresolved)
 check('unresolved evaluation restarts complete parsing',override_comparison_state(fresh)==old.state and not unresolved.state)
 check('unresolved independent result',fresh.formatting is not unresolved.state)
 for change in [dict(start_s=.5),dict(layer='2'),dict(text='Plain'),dict(text=r'{\an0\rOther\fs}New'),dict(style='Other'),dict(state=dict(event.state)),dict(state={**event.state,'fs':99}),dict(defaults=dict(event.defaults)),dict(styles=dict(event.styles))]:
  old_change=change.copy()
  if 'state' in old_change:old_change['state']={**old.state,**change['state']}
  updated=current.replace_event(event,**change);expected=previous.replace_event(old,**old_change)
  check('replacement parity',snap(updated)==snap(expected))
  check('measurement preserved',updated.measurement is event.measurement)
  if 'text' not in change and 'style' not in change:
   check('resolved edit retains history',updated.continuation is event.continuation)
  else:
   parsed=current.evaluate_effective_state(updated.text,updated.defaults,updated.styles)
   check('replacement recomputes history',updated.continuation==parsed.continuation)
 clear=current.replace_event(event,state={},continuation=current.OverrideContinuation('Other',True))
 check('cleared cache invalidates history',not clear.state and clear.continuation==current.OverrideContinuation())
 branch=current.replace_event(event,state=dict(event.state),continuation=current.OverrideContinuation('',None))
 check('explicit branch history installed',branch.continuation==current.OverrideContinuation('',None))
 # Parser history is internal: serialization records authored tags alone.
 rendered=current.render_subtitle_document(doc,[event]);reparsed=current._resolve_document_state(current.parse_subtitle_document(rendered))
 again=next(iter(reparsed.events.values()))
 check('reparse reconstructs state/history',again.state==event.state and again.continuation==event.continuation)
 check('reparse owns formatting/context',again.state is not event.state and again.continuation is not event.continuation)
 check('input unchanged',before==vars(event))
 raw=current.parse_subtitle_document(HEADER+f'Comment: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,{text}\n')
 prepared=current._prepare_text_document(raw,ROOT/'test.ass');comment=next(iter(prepared.events.values()))
 check('comment cache pair',comment.continuation==current.evaluate_effective_state(text,comment.defaults,comment.styles).continuation)
 check('raw document not cached',not next(iter(raw.events.values())).state)

# Replacement text is authoritative even with an explicit stale state/context.
event=next(iter(parse(current,r'{\rOther\an0}Old').events.values()))
new=current.replace_event(event,text='New',state={'fs':999},continuation=current.OverrideContinuation('Other',True))
check('text replacement supersedes supplied cache',new.state==event.defaults and new.continuation==current.OverrideContinuation())
try:event.continuation.alignment_set=False
except FrozenInstanceError:check('event continuation immutable',True)
else:raise AssertionError('mutable event continuation')
source=(ROOT/'simplify_ass.py').read_text();tree=ast.parse(source)
check('no legacy key literals',not any(isinstance(n,ast.Constant) and isinstance(n.value,str) and n.value in PRIVATE for n in ast.walk(tree)))
check('no adapters',not any(hasattr(current,name) for name in ['apply_tag','_legacy_effective_state','_legacy_override_state','_legacy_override_evaluation']))
report=dict(version=current.__version__,reference_version=previous.__version__,checks_passed=len(checks),source_cases=len(bodies),all_four_legacy_keys_absent=True,cache_and_replacement_history_compared=True)
(ROOT/'validation/event-continuation-checks.json').write_text(json.dumps(report,indent=2)+'\n')
print(len(checks),'event continuation checks passed')
