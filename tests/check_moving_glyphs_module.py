"""Movement-chain ownership, shared source reads and installed delivery."""
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
from _simplify_ass import moving_glyphs as movement
from _simplify_ass import event_operations, effect_validation
from check_windows_installer import ROOT,load_installer
from moving_glyph_test_helpers import FAMILY,moving_inputs

RECORDS = ('MovingGlyphContext','MovingGlyphChain')
FUNCTIONS = (
    '_moving_glyph_source_families','_moving_glyph_geometry','_moving_glyph_paint',
    '_index_moving_glyph_sources','_index_retained_moving_glyphs','_retained_moving_glyph',
    '_group_moving_glyph_sequences','_moving_glyph_group_fits','_matching_moving_glyph_fades',
    '_prove_moving_glyph_chain','_match_moving_glyph_prefix','_collect_moving_glyph_overlays',
    '_match_moving_glyph_exit','_render_moving_glyph_caption','_propose_moving_glyph_sequence',
    '_apply_moving_glyph_proposals','collapse_moving_glyph_sequences',
)

COLD_CHECKS = r'''
from copy import deepcopy
from pathlib import Path
from _simplify_ass import moving_glyphs as m
assert 'simplify_ass' not in sys.modules
assert not any(n.split('.')[0] in {'PIL','fontTools','uharfbuzz'} for n in sys.modules)
for incomplete in (False,True):
    events,words,sources=moving_inputs(incomplete=incomplete,reverse=True)
    before=deepcopy(([vars(e) for e in events],words,{k:vars(e) for k,e in sources.items()}))
    result,count=m.collapse_moving_glyph_sequences(events,words,sources,None)
    assert count==(0 if incomplete else 2) and len(result)==len(events)-count
    assert any(e is original for e in result for original in events if original.source_index==99999)
    assert ([vars(e) for e in events],words,{k:vars(e) for k,e in sources.items()})==before
    again,removed=m.collapse_moving_glyph_sequences(result,words,sources,None)
    assert again==result and removed==0
assert 'simplify_ass' not in sys.modules
assert not any(n.split('.')[0] in {'PIL','fontTools','uharfbuzz'} for n in sys.modules)
font_path=Path(sys.argv[1]);metric=m.FontMetrics([font_path.parent]);face=metric.matching_face(FAMILY,0,False)
assert face is not None and Path(face.path).resolve()==font_path.resolve()
events,words,sources=moving_inputs(glyphs=True,metric=metric,sentinel=False)
before=deepcopy(([vars(e) for e in events],words,{k:vars(e) for k,e in sources.items()}))
result,count=m.collapse_moving_glyph_sequences(events,words,sources,metric)
assert count==5 and len(result)==1 and (result[0].start_s,result[0].end_s)==(1.,5.)
assert ([vars(e) for e in events],words,{k:vars(e) for k,e in sources.items()})==before
assert 'simplify_ass' not in sys.modules
import simplify_ass as engine
assert engine.collapse_moving_glyph_sequences is m.collapse_moving_glyph_sequences
assert engine.MovingGlyphContext is m.MovingGlyphContext
assert engine.literal_font_spans is m.literal_font_spans
assert engine.opaque_text_effect_state is m.opaque_text_effect_state
assert Path(m.__file__).resolve()==Path(engine.__file__).resolve().parent/'_simplify_ass/moving_glyphs.py'
import py_compile
py_compile.compile(m.__file__,doraise=True)
'''
COLD_CODE = Path(__file__).with_name('moving_glyph_test_helpers.py').read_text()+COLD_CHECKS


class MovingGlyphModuleChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.metric = engine.FontMetrics([ROOT/'fonts'])
        cls.face = cls.metric.matching_face(FAMILY,0,False)
        assert cls.face is not None,'Required exact Arial regular missing'
        cls.font = Path(cls.face.path)

    def test_canonical_aliases_annotations_and_historical_root_lookup(self):
        for name in RECORDS+FUNCTIONS:
            value = getattr(movement,name)
            self.assertIs(value,getattr(engine,name))
            get_type_hints(value)
            self.assertIs(pickle.loads(('csimplify_ass\n'+name+'\n.').encode()),value)
            self.assertIs(pickle.loads(pickle.dumps(value)),value)
        self.assertIs(movement.Event,engine.Event)
        self.assertIs(movement.FontMetrics,engine.FontMetrics)
        self.assertIs(movement.literal_font_spans,event_operations.literal_font_spans)
        self.assertIs(movement.opaque_text_effect_state,effect_validation.opaque_text_effect_state)
        self.assertEqual(tuple(inspect.signature(movement.collapse_moving_glyph_sequences).parameters),
                         ('events','visible_map','source_events','metric'))

    def test_shallow_frozen_records_borrow_events_and_keep_indexes_local(self):
        events,words,sources = moving_inputs(sentinel=False)
        families = movement._moving_glyph_source_families(sources)
        static,moves,fades = movement._index_moving_glyph_sources(sources,families)
        other = movement._index_moving_glyph_sources(sources,families)
        current = movement._index_retained_moving_glyphs(events,words)
        groups,by_start = movement._group_moving_glyph_sequences(moves)
        context = movement.MovingGlyphContext(static,fades,current,by_start,None)
        self.assertIs(context.static,static)
        self.assertTrue(all(a is not b for a,b in zip((static,moves,fades),other)))
        proof = movement._prove_moving_glyph_chain(context,groups[0])
        self.assertIsNotNone(proof)
        self.assertIs(proof.before,events[0])
        self.assertIs(proof.after,events[-1])
        self.assertIsNot(proof.parent,events[0])
        self.assertIs(proof.parent.defaults,events[0].defaults)
        self.assertIsNot(proof.parent.state,events[0].state)
        for record,name in ((context,'static'),(proof,'groups')):
            with self.assertRaises(FrozenInstanceError):setattr(record,name,None)
        context.static.clear()
        self.assertTrue(other[0])
        proof.groups.clear()
        self.assertTrue(by_start)

    def test_supported_chains_preserve_paint_timing_flags_inputs_and_untouched_identity(self):
        for reverse in (False,True):
            for inline in (False,True):
                events,words,sources = moving_inputs(reverse=reverse,inline=inline)
                before = deepcopy(([vars(e) for e in events],words,{k:vars(e) for k,e in sources.items()}))
                states = [e.state for e in events]
                result,count = movement.collapse_moving_glyph_sequences(events,MappingProxyType(words),MappingProxyType(sources),None)
                self.assertEqual((len(result),count),(2,2))
                self.assertEqual([e.source_index for e in result],sorted(e.source_index for e in result))
                caption,other = result
                self.assertEqual((caption.start_s,caption.end_s,caption.row,caption.lyric,caption.layer),(1.,5.,7,True,'2'))
                self.assertEqual(engine.OVERRIDE_RE.sub('',caption.text),'ABCD')
                self.assertEqual(engine.get_pos(caption.text),(320.,100.))
                self.assertEqual((caption.state['1c'],caption.state['3c']),('DDEEFF','112233'))
                self.assertIs(other,sources[99999])
                self.assertIs(caption.measurement,sources[caption.source_index].measurement)
                self.assertEqual(([vars(e) for e in events],words,{k:vars(e) for k,e in sources.items()}),before)
                self.assertTrue(all(e.state is state for e,state in zip(events,states)))
                again,removed = movement.collapse_moving_glyph_sequences(result,words,sources,None)
                self.assertEqual(again,result)
                self.assertEqual(removed,0)

    def test_incomplete_and_competing_chains_return_original_list(self):
        for options in ({'incomplete':True},{'competing':True}):
            events,words,sources = moving_inputs(**options)
            before = deepcopy([vars(e) for e in events])
            output,count = movement.collapse_moving_glyph_sequences(events,words,sources,self.metric)
            self.assertIs(output,events)
            self.assertEqual(count,0)
            self.assertEqual([vars(e) for e in events],before)
        empty = []
        self.assertIs(movement.collapse_moving_glyph_sequences(empty,{}, {},None)[0],empty)

    def test_exact_glyph_placement_and_optional_metric_refusal(self):
        events,words,sources = moving_inputs(glyphs=True,metric=self.metric)
        before = deepcopy([vars(e) for e in events])
        output,count = movement.collapse_moving_glyph_sequences(events,words,sources,self.metric)
        self.assertEqual((len(output),count),(2,5))
        self.assertEqual((output[0].start_s,output[0].end_s),(1.,5.))
        for metric in (None,type('Unavailable',(),{'available':False})()):
            result,removed = movement.collapse_moving_glyph_sequences(events,words,sources,metric)
            self.assertIs(result,events)
            self.assertEqual(removed,0)
        with patch.object(movement,'fit_fragment_anchor',return_value=None) as fit:
            result,removed = movement.collapse_moving_glyph_sequences(events,words,sources,self.metric)
        self.assertTrue(fit.called)
        self.assertIs(result,events)
        self.assertEqual(removed,0)
        self.assertEqual([vars(e) for e in events],before)

    def test_proposals_reject_competing_owners_and_count_actual_list_slots(self):
        events,_,_ = moving_inputs(sentinel=False)
        parent,phase,terminal = events
        successor = engine.replace_event(parent,end=terminal.end,end_s=terminal.end_s)
        ids = {parent.source_index,phase.source_index,terminal.source_index}
        inputs = [terminal,phase,parent,phase]
        output,count = movement._apply_moving_glyph_proposals(inputs,[(ids,successor)])
        self.assertEqual(count,3)
        self.assertEqual(len(output),1)
        self.assertIs(output[0],successor)
        output,count = movement._apply_moving_glyph_proposals(inputs,[(ids,successor),(ids,successor)])
        self.assertIs(output,inputs)
        self.assertEqual(count,0)

    def test_caller_retains_normalization_exact_pass_and_aggregate_reporting(self):
        events,words,sources = moving_inputs()
        context = engine.TextEffectSequenceContext(words,{},set(),True,sources,self.metric)
        trace = []
        def collapse(*args):
            trace.append('movement');return movement.collapse_moving_glyph_sequences(*args)
        def normalize(result,*args):
            trace.append('karaoke');return result
        def exact(result,*args,**kwargs):
            trace.append('exact');self.assertFalse(args[3]);return result,3
        with patch.object(engine,'collapse_moving_glyph_sequences',side_effect=collapse) as moving, \
                patch.object(engine,'normalize_karaoke_completion_paint',side_effect=normalize), \
                patch.object(engine,'flatten_text_effect_sequences',side_effect=exact):
            output,count = engine._finish_text_effect_sequences(context,events,4)
        self.assertEqual(trace,['movement','karaoke','exact'])
        self.assertEqual((len(output),count),(2,9))
        self.assertIs(moving.call_args.args[2],sources)
        self.assertIs(moving.call_args.args[3],self.metric)

    def test_cold_source_installed_processing_and_owned_uninstall(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);unrelated=root/'unrelated';unrelated.mkdir()
            installer=load_installer();target=root/'installed tools with spaces'
            _,installed=installer.install(ROOT,target,individual_launchers=False)
            fonts=installed/'fonts';fonts.mkdir();installed_font=fonts/self.font.name
            shutil.copy2(self.font,installed_font)
            for tools,font in ((ROOT,self.font),(installed,installed_font)):
                child=subprocess.run([sys.executable,'-I','-c','import sys\nsys.path.insert(0,'+repr(str(tools))+')\nsys.argv=["moving-probe",'+repr(str(font))+']\n'+COLD_CODE],cwd=unrelated,capture_output=True,text=True)
                self.assertEqual(child.returncode,0,child.stdout+child.stderr)
            user=installed/'_simplify_ass/user.py';user.write_text('# user\n')
            installer.remove(target)
            self.assertEqual(user.read_text(),'# user\n')
            self.assertTrue(installed_font.exists())
            self.assertFalse((installed/'_simplify_ass/moving_glyphs.py').exists())
            self.assertFalse(any((installed/'_simplify_ass').rglob('moving_glyphs*.pyc')))


if __name__=='__main__':
    unittest.main()
