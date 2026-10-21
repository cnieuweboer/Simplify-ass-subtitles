"""Boundary matching ownership, strict shared fades and isolated module execution."""
import test_paths
from copy import deepcopy
from dataclasses import FrozenInstanceError
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
from _simplify_ass import boundary_glyphs as glyphs, effect_validation
from boundary_glyph_test_helpers import boundary_inputs
from check_windows_installer import ROOT,load_installer

COLD_CHECKS=r'''
from pathlib import Path
from _simplify_ass import boundary_glyphs as glyphs
assert 'simplify_ass' not in sys.modules
assert not any(n.split('.')[0] in {'PIL','fontTools','uharfbuzz'} for n in sys.modules)
assert glyphs.match_boundary_glyph_effects([],{}, {},None)==set()
metric=glyphs.FontMetrics([Path(sys.argv[1])]);assert metric.matching_face('Arial',0,False)
for phase,variant,expected in (('entrance','complete',3),('exit','complete',3),('both','complete',6),('entrance','partial',0),('entrance','gap',0),('entrance','ambiguous',0),('entrance','absorbed',2)):
    args=boundary_inputs(metric,phase=phase,variant=variant,unresolved=True)
    result=glyphs.match_boundary_glyph_effects(*args,metric)
    assert len(result)==expected,(phase,variant,result)
assert 'simplify_ass' not in sys.modules
import simplify_ass as engine
assert engine.match_boundary_glyph_effects is glyphs.match_boundary_glyph_effects
'''
COLD_CODE=Path(__file__).with_name('boundary_glyph_test_helpers.py').read_text()+COLD_CHECKS


class BoundaryGlyphModuleChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.metric=engine.FontMetrics([ROOT/'fonts'])
        assert cls.metric.matching_face('Arial',0,False),'Required exact Arial regular missing'

    def test_canonical_aliases_annotations_and_historical_record_lookup(self):
        names=('BoundaryGlyphPhase','BoundaryGlyphIndex','match_boundary_glyph_effects')
        for name in names:
            value=getattr(glyphs,name)
            self.assertIs(value,getattr(engine,name));get_type_hints(value)
            self.assertIs(pickle.loads(('csimplify_ass\n'+name+'\n.').encode()),value)
        self.assertIs(glyphs._parse_simple_source_fade,effect_validation._parse_simple_source_fade)
        self.assertIs(engine._parse_simple_source_fade,effect_validation._parse_simple_source_fade)
        self.assertIs(glyphs.Event,engine.Event)

    def test_borrowed_read_only_maps_and_unresolved_sources(self):
        events,visible,sources=boundary_inputs(self.metric,unresolved=True)
        before=deepcopy([vars(e) for e in events+list(sources.values())])
        states=[e.state for e in events+list(sources.values())]
        result=glyphs.match_boundary_glyph_effects(events,MappingProxyType(visible),MappingProxyType(sources),self.metric)
        self.assertEqual(len(result),3)
        self.assertEqual(before,[vars(e) for e in events+list(sources.values())])
        self.assertTrue(all(s is e.state for s,e in zip(states,events+list(sources.values()))))

    def test_complete_phases_and_independent_ownership(self):
        for phase,expected in (('entrance',3),('exit',3),('both',6)):
            for variant in ('complete','partial','ambiguous','gap','within'):
                if phase!='entrance' and variant=='within':continue
                with self.subTest(phase=phase,variant=variant):
                    args=boundary_inputs(self.metric,phase=phase,variant=variant)
                    result=glyphs.match_boundary_glyph_effects(*args,self.metric)
                    self.assertEqual(len(result),expected if variant in ('complete','within') else 0)
                    args[0].reverse()
                    self.assertEqual(result,glyphs.match_boundary_glyph_effects(*args,self.metric))

    def test_absorbed_entrance_can_prove_slot_without_becoming_removable(self):
        args=boundary_inputs(self.metric,variant='absorbed')
        result=glyphs.match_boundary_glyph_effects(*args,self.metric)
        self.assertEqual(len(result),2);self.assertNotIn(args[0][0].source_index,result)

    def test_frozen_records_keep_local_shallow_payloads(self):
        args=boundary_inputs(self.metric)
        index=glyphs._index_boundary_glyph_events(*args)
        self.assertRaises(FrozenInstanceError,setattr,index,'groups',{})
        captions=index.captions
        glyphs._index_boundary_glyph_captions(index)
        self.assertIs(index.captions,captions);self.assertTrue(captions)
        profile=glyphs._profile_boundary_glyph_source(next(iter(args[2].values())),1)
        self.assertRaises(FrozenInstanceError,setattr,profile,'state',{})
        self.assertIsInstance(profile.state,dict)

    def test_unavailable_metrics_and_failed_fit_refuse_without_state_leaks(self):
        args=boundary_inputs(self.metric,unresolved=True);before=deepcopy(args)
        for metric in (None,SimpleNamespace(available=False)):
            self.assertEqual(glyphs.match_boundary_glyph_effects(*args,metric),set())
        with patch.object(glyphs,'fit_fragment_anchor',return_value=None):
            self.assertEqual(glyphs.match_boundary_glyph_effects(*args,self.metric),set())
        with patch.object(glyphs,'fit_fragment_anchor',side_effect=RuntimeError('fit failed')):
            self.assertRaises(RuntimeError,glyphs.match_boundary_glyph_effects,*args,self.metric)
        self.assertEqual(args,before)
        self.assertEqual(len(glyphs.match_boundary_glyph_effects(*args,self.metric)),3)

    def test_shared_fade_parser_is_strict_borrowed_and_returns_fresh_values(self):
        parser=effect_validation._parse_simple_source_fade
        tokens=[('pos','(1,2)'),('fad','(100,200)')];before=deepcopy(tokens)
        a=parser(tokens);b=parser(tokens)
        self.assertEqual(a,[100.,200.]);self.assertIsNot(a,b);self.assertEqual(tokens,before)
        for values in ([],[('fade','(0,0,0,0,1,2,3)')],[('fad','(1,0)'),('fad','(1,0)')],
                       [('fad','(1,0)'),('fade','(0,0,0,0,1,2,3)')]):
            self.assertIsNone(parser(values))
        for value in ('(1)','(1,2,3)','(-1,0)','(nan,0)','(inf,0)','(bad,0)'):
            self.assertIsNone(parser([('fad',value)]))
        self.assertEqual(parser([('fad','(0,0)')]),[0.,0.])

    def test_caption_phase_producer_retains_its_own_core_policy(self):
        args=boundary_inputs(self.metric);source=args[2][args[0][-1].source_index]
        source=engine.replace_event(source,text=r'{\pos(500,100)\fad(100,200)}abc')
        before=deepcopy(vars(source));phase=engine._caption_phase_source(source)
        self.assertIs(phase.source,source);self.assertEqual(phase.fade,(100.,200.))
        self.assertEqual(phase.core,(1.6,3.3));self.assertEqual(vars(source),before)
        too_long=engine.replace_event(source,text=r'{\pos(500,100)\fad(3000,3000)}abc')
        self.assertEqual(engine._parse_simple_source_fade([('fad','(3000,3000)')]),[3000.,3000.])
        self.assertIsNone(engine._caption_phase_source(too_long))

    def test_installed_independent_supported_and_refused_processing(self):
        installer=load_installer()
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'tools with spaces';installer.install(ROOT,target,True)
            tool=target/'simplify-ass'
            self.assertTrue((tool/'_simplify_ass/boundary_glyphs.py').is_file())
            code='import sys\nsys.path.insert(0,'+repr(str(tool))+')\n'+COLD_CODE
            child=subprocess.run([sys.executable,'-I','-c',code,str(ROOT/'fonts')],cwd=tmp,capture_output=True,text=True)
            self.assertEqual(child.returncode,0,child.stderr)
            installer.remove(target)
            self.assertFalse(tool.exists())


if __name__=='__main__':unittest.main()
