"""Inspect libass bitmap output and composite before/after frames."""
from pathlib import Path
import ctypes as c, hashlib, json, sys
import numpy as np
from PIL import Image
root=Path(__file__).resolve().parents[1]
workspace=root.parent
class Bitmap(c.Structure):pass
Bitmap._fields_=[('w',c.c_int),('h',c.c_int),('stride',c.c_int),('bitmap',c.POINTER(c.c_ubyte)),('color',c.c_uint32),('x',c.c_int),('y',c.c_int),('next',c.POINTER(Bitmap)),('type',c.c_int)]
a=c.CDLL('libass.so.9')
def function(name,restype,args):
    f=getattr(a,name);f.restype=restype;f.argtypes=args;return f
ptr=c.c_void_p
init=function('ass_library_init',ptr,[]);renderer=function('ass_renderer_init',ptr,[ptr])
frame_size=function('ass_set_frame_size',None,[ptr,c.c_int,c.c_int]);storage_size=function('ass_set_storage_size',None,[ptr,c.c_int,c.c_int])
fonts=function('ass_set_fonts',None,[ptr,c.c_char_p,c.c_char_p,c.c_int,c.c_char_p,c.c_int])
add_font=function('ass_add_font',None,[ptr,c.c_char_p,c.c_char_p,c.c_int])
read=function('ass_read_memory',ptr,[ptr,c.c_char_p,c.c_size_t,c.c_char_p])
render=function('ass_render_frame',c.POINTER(Bitmap),[ptr,ptr,c.c_longlong,c.POINTER(c.c_int)])
free=function('ass_free_track',None,[ptr]);renderer_done=function('ass_renderer_done',None,[ptr]);done=function('ass_library_done',None,[ptr])
library=init()
for path in (root.parent/'regression-v172/fonts').iterdir():
    data=path.read_bytes();add_font(library,path.name.encode(),data,len(data))
targets=[]
paths=[workspace/'upload/Attack on Titan - S02E01 - track-3.original.ass',workspace/'aot-investigation/v174-basic.ass',root/'validation/full-corpus-v175/windows/Attack-on-Titan-S02E01-track3-v175.ass']
for path in paths:
    r=renderer(library);frame_size(r,1920,1080);storage_size(r,1920,1080);fonts(r,None,b'Arial',1,None,1)
    data=path.read_bytes();track=read(library,data,len(data),None);targets.append((r,track))
def composite(target,at):
    changed=c.c_int();p=render(*target,round(at*1000),c.byref(changed))
    image=Image.new('RGBA',(1920,1080),(128,128,128,255));bitmaps=0;area=0
    while p:
        b=p.contents
        if b.w and b.h and b.color&255<255:
            bitmaps+=1;area+=b.w*b.h
            mask=np.frombuffer(c.string_at(b.bitmap,b.stride*(b.h-1)+b.w),dtype=np.uint8)
            padded=np.zeros(b.stride*b.h,dtype=np.uint8);padded[:len(mask)]=mask
            alpha=((padded.reshape(b.h,b.stride)[:,:b.w].astype(np.uint16)*(255-(b.color&255))+127)//255).astype(np.uint8)
            overlay=Image.new('RGBA',(b.w,b.h),((b.color>>24)&255,(b.color>>16)&255,(b.color>>8)&255,255))
            overlay.putalpha(Image.fromarray(alpha));image.alpha_composite(overlay,(b.x,b.y))
        p=b.next
    return image.convert('RGB'),bitmaps,area,changed.value
timestamps=[1340.65,1340.66,1340.76,1341,1341.5,1342.5,1343.54,1343.55,1343.56,1344,1348.98,1348.99,1349.2,1350.3,1350.5,1351.66,1351.67,1354.02,1354.03,1354.24,1354.25,1402.81,1402.93,1402.94,1403.5,1403.94,1404.26,1404.27,1404.7,1405.38,1417.05,1417.06]
checks=[]
for at in timestamps:
    samples=[composite(t,at) for t in targets]
    entry=dict(at=at,source_bitmaps=samples[0][1],v174_bitmaps=samples[1][1],v175_bitmaps=samples[2][1],source_area=samples[0][2],v174_area=samples[1][2],v175_area=samples[2][2])
    checks.append(entry)
    if at in (1341.5,1350.3,1403.5):
        canvas=Image.new('RGB',(1440,480))
        for i,(im,*_) in enumerate(samples):canvas.paste(im.crop((240,0,1680,160)),(0,i*160))
        canvas.save(root/'validation'/('jitter-render-'+str(at).replace('.','-')+'.png'))
for r,track in targets:free(track);renderer_done(r)
done(library)
report=dict(runtime_sha256=hashlib.sha256((root/'simplify_ass.py').read_bytes()).hexdigest(),renderer='libass 0.17.1',exact_ED_font_available=False,font_limitation='IM FELL English PRO is unavailable; this is a consistent fallback-font diagnostic, not exact episode-font visual proof.',checks=checks)
(root/'validation/jitter-render-checks.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
