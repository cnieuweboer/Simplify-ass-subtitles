"""Full-copy ownership, sparse handoff and independent installed execution."""
import test_paths
from copy import deepcopy
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
