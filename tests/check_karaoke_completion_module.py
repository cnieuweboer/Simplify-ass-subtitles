"""Karaoke completion ownership, canonical aliases and installed proof routes."""
import test_paths
from copy import deepcopy
from dataclasses import FrozenInstanceError
import inspect
from pathlib import Path
import pickle
import subprocess
import sys
import tempfile
from types import MappingProxyType
from typing import get_type_hints
import unittest
from unittest.mock import patch

import simplify_ass as engine
from _simplify_ass import karaoke_completion as completion
from check_windows_installer import ROOT, load_installer
from karaoke_completion_test_helpers import AFTER, BEFORE, OUTLINE, karaoke_inputs

RECORDS = ('KaraokeCompletionSourcePhase', 'KaraokeCompletionProfile')
FUNCTIONS = (
    '_karaoke_completion_identity', '_karaoke_completion_cue_start',
    '_karaoke_completion_paint', '_index_retained_karaoke_completion_rows',
    '_select_karaoke_completion_rows', '_index_karaoke_completion_sources',
    '_karaoke_completion_source_phases', '_profile_karaoke_completion_source_phase',
    '_prove_karaoke_completion_transition', '_match_karaoke_completion_profiles',
    '_prove_ordered_karaoke_completion_sweep', '_replace_karaoke_completion_paint',
    'normalize_karaoke_completion_paint',
)

COLD_CHECKS = r'''
from copy import deepcopy
from pathlib import Path
from _simplify_ass import karaoke_completion as c
assert 'simplify_ass' not in sys.modules
assert not any(n.split('.')[0] in {'PIL','fontTools','uharfbuzz'} for n in sys.modules)
for incomplete in (False, True):
    events, visible, sources = karaoke_inputs(incomplete=incomplete, reverse=True)
    before = deepcopy(([vars(e) for e in events], visible, sources))
    result = c.normalize_karaoke_completion_paint(events, visible, sources)
    assert len(result)==len(events)
    for original,caption in zip(events,result):
        if original.source_index==99999 or incomplete:
            assert caption is original
        else:
            assert caption is not original
            assert caption.state['1c']==AFTER and caption.state['3c']==OUTLINE
            assert caption.state['bord']==1.5
            assert (caption.start_s,caption.end_s,caption.row,caption.lyric)==(1.,5.,7,True)
    assert ([vars(e) for e in events], visible, sources)==before
    again = c.normalize_karaoke_completion_paint(result,visible,sources)
    assert [e.state for e in again]==[e.state for e in result]
events,visible,sources=karaoke_inputs(sentinel=False)
profiles={e.source_index:c.KaraokeCompletionProfile(('before',),('after',),
          2+i*.2,2.1+i*.2,{'1c':AFTER,'3c':OUTLINE},True) for i,e in enumerate(events)}
result=c.normalize_karaoke_completion_paint(events,visible,{},outline_profiles=profiles)
assert all(e.state['1c']==AFTER and e.state['3c']==OUTLINE for e in result)
assert 'simplify_ass' not in sys.modules
assert not any(n.split('.')[0] in {'PIL','fontTools','uharfbuzz'} for n in sys.modules)
import simplify_ass as engine
assert engine.normalize_karaoke_completion_paint is c.normalize_karaoke_completion_paint
assert engine.KaraokeCompletionProfile is c.KaraokeCompletionProfile
assert Path(c.__file__).resolve()==Path(engine.__file__).resolve().parent/'_simplify_ass/karaoke_completion.py'
import py_compile
py_compile.compile(c.__file__,doraise=True)
'''
COLD_CODE = Path(__file__).with_name('karaoke_completion_test_helpers.py').read_text() + COLD_CHECKS


class KaraokeCompletionModuleChecks(unittest.TestCase):
    def test_canonical_aliases_annotations_and_historical_root_lookup(self):
        for name in RECORDS + FUNCTIONS:
            value = getattr(completion, name)
            self.assertIs(getattr(engine, name), value)
            get_type_hints(value)
            self.assertIs(pickle.loads(('csimplify_ass\n'+name+'\n.').encode()), value)
            self.assertIs(pickle.loads(pickle.dumps(value)), value)
        self.assertIs(completion.Event, engine.Event)
        parameter = inspect.signature(completion.normalize_karaoke_completion_paint).parameters['outline_profiles']
        self.assertIsNone(parameter.default)
        self.assertEqual(parameter.kind, inspect.Parameter.KEYWORD_ONLY)

    def test_shallow_frozen_profiles_borrow_producer_paint(self):
        final = {'1c':AFTER}
        profile = completion.KaraokeCompletionProfile(('before',),('after',),2,3,final,True)
        hold = (('before',),1,2)
        phase = completion.KaraokeCompletionSourcePhase(hold,None)
        self.assertIs(profile.final, final)
        self.assertIs(phase.hold, hold)
        for value, name in ((profile,'final'),(phase,'hold')):
            with self.assertRaises(FrozenInstanceError):
                setattr(value,name,None)
        final['3c'] = OUTLINE
        self.assertEqual(profile.final['3c'],OUTLINE)

    def test_source_proof_preserves_order_metadata_inputs_and_untouched_identity(self):
        for reverse in (False,True):
            events, visible, sources = karaoke_inputs(reverse=reverse)
            before = deepcopy(([vars(e) for e in events],visible,sources))
            states = [e.state for e in events]
            output = completion.normalize_karaoke_completion_paint(
                events,MappingProxyType(visible),MappingProxyType(sources))
            self.assertEqual(len(output),len(events))
            for original, caption in zip(events,output):
                self.assertEqual(caption.source_index,original.source_index)
                if original.source_index==99999:
                    self.assertIs(caption,original)
                    continue
                self.assertIsNot(caption,original)
                self.assertEqual((caption.state['1c'],caption.state['3c'],caption.state['bord']),
                                 (AFTER,OUTLINE,1.5))
                self.assertEqual(caption.fields()[:9],original.fields()[:9])
                self.assertEqual((caption.start_s,caption.end_s,caption.row,caption.lyric),
                                 (1.,5.,7,True))
                self.assertEqual(engine.get_pos(caption.text),engine.get_pos(original.text))
                self.assertIs(caption.measurement,original.measurement)
            self.assertEqual(([vars(e) for e in events],visible,sources),before)
            self.assertTrue(all(e.state is state for e,state in zip(events,states)))

    def test_missing_coverage_refuses_the_entire_row_without_claiming_sources(self):
        events,visible,sources = karaoke_inputs(incomplete=True)
        before = deepcopy(([vars(e) for e in events],visible,sources))
        output = completion.normalize_karaoke_completion_paint(events,visible,sources)
        self.assertIsNot(output,events)
        self.assertTrue(all(a is b for a,b in zip(output,events)))
        self.assertEqual(([vars(e) for e in events],visible,sources),before)
        empty = []
        self.assertIs(completion.normalize_karaoke_completion_paint(empty,{},{}),empty)
        sentinel = [events[1]]
        self.assertIs(completion.normalize_karaoke_completion_paint(sentinel,visible,sources),sentinel)

    def test_outline_profiles_are_borrowed_and_do_not_rebuild_discarded_sources(self):
        events,visible,_ = karaoke_inputs(sentinel=False)
        profiles = {e.source_index:completion.KaraokeCompletionProfile(
            ('before',),('palette',),2+i*.2,2.1+i*.2,
            {'1c':AFTER,'3c':OUTLINE},True) for i,e in enumerate(events)}
        before = deepcopy(profiles)
        with patch.object(completion,'_index_karaoke_completion_sources',side_effect=AssertionError('source proof bypassed')):
            output = completion.normalize_karaoke_completion_paint(events,visible,{},
                outline_profiles=MappingProxyType(profiles))
            self.assertTrue(all(e.state['1c']==AFTER and e.state['3c']==OUTLINE for e in output))
            for supplied in ({},dict(list(profiles.items())[:-1])):
                refused = completion.normalize_karaoke_completion_paint(events,visible,{},outline_profiles=supplied)
                self.assertTrue(all(a is b for a,b in zip(refused,events)))
        self.assertEqual(profiles,before)

    def test_invocations_have_independent_buffers_and_repeat_resolved_paint_is_stable(self):
        events,visible,sources = karaoke_inputs()
        first = completion.normalize_karaoke_completion_paint(events,visible,sources)
        second = completion.normalize_karaoke_completion_paint(events,visible,sources)
        self.assertEqual(first,second)
        self.assertIsNot(first,second)
        self.assertIsNot(first[0],second[0])
        again = completion.normalize_karaoke_completion_paint(first,visible,sources)
        self.assertEqual([e.state for e in first],[e.state for e in again])
        self.assertTrue(all(e.state['1c']==BEFORE for e in events if e.source_index!=99999))
        first.pop()
        self.assertEqual(len(second),len(events))

    def test_cold_source_and_installed_proof_routes_and_owned_uninstall(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            unrelated = root/'unrelated'; unrelated.mkdir()
            installer = load_installer()
            target = root/'installed tools with spaces'
            _,installed = installer.install(ROOT,target,individual_launchers=False)
            for tools in (ROOT,installed):
                child = subprocess.run([sys.executable,'-I','-c',
                    'import sys\nsys.path.insert(0,'+repr(str(tools))+')\n'+COLD_CODE],
                    cwd=unrelated,capture_output=True,text=True)
                self.assertEqual(child.returncode,0,child.stdout+child.stderr)
            user = installed/'_simplify_ass/user.py'; user.write_text('# user\n')
            installer.remove(target)
            self.assertEqual(user.read_text(),'# user\n')
            self.assertFalse((installed/'_simplify_ass/karaoke_completion.py').exists())
            self.assertFalse(any((installed/'_simplify_ass').rglob('karaoke_completion*.pyc')))


if __name__=='__main__':
    unittest.main()
