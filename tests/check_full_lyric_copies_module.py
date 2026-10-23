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
from full_lyric_copy_test_helpers import full_copy_inputs,transitive_copy_inputs
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
                    self.assertEqual(result.removed_count,2)
                    self.assertEqual(len(result.events),2)
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

    def test_complete_family_pose_follows_selected_original_geometry(self):
        events,visible=full_copy_inputs(variant='chain')
        family=[]
        for n,event in enumerate(events[:3]):
            prefix=event.text.rsplit('}',1)[0]
            event=engine.replace_event(event,text=prefix+('\\fs50' if n==0 else '')+'}AB CD',effect='' if n==0 else 'fx')
            family.append(replace(event,evidence=engine.EventEvidence(frame_pose_intervals=engine._frame_pose_intervals(event))))
        result=copies.collapse_full_lyric_copies(family,{e.source_index:'AB CD' for e in family})
        self.assertEqual(len(result.events),1)
        caption=result.events[0]
        self.assertEqual(caption.state['fs'],50)
        self.assertEqual((caption.start_s,caption.end_s),(1.,5.))
        self.assertEqual(set(caption.evidence.frame_pose_intervals or ()),
            set(family[0].evidence.frame_pose_intervals))

    def test_original_anchor_settles_crossing_copies_without_iteration(self):
        from full_lyric_copy_test_helpers import HEADER
        specs=[('AB CD',1.5,4.5),('A B C D',2,5),('ABCD',2.5,5.5)]
        text=HEADER+''.join('Dialogue: 0,'+engine.format_time(start)+','+engine.format_time(end)+
            r',Default,,0,0,0,,{\pos(320,100)}'+word+'\n' for word,start,end in specs)
        events=list(engine._resolve_document_state(engine.parse_subtitle_document(text)).events.values())
        for event in events:event.lyric=True
        visible={e.source_index:engine.simplify_text(e.text,visible_only=True)[1] for e in events}
        before=deepcopy(events)
        for order in permutations(events):
            with patch.object(copies,'select_static_state',wraps=copies.select_static_state) as selected:
                result=copies.collapse_full_lyric_copies(list(order),MappingProxyType(visible))
            self.assertEqual(result.removed_count,2)
            self.assertEqual([(e.start_s,e.end_s) for e in result.events],[(1.5,5.5)])
            self.assertEqual(engine.OVERRIDE_RE.sub('',result.events[0].text),'A B C D')
            self.assertEqual(selected.call_count,1)
            self.assertEqual({id(e) for e in selected.call_args.kwargs['paint_events']},{id(e) for e in events})
            repeated=copies.collapse_full_lyric_copies(result.events,{**visible,**result.visibility_updates})
            self.assertEqual(repeated.removed_count,0)
        self.assertEqual(events,before)

    def test_complete_original_paint_is_order_independent(self):
        events,visible=full_copy_inputs(variant='chain')
        family=[]
        for event,color in zip(events[:3],('0000FF','00FF00','FF0000')):
            family.append(engine.replace_event(event,text=event.text.replace('\\1c&HFFFFFF&','\\1c&H'+color+'&')))
        appearances=[]
        for order in permutations(family):
            with patch.object(copies,'select_static_state',wraps=copies.select_static_state) as selected:
                result=copies.collapse_full_lyric_copies(list(order),visible)
            self.assertEqual(result.removed_count,2)
            self.assertEqual(selected.call_count,1)
            self.assertEqual({id(e) for e in selected.call_args.kwargs['paint_events']},{id(e) for e in family})
            appearances.append(result.events[0].text)
        self.assertEqual(len(set(appearances)),1)

    def test_zero_length_source_cannot_link_separate_cues(self):
        events,visible=full_copy_inputs(variant='gap')
        point=engine.replace_event(events[0],source_index=99,start_s=4.,end_s=4.,
            start=engine.format_time(4.),end=engine.format_time(4.))
        # A point at a touching boundary must not join two independent holds.
        next_cue=engine.replace_event(events[1],start_s=4.,end_s=7.,start=engine.format_time(4.),end=engine.format_time(7.))
        words={**visible,point.source_index:visible[events[0].source_index]}
        result=copies.collapse_full_lyric_copies([point,events[0],next_cue],words)
        self.assertTrue(any(e.start_s==4. and e.end_s==7. for e in result.events))
        self.assertFalse(any(e.start_s==1. and e.end_s==7. for e in result.events))

    def test_transitive_original_links_settle_a_rolling_chain(self):
        from full_lyric_copy_test_helpers import HEADER
        from full_copy_contract_helpers import accepted_copy_clusters,assert_anchored_copy_contract
        text=HEADER+''.join('Dialogue: 0,'+engine.format_time(1+n*.5)+','+engine.format_time(4+n*.5)+
            r',Default,,0,0,0,,{\pos(320,100)}AB CD'+'\n' for n in range(8))
        events=list(engine._resolve_document_state(engine.parse_subtitle_document(text)).events.values())
        for event in events:event.lyric=True;event.row=0
        visible={e.source_index:'AB CD' for e in events};outputs=[]
        for ordered in (events,list(reversed(events)),events[::2]+events[1::2]):
            with accepted_copy_clusters(engine) as clusters:
                result=copies.collapse_full_lyric_copies(ordered,visible)
            assert_anchored_copy_contract(engine,ordered,visible,result,clusters)
            self.assertEqual(len(result.events),1)
            self.assertEqual((result.events[0].start_s,result.events[0].end_s),(1.,7.5))
            repeated=copies.collapse_full_lyric_copies(result.events,{**visible,**result.visibility_updates})
            self.assertEqual(repeated.removed_count,0)
            outputs.append(sorted((e.source_index,e.start_s,e.end_s,e.text) for e in result.events))
        self.assertTrue(all(o==outputs[0] for o in outputs))

    def test_long_connected_chains_have_no_size_or_duration_cap(self):
        from full_lyric_copy_test_helpers import HEADER
        for count in (20,100):
            text=HEADER+''.join('Dialogue: 0,'+engine.format_time(1+n*.5)+','+engine.format_time(4+n*.5)+
                r',Default,,0,0,0,,{\pos(320,100)}ABCD'+'\n' for n in range(count))
            events=list(engine._resolve_document_state(engine.parse_subtitle_document(text)).events.values())
            for event in events:event.lyric=True;event.row=0
            visible={e.source_index:'ABCD' for e in events}
            result=copies.collapse_full_lyric_copies(events,visible)
            self.assertEqual(result.removed_count,count-1)
            self.assertEqual((result.events[0].start_s,result.events[0].end_s),(1.,4+(count-1)*.5))
            self.assertEqual(copies.collapse_full_lyric_copies(result.events,
                {**visible,**result.visibility_updates}).removed_count,0)

    def test_intervening_ink_partitions_copies_without_changing_paint_order(self):
        from full_lyric_copy_test_helpers import HEADER
        specs=[(1,4,'ABCD',''),(1.5,4.5,'ABCD',''),(2,5,'XXXX','independent'),
               (2,5,'ABCD',''),(2.5,5.5,'ABCD','')]
        text=HEADER+''.join(f'Dialogue: 0,{engine.format_time(a)},{engine.format_time(b)},Default,{name},0,0,0,,'+
            r'{\pos(320,100)\bord1.25\3c&HDDDDDD&}'+word+'\n' for a,b,word,name in specs)
        events=list(engine._resolve_document_state(engine.parse_subtitle_document(text)).events.values())
        for event in events:event.lyric=not event.name;event.row=0
        visible={e.source_index:engine.OVERRIDE_RE.sub('',e.text) for e in events}
        before=deepcopy([vars(e) for e in events])
        result=copies.collapse_full_lyric_copies(events,visible)
        self.assertEqual([(e.start_s,e.end_s) for e in result.events if not e.name],[(1.,4.5),(2.,5.5)])
        self.assertIs(result.events[1],events[2])
        self.assertEqual(result.removed_count,2)
        self.assertEqual([vars(e) for e in events],before)

    def test_shared_clearance_aliases_and_paint_vocabulary_keep_their_owners(self):
        from _simplify_ass import caption_clearance,caption_rendering
        self.assertIs(engine._caption_implicit_anchor,caption_clearance._caption_implicit_anchor)
        self.assertIs(engine._glyph_replacement_row_is_clear,caption_clearance._glyph_replacement_row_is_clear)
        self.assertIs(engine.CAPTION_PAINT_TAGS,caption_rendering.CAPTION_PAINT_TAGS)

    def test_unchanged_paint_order_and_nonconcurrent_content_need_no_measurement(self):
        for placement in (0,4):
            for layer,foreign_layer in (('0','0'),('2','1'),('0','1')):
                events,visible=transitive_copy_inputs(foreign='overlap',insertion=placement,
                    layer=layer,foreign_layer=foreign_layer)
                with patch.object(copies,'_glyph_replacement_row_is_clear',side_effect=AssertionError('unneeded measurement')):
                    result=copies.collapse_full_lyric_copies(events,visible)
                self.assertEqual(result.removed_count,3)
                self.assertEqual(next(e.layer for e in result.events if not e.name),layer)
                self.assertIs(next(e for e in result.events if e.name),next(e for e in events if e.name))
        events,visible=transitive_copy_inputs(foreign='outside')
        result=copies.collapse_full_lyric_copies(events,visible)
        self.assertEqual(result.removed_count,3)

    def test_measured_distant_and_animated_peers_do_not_block_reduction(self):
        metric=engine.FontMetrics([ROOT/'fonts'])
        self.assertIsNotNone(metric.matching_face('Arial',0,False),'Missing exact Arial regular')
        for tags,count in (('',3),(r'\t(0,3000,\fscx105)',3),
                           (r'\t(0,3000,\fscx500)',2)):
            events,visible=transitive_copy_inputs(foreign='distant',marker_tags=tags)
            before=deepcopy([vars(e) for e in events])
            result=copies.collapse_full_lyric_copies(events,visible,font_metrics=metric)
            self.assertEqual(result.removed_count,count,tags)
            self.assertIs(next(e for e in result.events if e.name),next(e for e in events if e.name))
            self.assertEqual([vars(e) for e in events],before)
        events,visible=transitive_copy_inputs(foreign='distant',marker_layout=r'\move(100,100,320,100)')
        self.assertEqual(copies.collapse_full_lyric_copies(events,visible,font_metrics=metric).removed_count,2)

    def test_original_foreground_coverage_allows_lower_effect_planes(self):
        events,visible=transitive_copy_inputs(foreign='overlap',layer='2',foreign_layer='1')
        # A full-length foreground covers the independent ink; lower copies
        # should not require the exact-font disjointness proof to disappear.
        end=max(e.end_s for e in events if not e.name)
        events=[engine.replace_event(e,end_s=end,end=engine.format_time(end)) if n==0 else
                engine.replace_event(e,layer='0') if not e.name else e
                for n,e in enumerate(events)]
        result=copies.collapse_full_lyric_copies(events,visible)
        self.assertEqual(result.removed_count,3)
        self.assertEqual(next(e.layer for e in result.events if not e.name),'2')
        # Shortening the foreground exposes a real order change in its tail.
        events[0]=engine.replace_event(events[0],end_s=4.,end=engine.format_time(4.))
        result=copies.collapse_full_lyric_copies(events,visible)
        self.assertLess(result.removed_count,3)
        self.assertIs(next(e for e in result.events if e.name),events[2])

    def test_unknown_measurement_keeps_sides_and_mixed_layers_keep_order(self):
        events,visible=transitive_copy_inputs(foreign='distant')
        self.assertEqual(copies.collapse_full_lyric_copies(events,visible).removed_count,2)
        events,visible=transitive_copy_inputs(foreign='overlap',layer='2',foreign_layer='3')
        events=[engine.replace_event(e,layer='4') if not e.name and n>2 else e for n,e in enumerate(events)]
        result=copies.collapse_full_lyric_copies(events,visible)
        self.assertEqual([e.layer for e in result.events],['0','3','4'])
        self.assertEqual([(e.start_s,e.end_s) for e in result.events if not e.name],[(1.,4.5),(2.,5.5)])

    def test_connected_matched_fades_keep_source_owned_color_phases(self):
        from full_lyric_copy_test_helpers import HEADER
        colors=('0000FF','00FF00','FF0000','00FFFF')
        text=HEADER+''.join(f'Dialogue: 0,{engine.format_time(1+n)},{engine.format_time(7+n)},Default,,0,0,0,,'+
            r'{\pos(320,100)\bord1.25\3c&HDDDDDD&\fad(2500,2500)\1c&H'+color+'&}ABCD\n'
            for n,color in enumerate(colors))
        events=list(engine._resolve_document_state(engine.parse_subtitle_document(text)).events.values())
        for event in events:event.lyric=True;event.row=0
        visible={e.source_index:'ABCD' for e in events}
        metric=engine.FontMetrics([ROOT/'fonts'])
        self.assertIsNotNone(metric.matching_face('Arial',0,False),'Missing exact Arial regular')
        data=engine.collect_source_text_rows({e.source_index:e for e in events},set(),font_metrics=metric)
        timelines=engine._collect_caption_paint_timelines(data,[],events,metric)
        result=copies.collapse_full_lyric_copies(events,visible,font_metrics=metric)
        self.assertEqual(result.removed_count,3)
        emitted,counts=engine._emit_caption_paint_timelines(result.events,timelines,engine.SimplifyConfig())
        self.assertEqual(counts['color_phase_changes_preserved'],3)
        self.assertEqual([e.state['1c'] for e in emitted],list(colors))
        self.assertEqual([(e.start_s,e.end_s) for e in emitted],[(1.,4.5),(4.5,5.5),(5.5,6.5),(6.5,10.)])

    def test_distinct_color_holds_and_interleaved_content_retain_ownership(self):
        events,visible=full_copy_inputs(variant='chain')
        marker=engine.replace_event(events[-1],start_s=1.,end_s=6.,
            start=engine.format_time(1.),end=engine.format_time(6.),layer='1')
        # A later color hold has the same literal/anchor but a separate lifetime.
        hold=engine.replace_event(events[0],source_index=100,start_s=5.,end_s=7.,
            start=engine.format_time(5.),end=engine.format_time(7.),
            text=events[0].text.replace('\\1c&HFFFFFF&',r'\1c&H00FF00&'))
        ordered=[events[0],marker,events[1],events[2],hold]
        words={**visible,hold.source_index:visible[events[0].source_index]}
        before=deepcopy(ordered)
        result=copies.collapse_full_lyric_copies(ordered,words)
        self.assertEqual(result.removed_count,2)
        self.assertIs(result.events[-1],hold)
        self.assertIs(result.events[0],marker)
        self.assertEqual(marker.layer,'1')
        self.assertEqual((hold.start_s,hold.end_s,hold.state['1c']),(5.,7.,'00FF00'))
        self.assertEqual(ordered,before)

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
