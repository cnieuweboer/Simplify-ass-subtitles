#!/usr/bin/env python3
"""Check positioned-row boundaries and preserve virtual-row tolerance."""
from pathlib import Path
import json
import tempfile
import simplify_ass as s

ROOT = Path(__file__).resolve().parent
header = (ROOT/'test-data/Overlord-22m06-source.ass').read_text(
    encoding='utf-8-sig').split('Dialogue:',1)[0]
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory)/'input.ass'
    path.write_text(header+'Dialogue: 0,0:00:01.00,0:00:03.00,ED-R,,0,0,0,,{\\pos(0,0)}a\n')
    sample = s.load_subtitle_events(path)[1][0]
checks = []

def ok(name,condition):
    assert condition,name
    checks.append(name)

def event(x,y=0,*,size=20,scale=100,unit=1,index=0):
    tags = '' if x is None else f'\\pos({x:g},{y:g})'
    return s.replace_event(sample,source_index=index,unit=unit,
                           text='{'+tags+f'\\fs{size:g}\\fscy{scale:g}'+'}a')

def valid(events,**kwargs):
    return s.positioned_row_geometry(events,**kwargs) is not None

ok('empty list supplies no row',not valid([]))
ok('single anchor supplies no row',not valid([event(0)]))
ok('unpositioned fragment rejects geometry',not valid([event(0),event(None)]))
row = [event(0),event(20),event(40)]
ok('coordinates remain in supplied reading order',
   s.positioned_row_geometry(row)==([0.,20.,40.],[0.,0.,0.]))
ok('reversed order is rejected rather than silently sorted',not valid(row[::-1]))
ok('coincident anchors reject geometry',not valid([event(0),event(0)]))
ok('horizontal step at unit boundary rejects geometry',not valid([event(0),event(1)]))
ok('horizontal step beyond unit boundary accepts geometry',valid([event(0),event(1.01)]))
ok('negative coordinates remain eligible',valid([event(-40),event(-20)]))
ok('total vertical spread at boundary accepts geometry',valid([event(0),event(20,3)]))
ok('total vertical spread beyond boundary rejects geometry',not valid([event(0),event(20,3.01)]))
ok('pairwise close anchors cannot drift into a second row',
   not valid([event(0),event(20,2),event(40,4)]))
ok('smallest height bounds rows with differing sizes',
   not valid([event(0,size=100),event(20,3.01)]))
ok('scaled height at boundary accepts geometry',
   valid([event(0),event(20,1.5,scale=50)]))
ok('scaled height beyond boundary rejects geometry',
   not valid([event(0),event(20,1.51,scale=50)]))
mixed_units = [event(0,unit=2),event(1.5,unit=1)]
ok('merged rows retain minimum-unit horizontal policy',valid(mixed_units))
ok('virtual rows retain first-unit horizontal policy',
   not valid(mixed_units,min_x_step=mixed_units[0].unit))
ok('explicit zero tolerance is not replaced by the default',
   valid([event(0),event(.5)],min_x_step=0))

def ids(runs):
    return [[e.source_index for e in run] for run in runs]

ok('empty candidates produce no runs',s.split_positioned_row_runs([])==[])
a,b,c = event(0,index=1),event(40,index=2),event(80.01,index=3)
ok('gap boundary joins, wider gap splits',
   ids(s.split_positioned_row_runs([c,b,a]))==[[1,2],[3]])
ok('splitting retains original event objects',
   s.split_positioned_row_runs([c,b,a])[0][0] is a)
small,tall = event(0,size=10,index=1),event(20.01,size=100,index=2)
ok('gap splitting uses smaller adjacent height',
   ids(s.split_positioned_row_runs([tall,small]))==[[1],[2]])
scaled = event(20.01,scale=50,index=2)
ok('gap splitting respects vertical font scale',
   ids(s.split_positioned_row_runs([scaled,event(0,index=1)]))==[[1],[2]])
tie1,tie2 = event(0,index=1),event(0,index=2)
ok('tied anchors retain stable source order',
   ids(s.split_positioned_row_runs([tie2,tie1]))==[[2,1]])
ok('run grouping does not bypass duplicate-anchor validation',
   not valid(s.split_positioned_row_runs([tie2,tie1])[0]))
before = [(e.fields(),e.state.copy(),e.unit) for e in row]
s.positioned_row_geometry(row)
s.split_positioned_row_runs(row)
ok('geometry helpers leave source events unchanged',
   before==[(e.fields(),e.state,e.unit) for e in row])
(ROOT/'validation').mkdir(exist_ok=True)
(ROOT/'validation/row-geometry-checks.json').write_text(json.dumps(checks,indent=2)+'\n')
print(f'{len(checks)} row-geometry checks passed')
