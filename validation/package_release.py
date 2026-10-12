from pathlib import Path
import hashlib,json,zipfile
root=Path(__file__).resolve().parents[1]
files=[]
for path in root.rglob('*'):
 if not path.is_file() or '__pycache__' in path.parts or path.suffix in ('.pyc','.zip'):continue
 relative=path.relative_to(root)
 if len(relative.parts)==1:
  if path.suffix not in ('.py','.bat','.ps1','.md'):continue
 elif relative.parts[0]=='validation':
  if path.suffix not in ('.py','.json','.log','.patch','.prof') and path.name not in ('static-outline-comparison.png','outline-karaoke-comparison.png') and not path.name.startswith(('shadow-compare-','jitter-render-','word-echo-render-','lifecycle-render-')):continue
 elif relative.parts[0] not in ('fonts','outputs','test-data'):continue
 files.append(path)
files.sort()
manifest={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
mp=root/'SHA256-MANIFEST.json';mp.write_text(json.dumps(manifest,indent=2)+'\n');files.append(mp)
archive=root/'simplify_ass-v177.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
 for p in files:z.write(p,p.relative_to(root))
with zipfile.ZipFile(archive) as z:
 assert z.testzip() is None
 saved=json.loads(z.read('SHA256-MANIFEST.json'))
 for name,digest in saved.items():assert hashlib.sha256(z.read(name)).hexdigest()==digest,name
print(json.dumps(dict(path=str(archive.resolve()),bytes=archive.stat().st_size,entries=len(files),sha256=hashlib.sha256(archive.read_bytes()).hexdigest())))
