"""Sampling ownership, lazy dependencies, refusals and installed execution."""
import test_paths
from copy import deepcopy
import inspect
from pathlib import Path
import pickle
import subprocess
import sys
import tempfile
from typing import get_type_hints
import unittest
from unittest.mock import patch

import simplify_ass as engine
from _simplify_ass import caption_paint_sampling as sampling
from check_windows_installer import ROOT, load_installer
from caption_paint_sampling_test_helpers import FAMILY, make_font, paint_inputs
from override_module_test_helpers import patch_interpreter_bindings

FUNCTIONS = ('_settled_caption_paint_samples','_pool_source_caption_paint')

COLD_CHECKS = r'''
from copy import deepcopy
from pathlib import Path
from _simplify_ass import caption_paint_sampling as s
assert 'simplify_ass' not in sys.modules
assert not any(n.split('.')[0] in {'PIL','fontTools','uharfbuzz'} for n in sys.modules)
accepted=[((2.,1.,1.,0.,0.),(4.,2.,0.,2.,0.))]
paint=s._pool_source_caption_paint(accepted)
assert (paint.fill,paint.outline,paint.outline_alpha,paint.border)==('0000FF','00FF00',128,(2.,2.))
assert not any(n.split('.')[0] in {'PIL','fontTools','uharfbuzz'} for n in sys.modules)
font_path=Path(sys.argv[1]);metric=s.FontMetrics([font_path.parent])
face=metric.matching_face(FAMILY,0,False)
assert face is not None and Path(face.path).resolve()==font_path.resolve()
foreground,planes=paint_inputs()
before=deepcopy([vars(e) for e in planes])
first=s._settled_caption_paint_samples(foreground,planes,metric)
assert first is not None and all(len(region)==5 and region[0]>0 and region[1]>0 for region in first)
assert s._settled_caption_paint_samples(foreground,list(reversed(planes)),metric)==first
assert [vars(e) for e in planes]==before
paint=s._pool_source_caption_paint([first])
assert isinstance(paint,s.SourceCaptionPaint) and paint.border==(2.,2.)
bad=replace_event(foreground,state={**foreground.state,'fsp':1})
assert s._settled_caption_paint_samples(bad,[bad],metric) is None
assert 'simplify_ass' not in sys.modules
import simplify_ass as engine
assert engine._settled_caption_paint_samples is s._settled_caption_paint_samples
assert engine.SourceCaptionPaint is s.SourceCaptionPaint
assert Path(s.__file__).resolve()==Path(engine.__file__).resolve().parent/'_simplify_ass/caption_paint_sampling.py'
import py_compile
py_compile.compile(s.__file__,doraise=True)
'''
COLD_CODE = Path(__file__).with_name('caption_paint_sampling_test_helpers.py').read_text() + COLD_CHECKS


class CaptionPaintSamplingModuleChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        cls.font = Path(cls.folder.name)/'PaintSampling.ttf'
        make_font(cls.font)
        cls.metric = engine.FontMetrics([cls.font.parent])
        face = cls.metric.matching_face(FAMILY,0,False)
        assert face is not None and Path(face.path).resolve()==cls.font.resolve()
        cls.metric.ass_em_scale(face)

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def test_canonical_aliases_annotations_and_historical_root_lookup(self):
        for name in FUNCTIONS:
            value = getattr(sampling,name)
            self.assertIs(value,getattr(engine,name))
            get_type_hints(value)
            self.assertIs(pickle.loads(('csimplify_ass\n'+name+'\n.').encode()),value)
            self.assertIs(pickle.loads(pickle.dumps(value)),value)
        self.assertIs(sampling.Event,engine.Event)
        self.assertIs(sampling.FontMetrics,engine.FontMetrics)
        self.assertIs(sampling.SourceCaptionPaint,engine.SourceCaptionPaint)
        self.assertEqual(sampling.SourceCaptionPaint.__module__,'_simplify_ass.caption_rendering')
        self.assertEqual(tuple(inspect.signature(sampling._settled_caption_paint_samples).parameters),
                         ('foreground','copies','metric'))

    def test_pooling_borrows_samples_and_returns_canonical_paint(self):
        samples = [((2.,1.,1.,0.,0.),(4.,2.,0.,2.,0.))]
        before = deepcopy(samples)
        paint = sampling._pool_source_caption_paint(samples)
        self.assertEqual(paint,engine.SourceCaptionPaint('0000FF','00FF00',128))
        self.assertEqual(sampling._pool_source_caption_paint(samples*3),paint)
        self.assertEqual(samples,before)
        self.assertIsNot(sampling._pool_source_caption_paint(samples),paint)

    def test_exact_sampling_replays_settled_paint_without_mutating_sources(self):
        foreground,planes = paint_inputs()
        before = deepcopy([vars(e) for e in planes])
        states = [e.state for e in planes]
        result = sampling._settled_caption_paint_samples(foreground,planes,self.metric)
        self.assertIsNotNone(result)
        self.assertTrue(all(isinstance(region,tuple) and len(region)==5 and region[0]>0 and region[1]>0 for region in result))
        final,settled = paint_inputs(transformed=False)
        self.assertEqual(result,sampling._settled_caption_paint_samples(final,settled,self.metric))
        self.assertEqual([vars(e) for e in planes],before)
        self.assertTrue(all(e.state is original for e,original in zip(planes,states)))

    def test_numeric_layer_and_source_order_are_distinct_from_supplied_list_order(self):
        foreground,planes = paint_inputs(transformed=False)
        result = sampling._settled_caption_paint_samples(foreground,planes,self.metric)
        self.assertEqual(result,sampling._settled_caption_paint_samples(foreground,list(reversed(planes)),self.metric))
        background = engine.replace_event(planes[0],layer='2')
        top = engine.replace_event(foreground,layer='10')
        self.assertEqual(result,sampling._settled_caption_paint_samples(top,[top,background],self.metric))
        foreground,planes = paint_inputs(transformed=False,same_layer=True)
        first = sampling._settled_caption_paint_samples(foreground,planes,self.metric)
        promoted = engine.replace_event(planes[0],source_index=9999)
        second = sampling._settled_caption_paint_samples(foreground,[promoted,foreground],self.metric)
        self.assertNotEqual(first,second)

    def test_sampling_without_deprecated_or_newer_flattened_pixel_apis(self):
        from PIL import Image
        foreground,planes = paint_inputs()
        expected = sampling._settled_caption_paint_samples(foreground,planes,self.metric)
        self.assertIsNotNone(expected)
        # The old API is being removed; its replacement is absent on older Pillow.
        unavailable = AssertionError('Flattened pixel API unavailable')
        with patch.object(Image.Image,'getdata',side_effect=unavailable,create=True), \
                patch.object(Image.Image,'get_flattened_data',side_effect=unavailable,create=True):
            actual = sampling._settled_caption_paint_samples(foreground,planes,self.metric)
        self.assertEqual(actual,expected)

    def test_existing_unsupported_layout_and_paint_keep_refusal(self):
        foreground,planes = paint_inputs(transformed=False)
        for change in ({'fsp':1},{'kerning':True},{'u':True},{'s':True},
                       {'fs':0},{'fs':10000},{'blur':65},{'be':1},{'bord':1},{'xshad':1}):
            with self.subTest(change=change):
                bad = engine.replace_event(foreground,state={**foreground.state,**change})
                self.assertIsNone(sampling._settled_caption_paint_samples(bad,[bad],self.metric))
        for text in ('A\u0301','\u05d0'):
            bad = engine.replace_event(foreground,text=foreground.text.replace('AAA',text))
            self.assertIsNone(sampling._settled_caption_paint_samples(bad,[bad],self.metric))
        changed = engine.replace_event(foreground,text=foreground.text.replace('}',r'\t(0,100,\fscx120)}'))
        self.assertIsNone(sampling._settled_caption_paint_samples(changed,[changed],self.metric))
        with patch.object(self.metric,'matching_face',return_value=None):
            self.assertIsNone(sampling._settled_caption_paint_samples(foreground,planes,self.metric))

    def test_metric_failures_preserve_existing_refusal_and_exception_boundaries(self):
        foreground,planes = paint_inputs()
        for error in (OSError,ValueError,RuntimeError):
            with self.subTest(error=error),patch.object(self.metric,'face_data',side_effect=error('probe')):
                self.assertIsNone(sampling._settled_caption_paint_samples(foreground,planes,self.metric))
        with patch.object(self.metric,'face_data',side_effect=MemoryError('probe')):
            with self.assertRaises(MemoryError):
                sampling._settled_caption_paint_samples(foreground,planes,self.metric)

    def test_invocation_buffers_and_actual_interpreter_observation(self):
        foreground,planes = paint_inputs()
        first = sampling._settled_caption_paint_samples(foreground,planes,self.metric)
        second = sampling._settled_caption_paint_samples(foreground,planes,self.metric)
        self.assertEqual(first,second)
        self.assertIsNot(first,second)
        self.assertIsNot(first[0],second[0])
        with patch_interpreter_bindings(engine,'apply_override',wraps=engine.apply_override) as replay:
            self.assertEqual(first,engine._settled_caption_paint_samples(foreground,planes,self.metric))
            self.assertEqual([call.args[1] for call in replay.call_args_list],['1c','1a','blur'])
        self.assertEqual(sampling._settled_caption_paint_samples(foreground,planes,self.metric),first)

    def test_cold_source_and_installed_sampling_and_owned_uninstall(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); unrelated = root/'unrelated'; unrelated.mkdir()
            installer = load_installer(); target = root/'installed tools with spaces'
            _,installed = installer.install(ROOT,target,individual_launchers=False)
            for tools in (ROOT,installed):
                child = subprocess.run([sys.executable,'-I','-c',
                    'import sys\nsys.path.insert(0,'+repr(str(tools))+')\nsys.argv=["paint-probe",'+repr(str(self.font))+']\n'+COLD_CODE],
                    cwd=unrelated,capture_output=True,text=True)
                self.assertEqual(child.returncode,0,child.stdout+child.stderr)
            user = installed/'_simplify_ass/user.py'; user.write_text('# user\n')
            installer.remove(target)
            self.assertEqual(user.read_text(),'# user\n')
            self.assertFalse((installed/'_simplify_ass/caption_paint_sampling.py').exists())
            self.assertFalse(any((installed/'_simplify_ass').rglob('caption_paint_sampling*.pyc')))


if __name__=='__main__':
    unittest.main()
