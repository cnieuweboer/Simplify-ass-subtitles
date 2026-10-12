"""Render selected first/second/third corpus conversions for policy inspection."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
from PIL import Image, ImageChops, ImageDraw

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import simplify_ass as s
DEST=ROOT/'validation/second-pass-investigation'/s.__version__
samples={'Sword-S01E01':[256.5,751], 'Sword-S01E03':[121.3],
         'Sword-S01E01-track6':[256.5], 'Sword-S01E02-track5':[933],
         'DemonSlayer-S04E02':[1310,1340],
         'Overlord-S04E02':[70.5,72.75,73.0,73.7,76,100,1279,1280,1294.65,1297.75,1316,1329],
         'Attack-on-Titan-S02E01-track3':[728.22,729.18]}
records=[]
for name,times in samples.items():
    paths={'first':ROOT/'validation/lyric-layer-corpus/windows'/(name+'-current.ass'),
           'second':DEST/(name+'.second.ass'), 'third':DEST/(name+'.third.ass')}
    for at in times:
        images,fonts={},{}
        for label,path in paths.items():
            output=DEST/f'{name}.{at}.{label}.png'
            vf=f'settb=1/1000,setpts=PTS+{round(at*1000)},ass=filename={path}:fontsdir={ROOT/"fonts"}'
            run=subprocess.run(['ffmpeg','-v','info','-f','lavfi','-i','color=c=gray:s=1920x1080:r=1',
                                '-vf',vf,'-frames:v','1','-threads','1','-y',str(output)],
                               check=True,capture_output=True,text=True)
            images[label]=Image.open(output).convert('RGB')
            fonts[label]=[line for line in run.stderr.splitlines() if 'fontselect:' in line]
        differences={}
        for a,b in [('first','second'),('second','third')]:
            diff=ImageChops.difference(images[a],images[b]);data=diff.tobytes()
            differences[a+'-'+b]=dict(pixel_identical=diff.getbbox() is None,bbox=diff.getbbox(),
                                       changed_pixels=sum(bool(r or g or b) for r,g,b in zip(data[::3],data[1::3],data[2::3])))
        board=Image.new('RGB',(1920*3,1110),'#202020');draw=ImageDraw.Draw(board)
        for column,label in enumerate(('first','second','third')):
            draw.text((column*1920+10,8),f'{name} / {at}s / {label}',fill='white')
            board.paste(images[label],(column*1920,30))
        board.save(DEST/f'{name}.{at}.comparison.png')
        records.append(dict(name=name,time=at,differences=differences,font_selections=fonts,
                            hashes={label:hashlib.sha256(path.read_bytes()).hexdigest() for label,path in paths.items()}))
        (DEST/'corpus-renders.json').write_text(json.dumps(records,indent=2)+'\n')
        print(name,at,differences,flush=True)
print(len(records),'native-resolution corpus frame triplets rendered',flush=True)
