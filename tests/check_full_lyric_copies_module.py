"""Full-copy ownership, sparse handoff and independent installed execution."""
import test_paths
from copy import deepcopy
from dataclasses import replace
from itertools import permutations
from pathlib import Path
from types import MappingProxyType,SimpleNamespace
from typing import get_type_hints
import pickle
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import simplify_ass as engine
from _simplify_ass import full_lyric_copies as copies, text_visibility
from full_lyric_copy_test_helpers import full_copy_inputs
from check_windows_installer import ROOT,load_installer

COLD_CHECKS=r'''
from types import MappingProxyType
from _simplify_ass import full_lyric_copies as copies, text_visibility
assert 'simplify_ass' not in sys.modules
for variant,count in (('complete',1),('chain',2),('separate',0),('gap',0),('pose',1)):
    events,visible=full_copy_inputs(variant=variant)
    result=copies.collapse_full_lyric_copies(events,MappingProxyType(visible))
    assert isinstance(result,text_visibility.TextVisibilityResult)
    assert result.removed_count==count
    assert result.events[-1] is events[-1]
    assert 999999 not in result.visibility_updates
    again=copies.collapse_full_lyric_copies(result.events,{**visible,**result.visibility_updates})
    assert again.removed_count==0 and not again.visibility_updates
assert 'simplify_ass' not in sys.modules
assert not any(n.split('.')[0] in {'PIL','fontTools','uharfbuzz'} for n in sys.modules)
import simplify_ass as engine
assert engine.collapse_full_lyric_copies is copies.collapse_full_lyric_copies
'''
COLD_CODE=Path(__file__).with_name('full_lyric_copy_test_helpers.py').read_text()+COLD_CHECKS


class FullLyricCopyModuleChecks(unittest.TestCase):
    def test_canonical_alias_result_annotations_and_historical_lookup(self):
        fn=copies.collapse_full_lyric_copies
        self.assertIs(fn,engine.collapse_full_lyric_copies)
        self.assertIs(copies.Event,engine.Event)
        self.assertIs(copies.TextVisibilityResult,text_visibility.TextVisibilityResult)
        self.assertIs(get_type_hints(fn)['return'],engine.TextVisibilityResult)
        self.assertIs(pickle.loads(b'csimplify_ass\ncollapse_full_lyric_copies\n.'),fn)
        self.assertIs(pickle.loads(pickle.dumps(fn)),fn)

    def test_complete_selection_keeps_paint_geometry_timing_and_borrowed_inputs(self):
        events,visible=full_copy_inputs();before=deepcopy(([vars(e) for e in events],visible));states=[e.state for e in events]
        result=copies.collapse_full_lyric_copies(events,MappingProxyType(visible))
        self.assertEqual(result.removed_count,1)
        caption=result.events[0]
        self.assertEqual(engine.OVERRIDE_RE.sub('',caption.text),'AB CD')
        self.assertEqual((caption.start_s,caption.end_s),(1.,4.1))
        self.assertEqual(engine.get_pos(caption.text),(320.,100.))
        self.assertEqual((caption.state['1c'],caption.state['3c'],caption.state['3a'],caption.state['bord']),('FFFFFF','DDDDDD',96,1.25))
        self.assertEqual((caption.source_index,caption.layer,caption.effect),(events[0].source_index,'0',''))
        self.assertIs(caption.measurement,events[0].measurement)
        self.assertIs(result.events[-1],events[-1])
        self.assertEqual(result.visibility_updates,{caption.source_index:'AB CD'})
        self.assertEqual(([vars(e) for e in events],visible),before)
        self.assertTrue(all(e.state is state for e,state in zip(events,states)))

    def test_pending_overlay_sparse_equal_assignments_and_repeat(self):
        for variant in ('complete','chain','pose'):
            events,visible=full_copy_inputs(variant=variant);before=deepcopy(visible)
            result=copies.collapse_full_lyric_copies(events,visible)
            self.assertEqual(result.removed_count,2 if variant=='chain' else 1)
            self.assertEqual(len(result.visibility_updates),1)
            self.assertEqual(next(iter(result.visibility_updates.values())),'AB CD')
            self.assertEqual(visible,before)
            if variant=='pose':self.assertTrue(all(visible[k]==v for k,v in result.visibility_updates.items()))
            repeated=copies.collapse_full_lyric_copies(result.events,{**visible,**result.visibility_updates})
            self.assertEqual(repeated.events,result.events);self.assertFalse(repeated.visibility_updates)
            result.visibility_updates.clear();self.assertEqual(visible,before)

    def test_refused_families_keep_event_identity(self):
        for variant in ('separate','gap'):
            events,visible=full_copy_inputs(variant=variant)
            result=copies.collapse_full_lyric_copies(events,visible)
            self.assertEqual(result.removed_count,0);self.assertFalse(result.visibility_updates)
            self.assertTrue(all(a is b for a,b in zip(events,result.events)))

    def test_pose_support_retains_source_intervals_and_expires_old_coverage(self):
        events,visible=full_copy_inputs(variant='pose');before=deepcopy(events)
        result=copies.collapse_full_lyric_copies(events,visible);caption=result.events[0]
        self.assertEqual(set(caption.evidence.frame_pose_intervals),set(events[0].evidence.frame_pose_intervals+events[1].evidence.frame_pose_intervals))
        self.assertIsNone(caption.evidence.original_contour_points);self.assertIsNone(caption.evidence.opaque_spans)
        self.assertEqual(events,before)

    def test_caller_applies_visibility_before_frame_consumer(self):
        events,visible=full_copy_inputs()
        frozen=SimpleNamespace(captions=events,vectors=[],visible=visible,spaces={},statistics={'dropped':0},blanks=[])
        prepared=SimpleNamespace(rows=[],effects_removed=0,timing_sources=[])
        source=SimpleNamespace(styles={},events={},scaled_borders=True)
        class HandoffChecked(Exception):pass
        def next_consumer(output,adopted,**kwargs):
            self.assertIs(adopted,visible)
            self.assertEqual(len(output),2)
            caption=next(e for e in output if e.name!='unrelated')
            self.assertEqual(adopted[caption.source_index],'AB CD')
            self.assertEqual(adopted[999999],'historical source')
            self.assertEqual(engine.OVERRIDE_RE.sub('',caption.text),'AB CD')
            raise HandoffChecked
        with patch.object(engine,'collapse_matching_lyric_layers',side_effect=lambda e,v,m:(e,0)),patch.object(engine,'merge_frame_animation',side_effect=next_consumer):
            self.assertRaises(HandoffChecked,engine._consolidate_text_events,source,prepared,frozen,set(),engine.SimplifyConfig(),None)

    def test_chains_retain_full_coverage_across_orders_and_anchor_ids(self):
        failures=[]
        for order in permutations(range(3)):
            for ids in permutations((100,200,300)):
                for mirror in (False,True):
                    events,visible=full_copy_inputs(variant='chain')
                    family=[];words={999999:'historical source'}
                    for event,index in zip(events[:3],ids):
                        start,end=(6-event.end_s,6-event.start_s) if mirror else (event.start_s,event.end_s)
                        item=engine.replace_event(event,source_index=index,start_s=start,end_s=end,
                            start=engine.format_time(start),end=engine.format_time(end))
                        family.append(item);words[index]=visible[event.source_index]
                    ordered=[family[n] for n in order]+[events[-1]]
                    words[events[-1].source_index]='Independent'
                    before=deepcopy(([vars(e) for e in ordered],words))
                    result=copies.collapse_full_lyric_copies(ordered,MappingProxyType(words))
                    spans=sorted((e.start_s,e.end_s) for e in result.events if e.name!='unrelated')
                    coverage=[]
                    for start,end in spans:
                        if coverage and start<=coverage[-1][1]:coverage[-1]=(coverage[-1][0],max(end,coverage[-1][1]))
                        else:coverage.append((start,end))
                    if coverage!=[(1.,5.)]:failures.append((order,ids,mirror,coverage))
                    self.assertEqual(result.removed_count,len(ordered)-len(result.events))
                    self.assertIs(result.events[-1],events[-1])
                    self.assertEqual(([vars(e) for e in ordered],words),before)
        self.assertEqual(failures,[],str(failures[:4]))

    def test_chained_pose_support_keeps_original_exposure_for_all_survivors(self):
        for order in permutations(range(3)):
            for ids in permutations((100,200,300)):
                events,visible=full_copy_inputs(variant='chain')
                family=[];words={}
                for n,(event,index) in enumerate(zip(events[:3],ids)):
                    text=event.text.rsplit('}',1)[0]+'}AB CD'
                    event=engine.replace_event(event,text=text,source_index=index)
                    evidence=engine.EventEvidence(
                        frame_pose_intervals=((event.start_s+.1,event.end_s-.1,(n*40,96,255)),),
                        original_contour_points=((1.,1.),(2.,2.)),opaque_spans=((event.start_s,event.end_s),))
                    family.append(replace(event,evidence=evidence));words[index]='AB CD'
                original=deepcopy(family)
                result=copies.collapse_full_lyric_copies([family[n] for n in order],words)
                expected={span for e in family for span in e.evidence.frame_pose_intervals}
                actual={span for e in result.events for span in e.evidence.frame_pose_intervals or ()}
                self.assertEqual(actual,expected,(order,ids))
                self.assertTrue(all(e.evidence.original_contour_points is None and e.evidence.opaque_spans is None
                    for e in result.events if not any(e is source for source in family)))
                self.assertEqual(family,original)

    def test_pending_spaced_caption_retains_only_compatible_source_pose(self):
        events,visible=full_copy_inputs(variant='chain')
        events=[replace(e,evidence=engine.EventEvidence(frame_pose_intervals=engine._frame_pose_intervals(e))) for e in events]
        spaced=next(e for e in events if visible[e.source_index]=='AB CD')
        result=copies.collapse_full_lyric_copies(events,visible)
        caption=result.events[0]
        self.assertEqual((caption.start_s,caption.end_s),(1.,5.))
        self.assertEqual(caption.evidence.frame_pose_intervals,spaced.evidence.frame_pose_intervals)
        self.assertEqual(engine.OVERRIDE_RE.sub('',caption.text),'AB CD')
        self.assertEqual((caption.state['1c'],caption.state['3c'],caption.state['3a'],caption.state['bord']),('FFFFFF','DDDDDD',96,1.25))

    def test_matching_original_pose_wins_when_pending_caption_has_other_geometry(self):
        events,visible=full_copy_inputs(variant='chain')
        family=[]
        for n,event in enumerate(events[:3]):
            prefix=event.text.rsplit('}',1)[0]
            event=engine.replace_event(event,text=prefix+('\\fs50' if n==0 else '')+'}AB CD',effect='' if n==0 else 'fx')
            family.append(replace(event,evidence=engine.EventEvidence(frame_pose_intervals=engine._frame_pose_intervals(event))))
        result=copies.collapse_full_lyric_copies(family,{e.source_index:'AB CD' for e in family})
        self.assertEqual(len(result.events),1)
        caption=result.events[0]
        self.assertEqual(caption.state['fs'],40)
        self.assertEqual((caption.start_s,caption.end_s),(1.,5.))
        self.assertEqual(set(caption.evidence.frame_pose_intervals or ()),
            {span for e in family[1:] for span in e.evidence.frame_pose_intervals})

    def test_timing_handoff_does_not_expand_matching_or_iterate(self):
        from full_lyric_copy_test_helpers import HEADER
        specs=[('AB CD',1.5,4.5),('A B C D',2,5),('ABCD',2.5,5.5)]
        text=HEADER+''.join('Dialogue: 0,'+engine.format_time(start)+','+engine.format_time(end)+
            r',Default,,0,0,0,,{\pos(320,100)}'+word+'\n' for word,start,end in specs)
        events=list(engine._resolve_document_state(engine.parse_subtitle_document(text)).events.values())
        for event in events:event.lyric=True
        visible={e.source_index:engine.simplify_text(e.text,visible_only=True)[1] for e in events}
        result=copies.collapse_full_lyric_copies(events,visible)
        self.assertEqual(result.removed_count,1)
        self.assertEqual([(e.start_s,e.end_s) for e in result.events],[(1.5,5.),(2.5,5.5)])
        repeated=copies.collapse_full_lyric_copies(result.events,{**visible,**result.visibility_updates})
        self.assertEqual(repeated.removed_count,1)

    def test_cold_source_installed_processing_and_owned_uninstall(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);target=root/'installed tools with spaces';installer=load_installer()
            _,installed=installer.install(ROOT,target,individual_launchers=False)
            for tools in (ROOT,installed):
                code='import sys\nsys.path.insert(0,'+repr(str(tools))+')\n'+COLD_CODE
                child=subprocess.run([sys.executable,'-I','-c',code],cwd=root,capture_output=True,text=True)
                self.assertEqual(child.returncode,0,child.stderr)
            user=installed/'_simplify_ass/user.py';user.write_text('# user\n')
            installer.remove(target);self.assertEqual(user.read_text(),'# user\n')
            self.assertFalse((installed/'_simplify_ass/full_lyric_copies.py').exists())
            self.assertFalse(any((installed/'_simplify_ass').rglob('full_lyric_copies*.pyc')))


if __name__=='__main__':unittest.main()
