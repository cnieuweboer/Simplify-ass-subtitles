"""Reveal ownership, complete coverage and cold installed-module delivery."""
import test_paths
from copy import deepcopy
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import MappingProxyType
from typing import get_type_hints
import pickle
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import simplify_ass as engine
from _simplify_ass import progressive_reveals as reveal, text_visibility
from check_windows_installer import ROOT,load_installer
from progressive_reveal_test_helpers import reveal_inputs

RECORDS=('ProgressiveRevealPrefix','ProgressiveRevealBand','ProgressiveRevealCaption')
FUNCTIONS=(
    '_eligible_progressive_reveal_families','_parse_progressive_reveal_prefix',
    '_profile_progressive_reveal_event','_index_progressive_reveal_families',
    '_build_progressive_reveal_chains','_progressive_reveal_finishing_holds',
    '_progressive_reveal_strip_band','_progressive_reveal_strips_cover_band',
    '_progressive_reveal_strip_coverage','_select_progressive_reveal_caption',
    '_progressive_reveal_intervals','_record_progressive_reveal_replacements',
    'collapse_progressive_text_reveals',
)
COLD_CHECKS=r'''
import sys
from types import MappingProxyType
from _simplify_ass import progressive_reveals as reveal, text_visibility
assert 'simplify_ass' not in sys.modules
for options in ({},{'strips':True},{'strips':True,'incomplete':True},{'gaps':True},{'tags':r'\1a&H40&\3a&H40&'}):
    events,visible=reveal_inputs(**options)
    result=reveal.collapse_progressive_text_reveals(events,MappingProxyType(visible))
    expected=0 if options.get('gaps') or options.get('incomplete') else 18 if options.get('strips') else 3
    assert result.removed_count==expected
    assert isinstance(result,text_visibility.TextVisibilityResult)
    assert 999999 not in result.visibility_updates
    assert result.events[-1] is events[-1]
assert 'simplify_ass' not in sys.modules
assert not any(n.split('.')[0] in {'PIL','fontTools','uharfbuzz'} for n in sys.modules)
import simplify_ass as engine
assert engine.collapse_progressive_text_reveals is reveal.collapse_progressive_text_reveals
assert engine.TextVisibilityResult is reveal.TextVisibilityResult is text_visibility.TextVisibilityResult
'''
COLD_CODE=Path(__file__).with_name('progressive_reveal_test_helpers.py').read_text()+COLD_CHECKS


class ProgressiveRevealModuleChecks(unittest.TestCase):
    def test_canonical_aliases_annotations_and_historical_root_pickle(self):
        for name in RECORDS+FUNCTIONS:
            value=getattr(reveal,name)
            self.assertIs(value,getattr(engine,name));get_type_hints(value)
            self.assertIs(pickle.loads(('csimplify_ass\n'+name+'\n.').encode()),value)
            self.assertIs(pickle.loads(pickle.dumps(value)),value)
        self.assertIs(engine.TextVisibilityResult,text_visibility.TextVisibilityResult)
        self.assertIs(reveal.TextVisibilityResult,text_visibility.TextVisibilityResult)
        self.assertIs(get_type_hints(engine.collapse_full_lyric_copies)['return'],text_visibility.TextVisibilityResult)
        self.assertIs(pickle.loads(b'csimplify_ass\nTextVisibilityResult\n.'),text_visibility.TextVisibilityResult)

    def test_shared_result_and_reveal_records_preserve_shallow_ownership(self):
        events,visible=reveal_inputs();updates={}
        result=text_visibility.TextVisibilityResult(events,0,updates)
        self.assertIs(result.events,events);self.assertIs(result.visibility_updates,updates)
        foreground={'1c':'ABCDEF'}
        prefix=reveal.ProgressiveRevealPrefix('abcd','a',(),foreground)
        caption=reveal.ProgressiveRevealCaption(events[0],'body')
        band=reveal.ProgressiveRevealBand(40,80,100)
        self.assertIs(prefix.foreground,foreground);self.assertIs(caption.event,events[0])
        for record,field in ((result,'events'),(prefix,'foreground'),(caption,'body'),(band,'top')):
            with self.assertRaises(FrozenInstanceError):setattr(record,field,None)
        foreground['1c']='123456';self.assertEqual(prefix.foreground['1c'],'123456')
        first=engine.replace_event(events[-2],source_index=10000)
        second=engine.replace_event(first,source_index=10001)
        full=engine.collapse_full_lyric_copies([first,second],{10000:'abcd',10001:'abcd'})
        self.assertIs(type(full),type(result));self.assertEqual(full.removed_count,1)

    def test_complete_reveals_keep_paint_timing_pose_and_borrowed_inputs(self):
        for strips in (False,True):
            for reverse in (False,True):
                events,visible=reveal_inputs(strips=strips,tags=r'\1c&HABCDEF&\3c&H123456&\1a&H40&\3a&H40&')
                if reverse:events.reverse()
                before=deepcopy(([vars(e) for e in events],visible));states=[e.state for e in events]
                result=reveal.collapse_progressive_text_reveals(events,MappingProxyType(visible))
                self.assertEqual(result.removed_count,18 if strips else 3)
                caption=next(e for e in result.events if e.source_index!=99999)
                self.assertEqual((caption.start_s,caption.end_s),(1.,2.))
                self.assertEqual(engine.get_pos(caption.text),(500.,100.))
                self.assertEqual(engine.OVERRIDE_RE.sub('',caption.text),'abcd')
                self.assertEqual((caption.state['1c'],caption.state['3c'],caption.state['1a'],caption.state['3a']),('ABCDEF','123456',64,64))
                self.assertIs(caption.measurement,events[0].measurement)
                self.assertTrue(any(e is next(x for x in events if x.source_index==99999) for e in result.events))
                self.assertEqual(([vars(e) for e in events],visible),before)
                self.assertTrue(all(e.state is state for e,state in zip(events,states)))
                self.assertEqual(result.visibility_updates,{caption.source_index:'abcd'})
                again=reveal.collapse_progressive_text_reveals(result.events,{**visible,**result.visibility_updates})
                self.assertEqual(again.events,result.events);self.assertFalse(again.visibility_updates)

    def test_gap_updates_and_refused_coverage_keep_distinct_contracts(self):
        events,visible=reveal_inputs(gaps=True,sentinel=False)
        result=reveal.collapse_progressive_text_reveals(events,MappingProxyType(visible))
        self.assertEqual(result.removed_count,0);self.assertEqual(len(result.visibility_updates),4)
        self.assertEqual([(e.start_s,e.end_s) for e in result.events],[(1,1.1),(1.12,1.22),(1.24,1.34),(1.36,2.06)])
        self.assertTrue(all(engine.OVERRIDE_RE.sub('',e.text)=='abcd' for e in result.events))
        for options in ({'strips':True,'incomplete':True},{'tags':r'\frz10'}):
            events,visible=reveal_inputs(**options);before=deepcopy([vars(e) for e in events])
            result=reveal.collapse_progressive_text_reveals(events,visible)
            self.assertEqual(result.removed_count,0);self.assertFalse(result.visibility_updates)
            self.assertTrue(all(a is b for a,b in zip(events,result.events)))
            self.assertEqual([vars(e) for e in events],before)
        hold=events[-2:-1]
        self.assertIs(reveal.collapse_progressive_text_reveals(hold,visible).events,hold)

    def test_caller_adopts_zero_count_updates_before_next_consumer(self):
        # Stop at the next consumer to check the real pipeline handoff in isolation.
        from types import SimpleNamespace
        events,visible=reveal_inputs(gaps=True)
        class AdoptionLog(dict):
            def __init__(self,values):
                super().__init__(values);self.accepted=[]
            def update(self,values):
                self.accepted.append(dict(values));super().update(values)
        visible=AdoptionLog(visible)
        frozen=SimpleNamespace(captions=events,vectors=[],visible=visible,spaces={},statistics={'dropped':0},blanks=[])
        prepared=SimpleNamespace(rows=[],effects_removed=0,timing_sources=[])
        source=SimpleNamespace(styles={},events={},scaled_borders=True)
        class HandoffChecked(Exception):pass
        def next_consumer(output,adopted,*args):
            self.assertIs(adopted,visible)
            # These accepted values can equal existing entries: still require
            # the caller to adopt the producer delta even with zero removals.
            self.assertEqual(adopted.accepted,[{e.source_index:'abcd' for e in events if e.source_index!=99999}])
            for e in output:
                if e.source_index!=99999:self.assertEqual(adopted[e.source_index],'abcd')
            self.assertEqual(adopted[999999],'removed historical source')
            self.assertTrue(all(engine.OVERRIDE_RE.sub('',e.text)=='abcd' for e in output if e.source_index!=99999))
            raise HandoffChecked
        with patch.object(engine,'flatten_complete_line_jitter',return_value=SimpleNamespace(events=events,frames=0,stacks=0,captions=[])), \
             patch.object(engine,'remove_owned_word_echoes',return_value=SimpleNamespace(events=events,removed_effects=0)), \
             patch.object(engine,'remove_fragmented_font_decorations',side_effect=next_consumer):
            with self.assertRaises(HandoffChecked):
                engine._consolidate_text_events(source,prepared,frozen,set(),engine.SimplifyConfig(),None)

    def test_cold_source_installed_processing_and_owned_uninstall(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);unrelated=root/'unrelated';unrelated.mkdir()
            installer=load_installer();target=root/'installed tools with spaces'
            _,installed=installer.install(ROOT,target,individual_launchers=False)
            for tools in (ROOT,installed):
                child=subprocess.run([sys.executable,'-I','-c','import sys\nsys.path.insert(0,'+repr(str(tools))+')\n'+COLD_CODE],cwd=unrelated,capture_output=True,text=True)
                self.assertEqual(child.returncode,0,child.stdout+child.stderr)
            user=installed/'_simplify_ass/user.py';user.write_text('# user\n')
            installer.remove(target);self.assertEqual(user.read_text(),'# user\n')
            for name in ('progressive_reveals','text_visibility'):
                self.assertFalse((installed/'_simplify_ass'/f'{name}.py').exists())
                self.assertFalse(any((installed/'_simplify_ass').rglob(name+'*.pyc')))


if __name__=='__main__':unittest.main()
