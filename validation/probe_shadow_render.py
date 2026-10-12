"""Inspect libass bitmap output and composite before/after frames."""
from pathlib import Path
import ctypes as c, hashlib, json, sys
import numpy as np
from PIL import Image
root=Path(__file__).resolve().parents[1]
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
folder=root/'validation/full-corpus-v174/windows'
for version in ('v173','v174'):
    r=renderer(library);frame_size(r,1920,1080);storage_size(r,1920,1080);fonts(r,None,b'Nyala',1,None,1)
    data=(folder/('Sword-S01E01-'+version+'.ass')).read_bytes();track=read(library,data,len(data),None)
    targets.append((r,track))
def composite(target,at):
    changed=c.c_int();p=render(*target,round(at*1000),c.byref(changed))
    image=Image.new('RGBA',(1920,1080),(0,0,0,255));bitmaps=0;area=0
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
timestamps=sorted(set([235,239,257]+[t+d for t in (236.59,236.92,237.18,237.38,237.68,237.93,238.18) for d in (-.01,0,.04,.17)]))
checks=[]
for at in timestamps:
    before,bcount,barea,bchange=composite(targets[0],at)
    after,acount,aarea,achange=composite(targets[1],at)
    diff=np.abs(np.asarray(before).astype(np.int16)-np.asarray(after).astype(np.int16))
    entry=dict(at=at,before_bitmaps=bcount,after_bitmaps=acount,before_bitmap_area=barea,after_bitmap_area=aarea,max_channel_difference=int(diff.max()),changed_pixels=int(np.any(diff,axis=2).sum()),mean_channel_difference=float(diff.mean()))
    checks.append(entry)
    if at in (235,238.22,239,257):
        canvas=Image.new('RGB',(3840,1080));canvas.paste(before,(0,0));canvas.paste(after,(1920,0));canvas.save(root/'validation'/('shadow-compare-'+str(at).replace('.','-')+'.png'))
    print(entry,flush=True)
for r,track in targets:free(track);renderer_done(r)
done(library)
report=dict(runtime_sha256=hashlib.sha256((root/'simplify_ass.py').read_bytes()).hexdigest(),renderer='libass 0.17.1 at 1920x1080',checks=checks)
(root/'validation/shadow-render-checks.json').write_text(json.dumps(report,indent=2)+'\n')
