"""Shrinking-row ownership, fixed-boundary reads and installed-module execution."""
import test_paths
from copy import deepcopy
from dataclasses import FrozenInstanceError,replace
from pathlib import Path
from types import MappingProxyType,SimpleNamespace
from typing import get_type_hints
import pickle
import inspect
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import simplify_ass as engine
from _simplify_ass import shrinking_rows as rows, boundary_groups
from check_windows_installer import ROOT,load_installer
from shrinking_row_test_helpers import shrinking_inputs

RECORDS=('ShrinkingRowSource','ShrinkingRowIndex','ShrinkingRowProposal')
FUNCTIONS=('_eligible_shrinking_row_families','_shrinking_row_geometry',
    '_profile_shrinking_row_source','_index_shrinking_row_hold','_prove_shrinking_row_glyph',
    '_index_shrinking_row_sources','_shrinking_row_owners','_adjust_shrinking_row_fade_handoffs',
    'collapse_shrinking_glyph_rows')
COLD_CHECKS=r'''
from pathlib import Path
from _simplify_ass import shrinking_rows as rows, boundary_groups
assert 'simplify_ass' not in sys.modules
assert not any(n.split('.')[0] in {'PIL','fontTools','uharfbuzz'} for n in sys.modules)
empty={}
assert rows.collapse_shrinking_glyph_rows(empty,None,2)==(empty,0)
assert rows.collapse_shrinking_glyph_rows(empty,None,2)[0] is empty
assert boundary_groups.nearby_boundary_groups({},('missing',),1.)==[]
metric=rows.FontMetrics([Path(sys.argv[1])]);assert metric.matching_face('Arial',0,False)
for variant,expected in (('complete',3),('partial',0),('gap',0),('ambiguous',0),('fade',3),('gap_fade',3)):
    events=shrinking_inputs(metric,variant=variant,unresolved=True)
    output,count=rows.collapse_shrinking_glyph_rows(events,metric,2)
    assert count==expected and len(output)==len(events)-expected
    if expected:
        caption=next(e for e in output.values() if e.name!='unrelated' and 'abc' in e.text)
        assert (caption.start_s,caption.end_s)==(1.2 if variant=='fade' else 1.,3.5)
    else:assert output is events
assert 'simplify_ass' not in sys.modules
import simplify_ass as engine
assert engine.collapse_shrinking_glyph_rows is rows.collapse_shrinking_glyph_rows
assert engine.nearby_boundary_groups is rows.nearby_boundary_groups is boundary_groups.nearby_boundary_groups
'''
COLD_CODE=Path(__file__).with_name('shrinking_row_test_helpers.py').read_text()+COLD_CHECKS


class ShrinkingRowModuleChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.metric=engine.FontMetrics([ROOT/'fonts'])
        assert cls.metric.matching_face('Arial',0,False),'Required exact Arial regular missing'

    def test_canonical_aliases_annotations_and_historical_root_pickle(self):
        for name in RECORDS+FUNCTIONS:
            value=getattr(rows,name);self.assertIs(value,getattr(engine,name));get_type_hints(value)
            self.assertIs(pickle.loads(('csimplify_ass\n'+name+'\n.').encode()),value)
            self.assertIs(pickle.loads(pickle.dumps(value)),value)
        self.assertIs(rows.Event,engine.Event)
        self.assertIs(engine.nearby_boundary_groups,boundary_groups.nearby_boundary_groups)
        self.assertIs(rows.nearby_boundary_groups,boundary_groups.nearby_boundary_groups)
        self.assertIs(pickle.loads(b'csimplify_ass\nnearby_boundary_groups\n.'),boundary_groups.nearby_boundary_groups)

    def test_query_keeps_authored_times_borrowed_groups_and_fixed_inclusive_window(self):
        slack=.05+1e-6
        times=(-slack-1e-9,-slack,-.04,0.,.04,slack,slack+1e-9,.08)
        groups={time:[object()] for time in times}
        index=MappingProxyType({('caption',):(times,MappingProxyType(groups))})
        selected=boundary_groups.nearby_boundary_groups(index,('caption',),0.)
        self.assertEqual([t for t,g in selected],list(times[1:6]))
        self.assertTrue(all(g is groups[t] for t,g in selected))
        self.assertNotIn(.08,[t for t,g in selected])
        self.assertEqual(boundary_groups.nearby_boundary_groups(index,('missing',),0.),[])
        self.assertEqual(tuple(groups),times)
        # The unchanged boundary-glyph consumer shares the same query owner.
        events=shrinking_inputs(self.metric);families=rows._eligible_shrinking_row_families(events)
        local=rows._index_shrinking_row_sources(events,families,2)
        peers=next(iter(local.groups.values()));held=next(e for e in events.values() if e.text.endswith('abc'))
        words={held.source_index:'abc'};key=('word',)
        with patch.object(inspect.getmodule(engine._match_boundary_glyph_words),
                          'nearby_boundary_groups',wraps=boundary_groups.nearby_boundary_groups) as query:
            result=engine._match_boundary_glyph_words(key,1.5,[(e,(m[0],m[1]),c) for e,c,m in peers],{key:([1.5],{1.5:[held]})},words)
        self.assertEqual(query.call_count,1);self.assertEqual(result,[held])

    def test_profiles_indexes_and_frozen_records_preserve_local_and_shallow_ownership(self):
        events=shrinking_inputs(self.metric,unresolved=True);before=deepcopy({k:vars(e) for k,e in events.items()})
        families=rows._eligible_shrinking_row_families(events)
        original=next(e for e in events.values() if r'\move' in e.text)
        profile=rows._profile_shrinking_row_source(original,families)
        self.assertIsNot(profile.event,original);self.assertIsNot(profile.event.state,original.state)
        for field in ('defaults','styles','measurement','evidence'):
            self.assertIs(getattr(profile.event,field),getattr(original,field))
        first=rows._index_shrinking_row_sources(events,families,2)
        second=rows._index_shrinking_row_sources(events,families,2)
        self.assertIsNot(first.groups,second.groups);self.assertIsNot(first.caption_index,second.caption_index)
        peers=next(iter(first.groups.values()));held=next(iter(first.caption_index.values()))[1][1.5][0]
        proposal=rows.ShrinkingRowProposal(1,1.5,'0',peers,held)
        self.assertIs(proposal.peers,peers);self.assertIs(proposal.held,held)
        for record,field in ((profile,'moves'),(first,'groups'),(proposal,'held')):
            with self.assertRaises(FrozenInstanceError):setattr(record,field,None)
        profile.moves.clear();first.groups.clear()
        self.assertTrue(second.groups);self.assertEqual({k:vars(e) for k,e in events.items()},before)

    def test_complete_rows_keep_paint_pose_context_order_and_borrowed_input_caches(self):
        for unresolved in (False,True):
            for reverse in (False,True):
                events=shrinking_inputs(self.metric,unresolved=unresolved,reverse=reverse)
                before=deepcopy({k:vars(e) for k,e in events.items()});states={k:e.state for k,e in events.items()}
                borrowed=MappingProxyType(events);output,count=rows.collapse_shrinking_glyph_rows(borrowed,self.metric,2)
                self.assertEqual(count,3);self.assertEqual(len(output),2)
                self.assertEqual(list(output),[k for k in events if k in output])
                caption=next(e for e in output.values() if e.name!='unrelated')
                self.assertEqual((caption.start_s,caption.end_s),(1.,3.5))
                self.assertEqual(engine.get_pos(caption.text),(500.,100.))
                self.assertEqual((caption.state['1c'],caption.state['3c']),('ABCDEF','123456'))
                self.assertEqual(engine.OVERRIDE_RE.sub('',caption.text),'abc')
                source=events[caption.source_index]
                for field in ('defaults','styles','measurement'):
                    self.assertIs(getattr(caption,field),getattr(source,field))
                sentinel=next(e for e in events.values() if e.name=='unrelated')
                self.assertIs(output[sentinel.source_index],sentinel)
                self.assertEqual({k:vars(e) for k,e in events.items()},before)
                self.assertTrue(all(e.state is states[k] for k,e in events.items()))
                again,repeated=rows.collapse_shrinking_glyph_rows(output,self.metric,2)
                self.assertIs(again,output);self.assertEqual(repeated,0)

    def test_freezing_expires_old_coverage_without_extending_source_pose_evidence(self):
        events=shrinking_inputs(self.metric)
        original=next(e for e in events.values() if e.text.endswith('abc'))
        evidence=engine.EventEvidence(original_contour_points=((0,0),(1,0),(1,1)),
            opaque_spans=((1.5,3.5),),frame_pose_intervals=((1.5,3.5,(0,0,0)),))
        held=replace(original,evidence=evidence);events[held.source_index]=held
        output,count=rows.collapse_shrinking_glyph_rows(events,self.metric,2)
        self.assertEqual(count,3);caption=output[held.source_index]
        self.assertIs(held.evidence,evidence)
        self.assertIsNone(caption.evidence.original_contour_points)
        self.assertIsNone(caption.evidence.opaque_spans)
        self.assertEqual(caption.evidence.frame_pose_intervals,((1.5,3.5,(0,0,0)),))
        self.assertEqual(caption.start_s,1.)

    def test_incomplete_ambiguous_or_gapped_rows_and_unavailable_fits_refuse_without_edits(self):
        for variant in ('partial','ambiguous','gap'):
            events=shrinking_inputs(self.metric,variant=variant);before=deepcopy({k:vars(e) for k,e in events.items()})
            output,count=rows.collapse_shrinking_glyph_rows(events,self.metric,2)
            self.assertIs(output,events);self.assertEqual(count,0);self.assertEqual({k:vars(e) for k,e in events.items()},before)
        events=shrinking_inputs(self.metric)
        for metric in (None,SimpleNamespace(available=False)):
            self.assertIs(rows.collapse_shrinking_glyph_rows(events,metric,2)[0],events)
        with patch.object(rows,'matches_authored_glyph_positions',return_value=False):
            self.assertIs(rows.collapse_shrinking_glyph_rows(events,self.metric,2)[0],events)

    def test_terminal_fade_handoffs_keep_gaps_and_uncertain_visible_predecessors(self):
        for variant,start,previous_end in (('fade',1.2,1.2),('gap_fade',1.,.6),('visible_predecessor',1.,1.5)):
            events=shrinking_inputs(self.metric,variant=variant);before=deepcopy({k:vars(e) for k,e in events.items()})
            output,count=rows.collapse_shrinking_glyph_rows(events,self.metric,2)
            self.assertEqual(count,3)
            caption=next(e for e in output.values() if e.text.endswith('abc'))
            preceding=next(e for e in output.values() if e.text.endswith('xyz'))
            self.assertEqual((caption.start_s,preceding.end_s),(start,previous_end))
            self.assertEqual({k:vars(e) for k,e in events.items()},before)

    def test_source_preparation_keeps_original_timing_history_stage_order_and_accounting(self):
        events=shrinking_inputs(self.metric);source=SimpleNamespace(events=events)
        held=next(e for e in events.values() if e.text.endswith('abc'));order=[]
        def vectors(working,*args,**kwargs):order.append('vectors');return working,0
        def rotation(working):order.append('rotation');return working
        def shrink(*args):order.append('shrink');return rows.collapse_shrinking_glyph_rows(*args)
        def lifecycles(working,*args,**kwargs):order.append('lifecycles');return SimpleNamespace(events=list(working.values()),rows=[],removed_count=0)
        def collect(working,*args,**kwargs):return SimpleNamespace(events=working,rows=[],words={},positions={})
        def remove(working,*args,**kwargs):return SimpleNamespace(events=working,rows=[],removed_effects=0,paint_families=[])
        def reconstruct(working,*args,**kwargs):return SimpleNamespace(events=working,rows=[])
        with patch.object(engine,'recover_vector_text_cues',side_effect=vectors), \
             patch.object(engine,'normalize_animated_rotations',side_effect=rotation), \
             patch.object(engine,'collapse_shrinking_glyph_rows',side_effect=shrink), \
             patch.object(engine,'reconstruct_glyph_lifecycles',side_effect=lifecycles), \
             patch.object(engine,'collect_source_text_rows',side_effect=collect), \
             patch.object(engine,'remove_source_fragment_effects',side_effect=remove), \
             patch.object(engine,'_collect_caption_paint_timelines',return_value=()), \
             patch.object(engine,'reconstruct_text_rows',side_effect=reconstruct):
            result=engine._prepare_source_text(source,set(),engine.SimplifyConfig(),self.metric)
        self.assertEqual(order,['vectors','rotation','shrink','lifecycles'])
        self.assertEqual(result.effects_removed,3)
        self.assertEqual(result.events[held.source_index].start_s,1.)
        self.assertIs(result.timing_sources[held.source_index],held)
        self.assertEqual(result.timing_sources[held.source_index].start_s,1.5)
        with patch.object(engine,'collapse_shrinking_glyph_rows',side_effect=AssertionError('level-two stage')):
            legacy=engine._prepare_source_text(source,set(),engine.SimplifyConfig(level=2),self.metric)
        self.assertIs(legacy.events,events);self.assertIs(legacy.timing_sources,events)

    def test_cold_source_installed_execution_and_owned_uninstall(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);unrelated=root/'unrelated';unrelated.mkdir();installer=load_installer()
            target=root/'installed tools with spaces';_,installed=installer.install(ROOT,target,individual_launchers=False)
            for tools in (ROOT,installed):
                child=subprocess.run([sys.executable,'-I','-c','import sys\nsys.path.insert(0,'+repr(str(tools))+')\n'+COLD_CODE,str(ROOT/'fonts')],cwd=unrelated,capture_output=True,text=True)
                self.assertEqual(child.returncode,0,child.stdout+child.stderr)
            user=installed/'_simplify_ass/user.py';user.write_text('# user\n');installer.remove(target)
            self.assertEqual(user.read_text(),'# user\n')
            for name in ('shrinking_rows','boundary_groups'):
                self.assertFalse((installed/'_simplify_ass'/f'{name}.py').exists())
                self.assertFalse(any((installed/'_simplify_ass').rglob(name+'*.pyc')))


if __name__=='__main__':unittest.main()
