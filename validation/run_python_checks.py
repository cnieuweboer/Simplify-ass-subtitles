from pathlib import Path
import json
import subprocess
import sys
import time

root = Path(__file__).resolve().parents[1]
scripts = [item['script'] for item in json.loads(
    (root/'validation/regression-inventory.json').read_text())['current'] if item['category']=='general']
results = []
for script in scripts:
    started = time.perf_counter()
    result = subprocess.run([sys.executable,str(root/script)],capture_output=True,text=True)
    (root/'validation'/script.replace('.py','.log')).write_text(result.stdout+result.stderr)
    entry = {'script':script,'exit_code':result.returncode,
        'seconds':round(time.perf_counter()-started,3),'summary':result.stdout.splitlines()[-3:]}
    results.append(entry)
    print(script,result.returncode,entry['summary'],flush=True)
    if result.returncode:
        print(result.stderr,flush=True)
        break
(root/'validation/existing-python-checks.json').write_text(json.dumps(results,indent=2)+'\n')
assert len(results)==len(scripts) and all(item['exit_code']==0 for item in results)
