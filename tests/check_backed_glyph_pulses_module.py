"""Complete pulse operation ownership, arbitration and installed delivery."""
import test_paths
from copy import deepcopy
from dataclasses import FrozenInstanceError
import inspect
from pathlib import Path
import pickle
import shutil
import subprocess
import sys
import tempfile
from types import MappingProxyType
from typing import get_type_hints
import unittest
from unittest.mock import patch

import simplify_ass as engine
from _simplify_ass import backed_glyph_pulses as pulses
from check_windows_installer import ROOT,load_installer
from backed_glyph_pulse_test_helpers import FAMILY,backed_inputs

RECORDS = ('BackedPulseContext','BackedPulseRow')
FUNCTIONS = (
    '_eligible_backed_glyph_state','_parse_backed_glyph_effects',
    '_prepare_backed_glyph_pulses','_group_backed_glyph_rows',
    '_backed_glyph_pose','_backed_frames_converge','_collect_backed_row_holds',
    '_backed_row_has_conflicts','_select_backed_row_pose','_backed_sizes_are_positive',
    '_backed_foreground_coverage','_backed_transform_returns',
    '_prove_backed_foreground_pulses','_extend_backed_pulse_tails',
    '_proved_backed_row_paint','_propose_backed_pulse_row',
    '_apply_backed_pulse_proposals','collapse_backed_glyph_pulses',
)

COLD_CHECKS = r'''
from copy import deepcopy
from pathlib import Path
from _simplify_ass import backed_glyph_pulses as p
assert 'simplify_ass' not in sys.modules
assert not any(n.split('.')[0] in {'PIL','fontTools','uharfbuzz'} for n in sys.modules)
for incomplete in (False,True):
    events,words,positions=backed_inputs(incomplete=incomplete,reverse=True)
    before=deepcopy(([vars(e) for e in events],words,positions))
    result,count=p.collapse_backed_glyph_pulses(events,words,positions)
    assert count==(0 if incomplete else 8)
    assert len(result)==len(events)-count
    assert any(e is original for e in result for original in events if original.source_index==99999)
    assert ([vars(e) for e in events],words,positions)==before
    again,removed=p.collapse_backed_glyph_pulses(result,words,positions)
    assert again is result and removed==0
assert 'simplify_ass' not in sys.modules
assert not any(n.split('.')[0] in {'PIL','fontTools','uharfbuzz'} for n in sys.modules)
font_path=Path(sys.argv[1]);metric=p.FontMetrics([font_path.parent]);face=metric.matching_face(FAMILY,0,False)
assert face is not None and Path(face.path).resolve()==font_path.resolve()
events,words,positions=backed_inputs(sentinel=False)
before=deepcopy(([vars(e) for e in events],words,positions))
result,count=p.collapse_backed_glyph_pulses(events,words,positions,metric)
assert count==8 and len(result)==4 and all(0<e.state['3a']<255 for e in result)
assert len({(e.state['1c'],e.state['3c'],e.state['3a']) for e in result})==1
assert ([vars(e) for e in events],words,positions)==before
assert 'simplify_ass' not in sys.modules
import simplify_ass as engine
assert engine.collapse_backed_glyph_pulses is p.collapse_backed_glyph_pulses
assert engine.BackedPulseContext is p.BackedPulseContext
assert Path(p.__file__).resolve()==Path(engine.__file__).resolve().parent/'_simplify_ass/backed_glyph_pulses.py'
import py_compile
py_compile.compile(p.__file__,doraise=True)
'''
COLD_CODE = Path(__file__).with_name('backed_glyph_pulse_test_helpers.py').read_text()+COLD_CHECKS


class BackedGlyphPulseModuleChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.metric = engine.FontMetrics([ROOT/'fonts'])
        cls.face = cls.metric.matching_face(FAMILY,0,False)
        assert cls.face is not None,'Required exact Volkhov regular missing'
        cls.font = Path(cls.face.path)

    def test_canonical_aliases_annotations_defaults_and_historical_root_lookup(self):
        for name in RECORDS+FUNCTIONS:
            value = getattr(pulses,name)
            self.assertIs(value,getattr(engine,name))
            get_type_hints(value)
            self.assertIs(pickle.loads(('csimplify_ass\n'+name+'\n.').encode()),value)
            self.assertIs(pickle.loads(pickle.dumps(value)),value)
        self.assertIs(pulses.Event,engine.Event)
        self.assertIs(pulses.FontMetrics,engine.FontMetrics)
        self.assertIs(pulses.SourceCaptionPaint,engine.SourceCaptionPaint)
        self.assertIsNone(inspect.signature(pulses.collapse_backed_glyph_pulses).parameters['font_metrics'].default)

    def test_shallow_frozen_records_borrow_inputs_and_keep_context_buffers_local(self):
        events,words,positions = backed_inputs(sentinel=False)
        context = pulses._prepare_backed_glyph_pulses(events,words,positions)
        other = pulses._prepare_backed_glyph_pulses(events,words,positions)
        self.assertIs(context.words,words)
        self.assertIs(context.positions,positions)
        self.assertIs(context.details[events[0].source_index][0],events[0].state)
        self.assertIs(context.continuations[events[0].source_index],events[0].continuation)
        for name in ('allowed','indexed','backing','details','continuations'):
            self.assertIsNot(getattr(context,name),getattr(other,name))
        groups = pulses._group_backed_glyph_rows(context)
        key,row = next(iter(groups.items()))
        row.sort(key=lambda item:item[0][0])
        cue = pulses._collect_backed_row_holds(context,key,row)
        self.assertIsNotNone(cue)
        self.assertIs(cue.backing,row)
        for record,name in ((context,'words'),(cue,'glyphs')):
            with self.assertRaises(FrozenInstanceError):
                setattr(record,name,None)
        context.allowed.add('test-only')
        self.assertNotIn('test-only',other.allowed)
        cue.common.clear()
        self.assertTrue(other.details)

    def test_supported_rows_preserve_inputs_metadata_order_identity_and_repeat_behavior(self):
        for reverse in (False,True):
            events,words,positions = backed_inputs(reverse=reverse)
            before = deepcopy(([vars(e) for e in events],words,positions))
            states = [e.state for e in events]
            output,count = pulses.collapse_backed_glyph_pulses(events,MappingProxyType(words),MappingProxyType(positions))
            self.assertEqual((len(output),count),(5,8))
            expected_ids = [e.source_index for e in events if e.layer=='2' or e.source_index==99999]
            self.assertEqual([e.source_index for e in output],expected_ids)
            for caption in output:
                original = next(e for e in events if e.source_index==caption.source_index)
                if caption.source_index==99999:
                    self.assertIs(caption,original)
                else:
                    self.assertIsNot(caption,original)
                    self.assertEqual((caption.start_s,caption.end_s,caption.row,caption.lyric,caption.layer),(1.,4.,7,True,'0'))
                    self.assertEqual(engine.OVERRIDE_RE.sub('',caption.text),words[caption.source_index])
                    self.assertEqual(engine.get_pos(caption.text),positions[caption.source_index])
                    self.assertIs(caption.measurement,original.measurement)
            self.assertEqual(([vars(e) for e in events],words,positions),before)
            self.assertTrue(all(e.state is original for e,original in zip(events,states)))
            again,removed = pulses.collapse_backed_glyph_pulses(output,words,positions)
            self.assertIs(again,output)
            self.assertEqual(removed,0)

    def test_incomplete_and_competing_rows_remain_untouched(self):
        for options in ({'incomplete':True},{'competing':True}):
            with self.subTest(options=options):
                events,words,positions = backed_inputs(**options)
                before = deepcopy(([vars(e) for e in events],words,positions))
                output,count = pulses.collapse_backed_glyph_pulses(events,words,positions)
                self.assertIs(output,events)
                self.assertEqual(count,0)
                self.assertEqual(([vars(e) for e in events],words,positions),before)
        empty = []
        output,count = pulses.collapse_backed_glyph_pulses(empty,{}, {})
        self.assertIs(output,empty)
        self.assertEqual(count,0)

    def test_exact_metrics_supply_proved_paint_without_becoming_a_proof_prerequisite(self):
        events,words,positions = backed_inputs(sentinel=False)
        before = deepcopy(([vars(e) for e in events],words,positions))
        painted,count = pulses.collapse_backed_glyph_pulses(events,words,positions,self.metric)
        fallback,other_count = pulses.collapse_backed_glyph_pulses(events,words,positions)
        self.assertEqual((count,other_count),(8,8))
        self.assertTrue(all(0<e.state['3a']<255 for e in painted))
        self.assertTrue(all(e.state.get('3a',0)==0 for e in fallback))
        self.assertEqual(len({(e.state['1c'],e.state['3c'],e.state['3a']) for e in painted}),1)
        self.assertEqual([(e.source_index,e.start_s,e.end_s,engine.get_pos(e.text)) for e in painted],
                         [(e.source_index,e.start_s,e.end_s,engine.get_pos(e.text)) for e in fallback])
        self.assertEqual(([vars(e) for e in events],words,positions),before)

    def test_ordered_proposal_application_counts_actual_slots_and_rejects_shared_owners(self):
        events,_,_ = backed_inputs()
        kept,removed,sentinel = events[2],events[0],events[1]
        inputs = [kept,removed,sentinel,removed]
        before = deepcopy([vars(e) for e in inputs])
        successor = engine.replace_event(kept,layer='0')
        members = {kept.source_index,removed.source_index}
        output,count = pulses._apply_backed_pulse_proposals(inputs,[(members,[successor])])
        self.assertEqual(count,2)
        self.assertEqual(len(output),2)
        self.assertIs(output[0],successor)
        self.assertIs(output[1],sentinel)
        output,count = pulses._apply_backed_pulse_proposals(inputs,[(members,[successor]),(members,[successor])])
        self.assertIs(output,inputs)
        self.assertEqual(count,0)
        self.assertEqual([vars(e) for e in inputs],before)

    def test_caller_keeps_stage_handoff_and_source_fragment_accounting(self):
        events,words,positions = backed_inputs()
        before = deepcopy(([vars(e) for e in events],words,positions))
        captured = []
        def collect(*args,**kwargs):
            result = pulses.collapse_backed_glyph_pulses(*args,**kwargs)
            captured.append(result)
            return result
        with patch.object(engine,'collapse_backed_glyph_pulses',side_effect=collect), \
                patch.object(engine,'collapse_sliced_text_sequences',wraps=engine.collapse_sliced_text_sequences) as sliced:
            result = engine.remove_source_fragment_effects(events,[],words,positions,set())
        self.assertEqual(len(captured),1)
        self.assertIs(sliced.call_args.args[0],captured[0][0])
        self.assertEqual(result.removed_effects,captured[0][1])
        self.assertEqual(result.removed_effects,8)
        self.assertEqual(([vars(e) for e in events],words,positions),before)

    def test_cold_source_and_installed_processing_and_owned_uninstall(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); unrelated = root/'unrelated'; unrelated.mkdir()
            installer = load_installer(); target = root/'installed tools with spaces'
            _,installed = installer.install(ROOT,target,individual_launchers=False)
            fonts = installed/'fonts'; fonts.mkdir()
            installed_font = fonts/self.font.name
            shutil.copy2(self.font,installed_font)
            for tools,font in ((ROOT,self.font),(installed,installed_font)):
                child = subprocess.run([sys.executable,'-I','-c',
                    'import sys\nsys.path.insert(0,'+repr(str(tools))+')\nsys.argv=["backed-probe",'+repr(str(font))+']\n'+COLD_CODE],
                    cwd=unrelated,capture_output=True,text=True)
                self.assertEqual(child.returncode,0,child.stdout+child.stderr)
            user = installed/'_simplify_ass/user.py'; user.write_text('# user\n')
            installer.remove(target)
            self.assertEqual(user.read_text(),'# user\n')
            self.assertTrue(installed_font.exists())
            self.assertFalse((installed/'_simplify_ass/backed_glyph_pulses.py').exists())
            self.assertFalse(any((installed/'_simplify_ass').rglob('backed_glyph_pulses*.pyc')))


if __name__=='__main__':
    unittest.main()
