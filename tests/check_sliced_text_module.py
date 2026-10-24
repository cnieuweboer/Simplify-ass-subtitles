"""Complete strip coverage, paint/timing ownership and installed source processing."""
import test_paths
from copy import deepcopy
from dataclasses import FrozenInstanceError,replace
import inspect
from pathlib import Path
import pickle
import subprocess
import sys
import tempfile
from typing import get_type_hints
import unittest
from unittest.mock import patch

from _simplify_ass import source_fragments
import simplify_ass as engine
from _simplify_ass import sliced_text as sliced, caption_geometry
from check_windows_installer import ROOT,load_installer
from sliced_text_test_helpers import sliced_inputs

RECORDS = ('SlicedTextIndex','SlicedTextEvent')
FUNCTIONS = (
    '_eligible_sliced_text_families','_sliced_text_layout','_sliced_text_paint',
    '_profile_sliced_text_event','_sliced_text_final_state','_index_sliced_text_pulse',
    '_index_sliced_text_tile','_index_sliced_text_event','_prove_sliced_text_strip_phases',
    '_propose_sliced_text_caption','_propose_sliced_text_replacements','_accept_sliced_text_ownership',
    '_group_sliced_text_cues','_adjust_sliced_text_cue_timing','_adjust_authored_sliced_text_timing',
    'collapse_sliced_text_sequences',
)

COLD_CHECKS = r'''
from copy import deepcopy
from pathlib import Path
from _simplify_ass import sliced_text as s, caption_geometry as g
assert 'simplify_ass' not in sys.modules
assert not any(n.split('.')[0] in {'PIL','fontTools','uharfbuzz'} for n in sys.modules)
for options in ({},{'partial':True},{'pulse':True},{'authored':True},{'unresolved':True}):
    events=sliced_inputs(reverse=True,**options)
    before=deepcopy([vars(e) for e in events]);states=[e.state for e in events]
    result,count=s.collapse_sliced_text_sequences(events)
    expected=0 if options.get('partial') else 7 if options.get('pulse') else 6
    assert count==expected and len(result)==len(events)-count
    assert any(e is original for e in result for original in events if original.source_index==99999)
    if count:
        caption=next(e for e in result if e.kind=='Dialogue' and e.source_index!=99999)
        assert (caption.start_s,caption.end_s)==(1. if options.get('authored') else .5,3.)
    else:assert result is events
    assert [vars(e) for e in events]==before and all(e.state is state for e,state in zip(events,states))
    again,repeated=s.collapse_sliced_text_sequences(result)
    assert again==result and repeated==0
assert s.rectangle_clip is g.rectangle_clip
assert 'simplify_ass' not in sys.modules
assert not any(n.split('.')[0] in {'PIL','fontTools','uharfbuzz'} for n in sys.modules)
from _simplify_ass import source_fragments
import simplify_ass as engine
assert engine.collapse_sliced_text_sequences is s.collapse_sliced_text_sequences
assert engine.SlicedTextIndex is s.SlicedTextIndex
assert engine.SlicedTextEvent is s.SlicedTextEvent
assert engine.rectangle_clip is g.rectangle_clip
assert Path(s.__file__).resolve()==Path(engine.__file__).resolve().parent/'_simplify_ass/sliced_text.py'
import py_compile
py_compile.compile(s.__file__,doraise=True)
'''
COLD_CODE = Path(__file__).with_name('sliced_text_test_helpers.py').read_text()+COLD_CHECKS


class SlicedTextModuleChecks(unittest.TestCase):
    def test_canonical_aliases_annotations_and_historical_root_lookup(self):
        for name in RECORDS+FUNCTIONS:
            value=getattr(sliced,name)
            self.assertIs(value,getattr(engine,name))
            get_type_hints(value)
            self.assertIs(pickle.loads(('csimplify_ass\n'+name+'\n.').encode()),value)
            self.assertIs(pickle.loads(pickle.dumps(value)),value)
        self.assertIs(sliced.Event,engine.Event)
        self.assertIs(sliced.rectangle_clip,caption_geometry.rectangle_clip)
        self.assertIs(sliced.rectangle_clip,engine.rectangle_clip)
        self.assertEqual(tuple(inspect.signature(sliced.collapse_sliced_text_sequences).parameters),('events',))

    def test_profiles_and_shallow_frozen_indexes_keep_local_state_and_borrow_catalogs(self):
        events=sliced_inputs(sentinel=False,unresolved=True)
        before=deepcopy([vars(e) for e in events])
        families=sliced._eligible_sliced_text_families(events)
        profiles=[sliced._profile_sliced_text_event(e,families) for e in events]
        self.assertTrue(all(p is not None for p in profiles))
        for original,profile in zip(events,profiles):
            self.assertIsNot(profile.event,original)
            self.assertIsNot(profile.event.state,original.state)
            for name in ('defaults','styles','measurement','evidence'):
                self.assertIs(getattr(profile.event,name),getattr(original,name))
        self.assertEqual(sliced._sliced_text_final_state(profiles[0])['1a'],0)
        indexes=[]
        for _ in range(2):
            index=sliced.SlicedTextIndex({},{},{})
            for profile in profiles:sliced._index_sliced_text_event(index,profile)
            indexes.append(index)
        first,second=indexes
        for name in ('holds','tiles','pulses'):self.assertIsNot(getattr(first,name),getattr(second,name))
        self.assertEqual((len(first.holds),len(first.tiles)),(1,2))
        self.assertIs(next(iter(first.holds.values()))[0],profiles[3].event)
        for record,name in ((first,'holds'),(profiles[0],'moves')):
            with self.assertRaises(FrozenInstanceError):setattr(record,name,None)
        first.holds.clear()
        self.assertTrue(second.holds)
        profiles[0].moves.clear()
        self.assertEqual([vars(e) for e in events],before)

    def test_supported_sequences_preserve_paint_pose_flags_inputs_and_untouched_identity(self):
        for reverse in (False,True):
            for pulse in (False,True):
                for unresolved in (False,True):
                    events=sliced_inputs(reverse=reverse,pulse=pulse,unresolved=unresolved)
                    before=deepcopy([vars(e) for e in events]);states=[e.state for e in events]
                    output,count=sliced.collapse_sliced_text_sequences(events)
                    self.assertEqual((len(output),count),(2,7 if pulse else 6))
                    caption,other=output
                    self.assertEqual((caption.start_s,caption.end_s,caption.row,caption.lyric,caption.layer),(.5,3.,8,True,'2'))
                    self.assertEqual(engine.OVERRIDE_RE.sub('',caption.text),'Hello')
                    self.assertEqual(engine.get_pos(caption.text),(320.,100.))
                    self.assertEqual((caption.state['1c'],caption.state['3c']),('DDEEFF','112233'))
                    self.assertIs(other,next(e for e in events if e.source_index==99999))
                    self.assertIs(caption.measurement,events[0].measurement)
                    self.assertEqual([vars(e) for e in events],before)
                    self.assertTrue(all(e.state is state for e,state in zip(events,states)))
                    self.assertEqual([e.source_index for e in output],sorted(e.source_index for e in output))
                    again,removed=sliced.collapse_sliced_text_sequences(output)
                    self.assertEqual(again,output);self.assertEqual(removed,0)

    def test_authored_timing_requires_complete_matching_text_and_retains_comment(self):
        for authored,beginning in ((True,1.),('Other',.5)):
            events=sliced_inputs(authored=authored)
            comment=next(e for e in events if e.kind=='Comment')
            output,count=sliced.collapse_sliced_text_sequences(events)
            self.assertEqual(count,6)
            caption=next(e for e in output if e.kind=='Dialogue' and e.source_index!=99999)
            self.assertEqual((caption.start_s,caption.end_s),(beginning,3.))
            self.assertTrue(any(e is comment for e in output))

    def test_coverage_paint_canvas_and_competing_ownership_refuse_without_edits(self):
        cases=[sliced_inputs(**options) for options in ({'partial':True},{'bad_paint':True},{'competing':True})]
        events=sliced_inputs();cases.append([replace(e,measurement=replace(e.measurement,canvas=None)) for e in events])
        for events in cases:
            before=deepcopy([vars(e) for e in events])
            output,count=sliced.collapse_sliced_text_sequences(events)
            self.assertIs(output,events);self.assertEqual(count,0)
            self.assertEqual([vars(e) for e in events],before)
        empty=[]
        self.assertIs(sliced.collapse_sliced_text_sequences(empty)[0],empty)

    def test_proposal_arbitration_and_actual_duplicate_list_slot_counts(self):
        events=sliced_inputs();caption=events[0];other=events[1]
        proposals=[({1,2},caption),({2,3},other),({9},caption)]
        sets=[ids.copy() for ids,_ in proposals]
        accepted=sliced._accept_sliced_text_ownership(proposals)
        self.assertEqual(accepted,[proposals[-1]])
        self.assertEqual([ids for ids,_ in proposals],sets)
        self.assertIs(accepted[0][1],caption)
        hold=next(e for e in events if e.start_s==1. and e.end_s==3.)
        events.append(hold)
        output,count=sliced.collapse_sliced_text_sequences(events)
        self.assertEqual((len(output),count),(2,7))
        self.assertEqual(count,len(events)-len(output))

    def test_caller_keeps_backing_handoff_source_isolation_and_aggregate_reporting(self):
        events=sliced_inputs();before=deepcopy([vars(e) for e in events])
        words={e.source_index:engine.OVERRIDE_RE.sub('',e.text) for e in events}
        positions={e.source_index:engine.get_pos(e.text) for e in events}
        captured=[]
        def backing(*args,**kwargs):
            output=engine_backing(*args,**kwargs);captured.append(output);return output
        engine_backing=engine.collapse_backed_glyph_pulses
        with patch.object(source_fragments,'collapse_backed_glyph_pulses',side_effect=backing), \
                patch.object(source_fragments,'collapse_sliced_text_sequences',wraps=sliced.collapse_sliced_text_sequences) as call:
            result=engine.remove_source_fragment_effects(events,[],words,positions,set())
        self.assertEqual(len(captured),1)
        self.assertIs(call.call_args.args[0],captured[0][0])
        self.assertEqual(result.removed_effects,6)
        self.assertEqual([vars(e) for e in events],before)

    def test_cold_source_installed_font_free_processing_and_owned_uninstall(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);unrelated=root/'unrelated';unrelated.mkdir()
            installer=load_installer();target=root/'installed tools with spaces'
            _,installed=installer.install(ROOT,target,individual_launchers=False)
            for tools in (ROOT,installed):
                child=subprocess.run([sys.executable,'-I','-c','import sys\nsys.path.insert(0,'+repr(str(tools))+')\n'+COLD_CODE],cwd=unrelated,capture_output=True,text=True)
                self.assertEqual(child.returncode,0,child.stdout+child.stderr)
            user=installed/'_simplify_ass/user.py';user.write_text('# user\n')
            installer.remove(target)
            self.assertEqual(user.read_text(),'# user\n')
            self.assertFalse((installed/'_simplify_ass/sliced_text.py').exists())
            self.assertFalse(any((installed/'_simplify_ass').rglob('sliced_text*.pyc')))


if __name__=='__main__':
    unittest.main()
