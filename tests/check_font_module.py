"""Private font imports, contour matching, resource roots and installed execution."""
import test_paths
from pathlib import Path
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

import simplify_ass as engine
from _simplify_ass import font_metrics, font_outlines
from stacked_contour_cases import HEADER, event
from validation.runtime_manifest import runtime_manifest

ROOT = Path(__file__).resolve().parents[1]


def installer():
    spec = importlib.util.spec_from_file_location('font_module_installer', ROOT/'installer/windows/install.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FontModuleChecks(unittest.TestCase):
    def child(self, code, directory, search):
        env = os.environ.copy()
        env.pop('PYTHONPATH', None)
        env.pop('PYTHONPYCACHEPREFIX', None)
        result = subprocess.run([sys.executable, '-c',
            'import sys\nsys.path.insert(0,'+repr(str(search))+')\n'+code],
            cwd=directory, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        return result

    def test_existing_engine_names_are_the_actual_private_classes(self):
        for name in ('FontFace', 'FontCapabilities', 'FontLineInkMetrics', 'FontMetrics'):
            self.assertIs(getattr(engine, name), getattr(font_metrics, name))
        self.assertIs(engine.FontOutlineMatcher, font_outlines.FontOutlineMatcher)
        self.assertIs(engine.fit_cubic_points, font_outlines.fit_cubic_points)
        self.assertFalse(hasattr(font_outlines, 'Event'))
        self.assertFalse(hasattr(font_metrics, 'Event'))
        self.assertFalse(hasattr(font_metrics, 'recover_font_row'))

    def test_private_import_does_not_load_the_engine_or_optional_backends(self):
        with tempfile.TemporaryDirectory() as folder:
            self.child("import _simplify_ass.font_outlines\n"
                       "assert 'simplify_ass' not in sys.modules\n"
                       "assert not any(n.split('.')[0] in {'PIL','fontTools','uharfbuzz'} for n in sys.modules)\n",
                       folder, ROOT)

    def test_engine_import_and_disabled_metrics_without_optional_packages(self):
        with tempfile.TemporaryDirectory() as folder:
            self.child("import builtins\noriginal=builtins.__import__\n"
                       "def limited(name,*a,**k):\n"
                       " if name.split('.')[0] in {'PIL','fontTools','uharfbuzz'}: raise ImportError(name)\n"
                       " return original(name,*a,**k)\n"
                       "builtins.__import__=limited\nimport simplify_ass as s\n"
                       "m=s.FontMetrics()\nassert not m.available and m.capabilities==s.FontCapabilities()\n",
                       folder, ROOT)

    def test_manifest_includes_package_edits_additions_and_removals(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); source = root/'simplify_ass.py'
            source.write_text('# standalone\n')
            self.assertEqual(set(runtime_manifest(source)), {'simplify_ass.py'})
            package = root/'_simplify_ass'; package.mkdir()
            (package/'__init__.py').write_text('')
            module = package/'font_metrics.py'; module.write_text('# first\n')
            before = runtime_manifest(source)
            module.write_text('# second\n')
            self.assertNotEqual(before, runtime_manifest(source))
            self.assertEqual(before['simplify_ass.py'], runtime_manifest(source)['simplify_ass.py'])
            extra = package/'extra.py'; extra.write_text('# added\n')
            self.assertIn('_simplify_ass/extra.py', runtime_manifest(source))
            extra.unlink(); module.unlink()
            self.assertNotIn('_simplify_ass/font_metrics.py', runtime_manifest(source))

    def test_installed_engine_uses_its_own_package_and_sibling_fonts(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); target = root/'installed tools with spaces'
            owner = installer(); _, tools = owner.install(ROOT, target, individual_launchers=False)
            fonts = tools/'fonts'; fonts.mkdir()
            # Reuse existing synthetic-font builders without running their suite.
            builders = {'__file__': str(ROOT/'tests/check_font_selection.py'), '__name__': 'module_font_builders'}
            code = (ROOT/'tests/check_font_selection.py').read_text().split('with tempfile.TemporaryDirectory()')[0]
            exec(compile(code, str(ROOT/'tests/check_font_selection.py'), 'exec'), builders)
            builders['master'](fonts/'local.ttf', 'Extraction Local Font')
            builders['master'](fonts/'outline.ttf', 'Extraction Outline Font')
            # One encoded contour avoids ambiguity with the builder's identical i.
            from fontTools.ttLib import TTFont
            with TTFont(fonts/'outline.ttf') as font:
                for table in font['cmap'].tables:
                    if table.isUnicode():
                        table.cmap.pop(ord('i'), None)
                font.save(fonts/'outline.ttf')
            unrelated = root/'unrelated working directory'; unrelated.mkdir()
            probe = self.child("from pathlib import Path\nimport simplify_ass as s\n"
                "from _simplify_ass import font_metrics as m, font_outlines as o, glyph_placement as g\n"
                "assert s.FontMetrics is m.FontMetrics\n"
                "assert s.authored_glyph_positions is g.authored_glyph_positions\n"
                "assert Path(g.__file__).resolve().parent==Path(m.__file__).resolve().parent\n"
                "assert s.FontOutlineMatcher is o.FontOutlineMatcher and s.fit_cubic_points is o.fit_cubic_points\n"
                "assert Path(o.__file__).resolve().parent==Path(m.__file__).resolve().parent\n"
                "assert Path(m.__file__).resolve().parent==Path(s.__file__).resolve().parent/'_simplify_ass'\n"
                "metric=s.FontMetrics()\nf=metric.matching_face('Extraction Local Font',0,False)\n"
                "assert f is not None\nassert Path(f.path).resolve()==Path(s.__file__).resolve().parent/'fonts/local.ttf'\n"
                "assert metric.measure(f,'Ai Ai')>0\nassert metric.line_ink_metrics(f,['Ai Ai']) is not None\n"
                "state={'fn':'Extraction Local Font','fs':40,'an':5}\n"
                "positions=g.authored_glyph_positions(metric,state,'AA',100,.01)\n"
                "assert positions is not None and len(positions)==2\n"
                "assert s.matches_authored_glyph_positions(metric,state,[x for c,x in positions],'AA',100,.01)\n"
                "f=metric.matching_face('Extraction Outline Font',0,False)\nassert f is not None\n"
                "model,em=metric.cubic_outline(f,'A')\nscale=metric.ass_em_scale(f)*40/em\n"
                "path=[];axis=0\n"
                "for value in model:\n"
                " if isinstance(value,str): path.append(value)\n"
                " else: path.append(value*scale+(100 if axis%2==0 else 200));axis+=1\n"
                "matcher=s.FontOutlineMatcher(metric)\n"
                "assert matcher.decode_cubic_outline(f,tuple(path),40,1,set())=='A'\n"
                "assert matcher.metrics is metric\n"
                "import py_compile\n"
                "for p in (Path(s.__file__),*Path(m.__file__).parent.rglob('*.py')): py_compile.compile(str(p),doraise=True)\n"
                "print('installed exact-font measurement passed')\n", unrelated, tools)
            self.assertIn('measurement passed', probe.stdout)
            source = unrelated/'input.ass'
            source.write_text(HEADER.replace('Volkhov', 'Extraction Local Font')+event('Ai Ai',0))
            env = os.environ.copy(); env.pop('PYTHONPATH', None)
            result = subprocess.run([sys.executable, str(tools/'simplify_ass.py'), str(source),
                                     '--stats-json', str(unrelated/'stats.json')],
                                    cwd=unrelated, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            output = source.with_name('input.simple.ass')
            events = engine.load_subtitle_events(output)[1]
            self.assertEqual(len(events), 1)
            self.assertEqual(engine.OVERRIDE_RE.sub('', events[0].text), 'Ai Ai')
            self.assertEqual((events[0].start_s,events[0].end_s),(1,3))
            self.assertEqual(json.loads((unrelated/'stats.json').read_text())['tracks'][0]['stats']['color_phase_change_interval'],0)
            # The uninstaller removes managed bytecode, retaining user fonts.
            self.assertTrue((tools/'_simplify_ass/__pycache__').is_dir())
            owner.remove(target)
            self.assertFalse((tools/'_simplify_ass').exists())
            self.assertTrue((fonts/'local.ttf').is_file())


if __name__ == '__main__':
    unittest.main()
