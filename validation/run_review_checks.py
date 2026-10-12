"""Run Windows font-backend regressions; RAQM is an explicit occasional check."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from PIL import features
import argparse, hashlib, json, os, shutil, subprocess, sys, time

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--backend',choices=('both','windows','raqm'),default='windows',
                    help='default: Windows BASIC plus real HarfBuzz')
args=parser.parse_args()
if args.backend in ('both','windows'):
    try:
        import uharfbuzz
    except ImportError:
        parser.error('Windows regression requires real uharfbuzz; install with: python -m pip install uharfbuzz')
if args.backend=='raqm' and not features.check_feature('raqm'):
    parser.error('RAQM regression requires a Pillow build with RAQM support')
if args.backend=='both':
    backends=['windows','raqm'] if features.check_feature('raqm') else ['windows']
else:
    backends=[args.backend]
scripts=[x['script'] for x in json.loads((root/'validation/regression-inventory.json').read_text())['current']]
pixel={s for s in scripts if s.endswith('_render.py') or Path(s).name=='check_relative_size_render.py'}
all_results=[]
backend_results=[]
for backend in backends:
    print('Backend:',backend,flush=True)
    started=time.time()
    destination=root/'validation/backend-runs'/backend
    destination.mkdir(parents=True,exist_ok=True)
    env=os.environ.copy()
    env['ASS_REGRESSION_FONT_BACKEND']=backend
    startup=str((root/'validation/backend_startup').resolve())
    inherited=[str(Path(p or os.curdir).resolve()) for p in env.get('PYTHONPATH','').split(os.pathsep)] if env.get('PYTHONPATH') else []
    env['PYTHONPATH']=os.pathsep.join([startup,*inherited])
    def run(script):
        start=time.perf_counter()
        p=subprocess.run([sys.executable,str(root/'validation/run_backend_check.py'),
                          '--backend',backend,str(root/script)],capture_output=True,text=True,env=env)
        log=p.stdout+p.stderr
        (destination/(Path(script).stem+'.log')).write_text(log)
        (root/'validation'/(Path(script).stem+'.log')).write_text(log)
        entry=dict(script=script,backend=backend,exit_code=p.returncode,
                   seconds=round(time.perf_counter()-start,3),summary=p.stdout.splitlines()[-3:])
        print(backend,script,p.returncode,entry['summary'],flush=True)
        if p.returncode:print(p.stderr[-1600:],flush=True)
        return entry
    # Render checks regenerate general checks; serialize those after the rest.
    with ThreadPoolExecutor(max_workers=3) as pool:
        results=list(pool.map(run,[s for s in scripts if s not in pixel]))
    results.extend(run(s) for s in scripts if s in pixel)
    # Preserve newly produced reports before the next backend overwrites them.
    for path in (root/'validation').iterdir():
        if path.is_file() and path.suffix in ('.json','.png') and path.stat().st_mtime>=started:
            shutil.copy2(path,destination/path.name)
    report=dict(backend=backend,checks=results,passed=all(x['exit_code']==0 for x in results))
    (destination/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    backend_results.append(report)
    all_results.extend(results)

report=dict(runtime_sha256=hashlib.sha256((root/'simplify_ass.py').read_bytes()).hexdigest(),
            primary_backend='windows' if 'windows' in backends else 'raqm',
            requested_backend=args.backend,backends=backend_results,checks=all_results,
            raqm_available=features.check_feature('raqm'))
tracked=[root/script for script in scripts]+[Path(__file__),root/'validation/run_backend_check.py',root/'validation/backend_startup/sitecustomize.py',root/'validation/regression-inventory.json']
report['harness_sha256']={str(path.relative_to(root)):hashlib.sha256(path.read_bytes()).hexdigest() for path in tracked}
(root/'validation/complete-regression-checks.json').write_text(json.dumps(report,indent=2)+'\n')
if args.backend=='both' and 'raqm' not in backends:
    print('RAQM unavailable on this host; required Windows regressions completed',flush=True)
assert all(x['exit_code']==0 for x in all_results)
