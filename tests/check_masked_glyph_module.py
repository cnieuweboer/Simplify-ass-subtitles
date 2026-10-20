"""Canonical masked-glyph ownership, real mask proofs and isolated delivery."""
import test_paths
from copy import deepcopy
from dataclasses import FrozenInstanceError, fields
from pathlib import Path
import inspect
import pickle
import subprocess
import sys
import tempfile
from typing import get_type_hints
import unittest
from unittest.mock import patch

import simplify_ass as engine
from _simplify_ass import masked_glyphs as masks
from check_windows_installer import ROOT, load_installer
from masked_glyph_test_helpers import FAMILY, MASK, make_font, mask_inputs

RECORDS = ('MaskedGlyphContext', 'ParsedGlyphMask', 'MaskedGlyphModel', 'MaskedGlyphProof')
FUNCTIONS = ('_canonicalize_mask_contours', '_prepare_masked_glyphs', '_index_masked_texture_peers',
             '_parse_glyph_mask', '_match_masked_shadow_texture', '_masked_glyph_candidates',
             '_masked_placement_matches', '_same_masked_text_copy', '_masked_glyph_outline',
             '_prepare_masked_outline_model', '_fit_masked_outline_segment', '_match_masked_glyph_contours',
             '_match_masked_glyph_bases', '_remove_masked_texture_companions', '_apply_masked_glyph_proof',
             '_follow_proven_shadow_mask_phases', '_close_masked_glyph_fonts', 'remove_masked_glyph_effects')

COLD_CHECKS = r'''
from copy import deepcopy
from pathlib import Path
from _simplify_ass import masked_glyphs as m
assert 'simplify_ass' not in sys.modules
assert not any(n.split('.')[0] in {'PIL','fontTools','uharfbuzz'} for n in sys.modules)
events, visible = mask_inputs(identical=True)
before = deepcopy([vars(e) for e in events])
output, count = m.remove_masked_glyph_effects(events, visible)
assert count == 1 and output[0] is events[0] and output[-1] is events[-1]
assert [vars(e) for e in events] == before
assert 'simplify_ass' not in sys.modules
assert not any(n.split('.')[0] in {'PIL','fontTools','uharfbuzz'} for n in sys.modules)
metric = m.FontMetrics([Path(sys.argv[1]).parent])
assert metric.matching_face(FAMILY, 0, False) is not None
events, visible = mask_inputs()
before = deepcopy(([vars(e) for e in events], visible))
output, count = m.remove_masked_glyph_effects(events, visible, metric)
assert count == 1 and len(output) == 2 and output[-1] is events[-1]
caption = output[0]
assert caption is not events[0] and caption.source_index == events[0].source_index
assert caption.start_s == 1 and caption.end_s == 5 and caption.state['pos'] == (160.,100.)
assert caption.state['fn'] == FAMILY and caption.state['1c'] == '224466'
assert caption.state['1a'] == 0 and caption.state['bord'] == 2 and caption.state['3c'] == 'FFFFFF'
assert caption.row == 8 and caption.lyric and caption.measurement is events[0].measurement
assert ([vars(e) for e in events], visible) == before
again, count = m.remove_masked_glyph_effects(output, visible, metric)
assert count == 0 and all(a is b for a,b in zip(again,output))
assert metric.matching_face(FAMILY,0,False) is not None
import simplify_ass as engine
assert engine.remove_masked_glyph_effects is m.remove_masked_glyph_effects
assert engine.MaskedGlyphContext is m.MaskedGlyphContext
assert Path(m.__file__).resolve() == Path(engine.__file__).resolve().parent/'_simplify_ass/masked_glyphs.py'
import py_compile
py_compile.compile(m.__file__, doraise=True)
'''
COLD_CODE = Path(__file__).with_name('masked_glyph_test_helpers.py').read_text() + COLD_CHECKS


class MaskedGlyphModuleChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.font = self.folder/'MaskModule.ttf'; make_font(self.font)
        self.metric = engine.FontMetrics([self.folder])

    def test_canonical_aliases_annotations_defaults_and_historical_root_lookup(self):
        for name in RECORDS + FUNCTIONS:
            value = getattr(masks,name)
            self.assertIs(getattr(engine,name),value)
            get_type_hints(value)
            self.assertIs(pickle.loads(('csimplify_ass\n'+name+'\n.').encode()),value)
            self.assertIs(pickle.loads(pickle.dumps(value)),value)
        self.assertIs(masks.Event,engine.Event)
        self.assertIs(masks.FontMetrics,engine.FontMetrics)
        self.assertEqual(masks.remove_masked_glyph_effects.__defaults__,(None,None))
        self.assertEqual(list(inspect.signature(masks.remove_masked_glyph_effects).parameters),
                         ['events','visible_map','metric','animated_sources'])

    def test_four_records_remain_shallow_frozen_with_independent_default_buffers(self):
        events,visible = mask_inputs()
        context = masks._prepare_masked_glyphs(events,visible,self.metric,{events[1].source_index})
        parsed = masks._parse_glyph_mask(events[1])
        outline = ([],[],1000,600,((800,200),))
        points = [(1.,2.)]
        model = masks.MaskedGlyphModel(outline,points,(0.,0.),1.,.04)
        proof = masks.MaskedGlyphProof()
        self.assertIs(context.visible,visible)
        self.assertIs(context.metric,self.metric)
        self.assertIs(model.points,points)
        self.assertIs(model.outline,outline)
        self.assertIsNot(context.fonts,masks._prepare_masked_glyphs(events,visible,self.metric,None).fonts)
        self.assertIsNot(proof.covered,masks.MaskedGlyphProof().covered)
        for record in (context,parsed,model,proof):
            self.assertTrue(type(record).__dataclass_params__.frozen)
            name = fields(record)[0].name
            with self.assertRaises(FrozenInstanceError):
                setattr(record,name,getattr(record,name))
        proof.covered.add(1)
        self.assertEqual(proof.covered,{1})

    def test_exact_font_mask_retains_caption_paint_geometry_timing_and_input_identity(self):
        events,visible = mask_inputs(); animated = {events[1].source_index}
        before = deepcopy(([vars(e) for e in events],visible,animated))
        original_states = [e.state for e in events]
        output,count = masks.remove_masked_glyph_effects(events,visible,self.metric,animated)
        self.assertEqual((count,len(output)),(1,2))
        caption = output[0]
        self.assertIsNot(caption,events[0]); self.assertIs(output[-1],events[-1])
        self.assertEqual(engine.OVERRIDE_RE.sub('',caption.text),'A')
        self.assertEqual((caption.source_index,caption.layer,caption.start_s,caption.end_s),
                         (events[0].source_index,'0',1.,5.))
        self.assertEqual((caption.state['fn'],caption.state['1c'],caption.state['1a'],caption.state['bord']),
                         (FAMILY,'224466',0,2))
        self.assertEqual((engine.get_pos(caption.text),caption.row,caption.lyric),((160.,100.),8,True))
        self.assertIs(caption.measurement,events[0].measurement)
        self.assertEqual(([vars(e) for e in events],visible,animated),before)
        self.assertTrue(all(e.state is state for e,state in zip(events,original_states)))

    def test_original_list_order_and_source_id_count_survive_repeated_mask_slots(self):
        events,visible = mask_inputs(); base,carrier,unrelated = events
        output,count = masks.remove_masked_glyph_effects([carrier,unrelated,base,carrier],visible,self.metric)
        self.assertEqual((count,len(output)),(1,2))
        self.assertIs(output[0],unrelated)
        self.assertEqual(output[1].source_index,base.source_index)
        self.assertEqual(engine.OVERRIDE_RE.sub('',output[1].text),'A')

    def test_uncertain_or_unavailable_mask_proofs_preserve_original_objects(self):
        events,visible = mask_inputs()
        variants = [(events,None),
                    ([events[0],engine.replace_event(events[1],text=events[1].text.replace('clip(','iclip(')),events[2]],self.metric),
                    (mask_inputs(mask='m 148 112 l 164 112 164 84')[0],self.metric),
                    ([engine.replace_event(events[0],start='0:00:02.00',start_s=2.),*events[1:]],self.metric)]
        for peers,metric in variants:
            output,count = masks.remove_masked_glyph_effects(peers,visible,metric)
            self.assertEqual(count,0)
            self.assertTrue(all(a is b for a,b in zip(output,peers)))

    def test_exact_font_cache_is_pass_local_and_reuses_only_its_own_initialized_handle(self):
        events,visible = mask_inputs()
        a = masks._prepare_masked_glyphs(events,visible,self.metric,None)
        b = masks._prepare_masked_glyphs(events,visible,self.metric,None)
        with patch.object(self.metric,'open_face',wraps=self.metric.open_face) as opened:
            try:
                first = masks._masked_glyph_outline(a,events[0])
                self.assertIsNotNone(first)
                self.assertIs(masks._masked_glyph_outline(a,events[0]),first)
                self.assertEqual(opened.call_count,1)
                self.assertFalse(b.fonts); self.assertFalse(b.outlines)
                self.assertIsNotNone(masks._masked_glyph_outline(b,events[0]))
                self.assertEqual(opened.call_count,2)
            finally:
                masks._close_masked_glyph_fonts(a); masks._close_masked_glyph_fonts(b)

    def test_repeated_calls_do_not_share_successors_and_second_pass_is_inert(self):
        events,visible = mask_inputs()
        first,count = masks.remove_masked_glyph_effects(events,visible,self.metric)
        other,again = masks.remove_masked_glyph_effects(events,visible,self.metric)
        self.assertEqual((count,again),(1,1))
        self.assertEqual(first,other); self.assertIsNot(first[0],other[0])
        output,count = masks.remove_masked_glyph_effects(first,visible,self.metric)
        self.assertEqual(count,0); self.assertTrue(all(a is b for a,b in zip(output,first)))
        self.assertEqual(masks.remove_masked_glyph_effects([],{}),([],0))

    def test_cold_source_installed_exact_font_processing_and_owned_uninstall(self):
        unrelated = self.folder/'unrelated'; unrelated.mkdir()
        owner = load_installer(); target = self.folder/'installed tools with spaces'
        _,installed = owner.install(ROOT,target,individual_launchers=False)
        for tools in (ROOT,installed):
            child = subprocess.run([sys.executable,'-I','-c',
                'import sys\nsys.path.insert(0,'+repr(str(tools))+')\n'+COLD_CODE,str(self.font)],
                cwd=unrelated,capture_output=True,text=True)
            self.assertEqual(child.returncode,0,child.stdout+child.stderr)
        user = installed/'_simplify_ass/user.py'; user.write_text('# user\n')
        owner.remove(target)
        self.assertEqual(user.read_text(),'# user\n')
        self.assertFalse((installed/'_simplify_ass/masked_glyphs.py').exists())
        self.assertFalse(any((installed/'_simplify_ass').rglob('masked_glyphs*.pyc')))


if __name__ == '__main__':
    unittest.main()
