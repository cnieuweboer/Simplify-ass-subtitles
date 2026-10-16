"""Fresh-process conversion benchmark; no production modifications."""
from pathlib import Path
import argparse,contextlib,cProfile,hashlib,importlib.util,json,os,platform,resource,sys,time
from runtime_manifest import runtime_manifest
ap=argparse.ArgumentParser();ap.add_argument('--engine',required=True,type=Path);ap.add_argument('--source',required=True,type=Path);ap.add_argument('--fonts',required=True,type=Path);ap.add_argument('--output',required=True,type=Path);ap.add_argument('--profile',action='store_true');ap.add_argument('--skip-outline-proofs',action='store_true',help='Diagnostic only: intentionally loses recovered outline colors');args=ap.parse_args()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
initial_manifest=runtime_manifest(args.engine)
sys.path.insert(0,str(args.engine.resolve().parent))
start=time.perf_counter();spec=importlib.util.spec_from_file_location('bench_engine',args.engine);engine=importlib.util.module_from_spec(spec);sys.modules[spec.name]=engine;spec.loader.exec_module(engine);import_s=time.perf_counter()-start
start=time.perf_counter();owner=engine.FontMetrics([args.fonts]) if hasattr(engine,'FontMetrics') else engine.FontSpacing([args.fonts]);font_setup_s=time.perf_counter()-start
kwargs={'font_metrics':owner,'font_report':engine.FontProcessingReport()} if hasattr(engine,'FontProcessingReport') else {'font_spacing':owner}
if args.skip_outline_proofs:
 engine._collect_outline_strip_evidence=lambda *args,**kwargs:None
input_sha=sha(args.source);args.output.parent.mkdir(parents=True,exist_ok=True)
prof=cProfile.Profile() if args.profile else None
with args.output.with_suffix('.log').open('w') as log,contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):
 if prof:prof.enable()
 wall=time.perf_counter();cpu=time.process_time();stats=engine.simplify_ass(args.source,args.output,engine.SimplifyConfig(),**kwargs);cpu_s=time.process_time()-cpu;wall_s=time.perf_counter()-wall
 if prof:prof.disable();prof.dump_stats(str(args.output.with_suffix('.prof')))
assert sha(args.source)==input_sha
assert runtime_manifest(args.engine)==initial_manifest, 'Runtime sources changed during conversion'
result=dict(version=engine.__version__,engine_sha256=sha(args.engine),source=str(args.source),source_sha256=input_sha,font_setup_s=font_setup_s,import_s=import_s,wall_s=wall_s,cpu_s=cpu_s,statistics=stats,profiled=args.profile,skip_outline_proofs=args.skip_outline_proofs,max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,output=str(args.output),output_sha256=sha(args.output),python=platform.python_version(),platform=platform.platform(),pid=os.getpid())
result['runtime_manifest']=initial_manifest
result['missing_families']=sorted(kwargs['font_report'].missing_families) if 'font_report' in kwargs else None
args.output.with_suffix('.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:result[k] for k in ['version','wall_s','cpu_s','font_setup_s','profiled','output']}),flush=True)
