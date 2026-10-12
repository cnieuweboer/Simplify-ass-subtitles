import test_paths  # Resolve the repository for direct test execution.
from pathlib import Path
import sys,tempfile,collections
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import simplify_ass as s
from font_geometry_test_helpers import font_test_report, measurement_fonts, row_test_call, adapt_reference_font_api, install_row_test_doubles
install_row_test_doubles(s)
root=Path(__file__).resolve().parents[1]
metric=s.FontMetrics([root/'fonts'])
header=r'''[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
ScaledBorderAndShadow: yes
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sign,Arial,40,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,5,0,0,0,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
def ev(tags,text='m 0 0 l 400 0 400 100 0 100',layer='0',start='0:00:01.00',end='0:00:04.00'):
    return f'Dialogue: {layer},{start},{end},Sign,,0,0,0,,{{{tags}}}{text}\n'
checks=0
with tempfile.TemporaryDirectory() as temp:
    p=Path(temp)/'input.ass'
    def load(events):
        p.write_text(header+events)
        return s.load_subtitle_events(p)[1]
    def vectors(events):
        return s.reduce_supporting_drawings(load(events))[0]
    simple=r'\an7\pos(100,100)\p1\bord0\shad0'
    a=vectors(ev(simple+r'\clip(100,0,300,1000)\1c&H0000FF&')+
              ev(simple+r'\clip(300,0,500,1000)\1c&HFF0000&'))
    assert len(a)==1 and s.rectangle_clip(a[0])==(100,100,500,200)
    assert a[0].state['1c']=='800080';checks+=1
    assert not vectors(ev(simple+r'\clip(100,0,299,1000)')+
                       ev(simple+r'\clip(300,0,500,1000)'));checks+=1
    assert not vectors(ev(simple+r'\clip(100,0,350,1000)')+
                       ev(simple+r'\clip(300,0,500,1000)'));checks+=1
    assert not vectors(ev(simple+r'\iclip(100,100,500,200)'));checks+=1
    assert not vectors(ev(simple+r'\clip(m 100 100 l 500 100 500 200)'));checks+=1
    assert not vectors(ev(simple+r'\move(100,100,200,100)'));checks+=1
    assert not vectors(ev(simple+r'\t(\fscx200)'));checks+=1
    assert not vectors(ev(simple+r'\t(\frz90)'));checks+=1
    entered=vectors(ev(simple+r'\fscx1\fscy1\t(0,200,\fscx100\fscy100)'))
    assert len(entered)==1 and entered[0].state['fscx']==100;checks+=1
    assert not vectors(ev(simple+r'\fscx1\t(0,2000,\fscx100)'));checks+=1
    assert not vectors(ev(simple+r'\t(0,200,\fscx110)\t(400,600,\fscx100)'));checks+=1
    assert not vectors(ev(simple+r'\fax0.3'));checks+=1
    assert not vectors(ev(simple+r'\frx20'));checks+=1
    assert not vectors(ev(simple,'m 0 0 b 30 0 60 20 100 100'));checks+=1
    assert not vectors(ev(simple,'m 0 0 l 400 0 400 100 m 20 20 l 40 20 40 40'));checks+=1
    top=vectors(ev(simple+r'\1c&H0000FF&')+ev(simple+r'\1c&HFF0000&'))
    assert len(top)==1 and top[0].state['1c']=='FF0000';checks+=1
    shade=vectors(ev(simple+r'\1a&HFE&\3a&HFE&\xshad0.01\4c&H123456&'))
    assert len(shade)==1 and shade[0].state['1c']=='123456' and shade[0].state['1a']==0;checks+=1
    assert not vectors(ev(simple+r'\1a&HFE&\3a&HFE&\xshad10'));checks+=1
    faded=vectors(ev(simple+r'\1a&H80&'))
    assert faded[0].state['1a']==128;checks+=1
    caption=load(ev(r'\pos(300,150)','Hello',layer='2'))
    tiny=vectors(ev(r'\an7\pos(295,145)\p1','m 0 0 l 10 0 10 10 0 10'))
    assert not s.select_caption_supports(tiny,caption,measurement_fonts(metric))[0];checks+=1
    bg=vectors(ev(simple))
    assert len(s.select_caption_supports(bg,caption,measurement_fonts(metric))[0])==1;checks+=1
    # A jagged panel is reduced only with a bounded change to its own contour.
    # Retain its exact original outline as temporary containment evidence.
    points=[(x, (x//10)%3-1) for x in range(0,401,10)]
    points += [(400,100)]+[(x,100+(x//10)%3-1) for x in range(390,-1,-10)]
    raw='m '+' '.join(str(v) for v in points[0])+' l '+' '.join(str(v) for p in points[1:] for v in p)
    jagged=vectors(ev(simple,raw))
    assert len(jagged)==1 and 3<=len(s.drawing_polygon(jagged[0]))<=8
    assert len(jagged[0].evidence.original_contour_points)==len(points)
    assert len(s.select_caption_supports(jagged,caption,measurement_fonts(metric))[0])==1;checks+=1
    # Reconstructed enclosing paper panels become opaque without changing
    # their reduced contour or placement. Other translucent primitives remain.
    paper=vectors(ev(simple+r'\1a&H80&',raw))
    kept,_=s.select_caption_supports(paper,caption,measurement_fonts(metric))
    assert len(kept)==1 and kept[0].state['1a']==kept[0].state['2a']==0
    assert s.geometry_key(kept[0].text)==s.geometry_key(paper[0].text)
    assert s.get_pos(kept[0].text)==s.get_pos(paper[0].text)
    assert kept[0].evidence.original_contour_points is not None;checks+=1
    # Rectangle bias keeps source extents, but does not flatten clearly
    # angled silhouettes, rounded shapes or deep cut-outs.
    fitted=s.fit_rectangular_contour(points)
    assert fitted is not None and len(fitted)==4
    assert min(x for x,y in fitted)==min(x for x,y in points)
    assert max(y for x,y in fitted)==max(y for x,y in points);checks+=1
    assert s.fit_rectangular_contour([(0,0),(400,0),(390,100),(10,100)]) is not None;checks+=1
    assert s.fit_rectangular_contour([(0,0),(400,0),(340,100),(60,100)]) is None;checks+=1
    assert s.fit_rectangular_contour([(200,0),(400,50),(200,100),(0,50)]) is None;checks+=1
    assert s.fit_rectangular_contour([(0,0),(190,0),(190,50),(210,50),
                                       (210,0),(400,0),(400,100),(0,100)]) is None;checks+=1
    circle=[(50+50*s.math.cos(i*s.math.pi/32),50+50*s.math.sin(i*s.math.pi/32))
            for i in range(64)]
    assert s.fit_rectangular_contour(circle) is None;checks+=1
    # Existing simple quadrilaterals do not enter contour simplification.
    trapezoid='m 0 0 l 400 0 390 100 10 100'
    unchanged=vectors(ev(simple,trapezoid))
    assert s.geometry_key(unchanged[0].text)==s.geometry_key(trapezoid);checks+=1
    translucent_rectangle=vectors(ev(simple+r'\1a&H80&'))
    assert s.select_caption_supports(translucent_rectangle,caption,measurement_fonts(metric))[0][0].state['1a']==128;checks+=1
    arrow=vectors(ev(r'\an7\pos(340,145)\p1\bord0\shad0\1a&H80&',
                     'm 0 0 l 25 5 0 10',layer='3'))
    assert s.select_caption_supports(arrow,caption,measurement_fonts(metric))[0][0].state['1a']==128;checks+=1
    # A fitted outer polygon must not fill an originally cut-out text region.
    jagged[0].evidence=s.EventEvidence(((100,100),(500,100),(500,200),
        (320,200),(320,130),(280,130),(280,200),(100,200)))
    assert not s.select_caption_supports(jagged,caption,measurement_fonts(metric))[0];checks+=1
    lower=load(ev(simple)+ev(simple+r'\1c&H123456&',layer='1'))
    kept,_=s.select_caption_supports(lower,caption,measurement_fonts(metric))
    assert len(kept)==1 and kept[0].layer=='1';checks+=1
    assert not s.select_caption_supports(bg,caption,None)[0];checks+=1
    # Any actual overlap is enough for a geometrically proved backdrop.
    # Arrival delays and brief holds retain their original source timing.
    late=vectors(ev(simple,start='0:00:01.05'))
    kept,_=s.select_caption_supports(late,caption,measurement_fonts(metric))
    assert len(kept)==1 and kept[0].start=='0:00:01.05';checks+=1
    early_end=vectors(ev(simple,end='0:00:03.95'))
    kept,_=s.select_caption_supports(early_end,caption,measurement_fonts(metric))
    assert len(kept)==1 and kept[0].end=='0:00:03.95';checks+=1
    delayed=vectors(ev(simple,start='0:00:01.50'))
    kept,_=s.select_caption_supports(delayed,caption,measurement_fonts(metric))
    assert len(kept)==1 and kept[0].start=='0:00:01.50';checks+=1
    flash=vectors(ev(simple,end='0:00:01.10'))
    kept,_=s.select_caption_supports(flash,caption,measurement_fonts(metric))
    assert len(kept)==1 and kept[0].end=='0:00:01.10';checks+=1
    short_caption=load(ev(r'\pos(300,150)','Hello',layer='2',end='0:00:01.10'))
    partial=vectors(ev(simple,start='0:00:01.04',end='0:00:01.10'))
    assert len(s.select_caption_supports(partial,short_caption,measurement_fonts(metric))[0])==1;checks+=1
    no_overlap=vectors(ev(simple,start='0:00:04.00',end='0:00:05.00'))
    assert not s.select_caption_supports(no_overlap,caption,measurement_fonts(metric))[0];checks+=1
    above_text=vectors(ev(simple,layer='3'))
    assert not s.select_caption_supports(above_text,caption,measurement_fonts(metric))[0];checks+=1
    # A higher panel visible only in the middle of a caption cannot erase
    # the sole lower backdrop needed before and after that shared interval.
    intervals=vectors(ev(simple,layer='0')+
                      ev(simple+r'\1c&H123456&',layer='1',
                         start='0:00:02.00',end='0:00:03.00'))
    kept,_=s.select_caption_supports(intervals,caption,measurement_fonts(metric))
    assert len(kept)==2 and {e.layer for e in kept}=={'0','1'};checks+=1
    consecutive=vectors(ev(simple,layer='0',end='0:00:02.00')+
                        ev(simple+r'\1c&H123456&',layer='1',start='0:00:02.00'))
    kept,_=s.select_caption_supports(consecutive,caption,measurement_fonts(metric))
    assert len(kept)==2 and sorted((e.start,e.end) for e in kept)==[
        ('0:00:01.00','0:00:02.00'),('0:00:02.00','0:00:04.00')];checks+=1
    # A higher overlapping panel may support one caption, but cannot remove
    # the lower panel that is the only backdrop for a different caption.
    peers=vectors(ev(simple,layer='0')+
                  ev(r'\an7\pos(350,100)\p1\bord0\shad0',
                     'm 0 0 l 150 0 150 100 0 100',layer='1'))
    labels=load(ev(r'\pos(200,150)','Left',layer='2')+
                ev(r'\pos(425,150)','Right',layer='2'))
    kept,associated=s.select_caption_supports(peers,labels,measurement_fonts(metric))
    assert len(kept)==2 and all(associated[e.source_index] for e in kept);checks+=1
    p.write_text(header+ev(simple,start='0:00:01.50')+
                 ev(r'\pos(300,150)','Hello',layer='2'))
    recovered=Path(temp)/'late-panel.ass'
    s.simplify_ass(p,recovered,s.SimplifyConfig(),font_metrics=metric, font_report=font_test_report(metric))
    panel_out=[e for e in s.load_subtitle_events(recovered)[1] if e.state.get('p',0)]
    assert len(panel_out)==1 and panel_out[0].start=='0:00:01.50';checks+=1
    # Fullscreen backgrounds form a separate category: retain them alongside
    # the uppermost local panel, with the original source layers.
    fulltags=r'\an7\pos(0,0)\p1\bord0\shad0'
    fullraw='m 0 0 l 1920 0 1920 1080 0 1080'
    screen=vectors(ev(fulltags,fullraw))
    assert len(screen)==1 and s.is_fullscreen_background(screen[0]);checks+=1
    panel=vectors(ev(simple,layer='1'))
    kept,_=s.select_caption_supports(vectors(ev(fulltags,fullraw)+ev(simple,layer='1')),caption,measurement_fonts(metric))
    assert len(kept)==2 and {e.layer for e in kept}=={'0','1'};checks+=1
    two_panels=vectors(ev(fulltags,fullraw)+ev(simple,layer='1')+ev(simple+r'\1c&H123456&',layer='2'))
    kept,_=s.select_caption_supports(two_panels,
                                      load(ev(r'\pos(300,150)','Hello',layer='3')),measurement_fonts(metric))
    assert len(kept)==2 and {e.layer for e in kept}=={'0','2'};checks+=1
    assert len(s.select_caption_supports(screen,caption,None)[0])==1;checks+=1
    assert len(s.select_caption_supports(screen,[],None)[0])==1;checks+=1
    clipped=vectors(ev(fulltags+r'\clip(0,0,960,1080)',fullraw))
    assert not s.is_fullscreen_background(clipped[0]);checks+=1
    triangle=vectors(ev(fulltags,'m 0 0 l 1920 0 1920 1080'))
    assert not s.is_fullscreen_background(triangle[0]);checks+=1
    assert not s.is_fullscreen_background(panel[0]);checks+=1
    # Centre-left drawing alignment is normalized without changing its fill.
    centred=vectors(ev(r'\an4\pos(82,459)\p1\fscx50\fscy49',
                        'm 16 -147 l 624 -147 624 147 16 147'))
    assert centred[0].state['an']==7
    assert s.get_pos(centred[0].text)==(82,386.97);checks+=1
    bordered=load(ev(r'\an4\pos(82,459)\p1\fscx50\fscy49\bord20\1c&H3D535F&\3c&H3D535F&',
                     'm 16 -147 l 624 -147 624 147 16 147'))[0]
    flattened=s.flatten_rectangular_border(bordered)
    bounds=s.coverage_geometry(flattened)[1]
    assert abs(bounds[0]-68)<.001 and abs(bounds[1]-292.94)<.001
    assert abs(bounds[2]-416)<.001 and abs(bounds[3]-481)<.001;checks+=1
    assert s.flatten_rectangular_border(bordered,scaled_borders=False) is bordered;checks+=1
    # Also retain a standalone background through the complete write path.
    p.write_text(header+ev(fulltags,fullraw))
    standalone=Path(temp)/'standalone.ass'
    stats=s.simplify_ass(p,standalone,s.SimplifyConfig(),font_metrics=None, font_report=font_test_report(None))
    assert stats['fullscreen_backgrounds_retained']==1
    assert len(s.load_subtitle_events(standalone)[1])==1;checks+=1
    fakegrain=load(ev(r'\an7\pos(0,0)\fnArial','This is ordinary text\\NThis is ordinary text\\NThis is ordinary text'))[0]
    assert not s.is_font_texture(fakegrain,measurement_fonts(metric));checks+=1
    realgrain=load(ev(r'\an7\pos(0,0)\fnGrain','ahdshdahdshd\\Nahdshdahdshd\\Nahdshdahdshd'))[0]
    assert s.is_font_texture(realgrain,measurement_fonts(metric));checks+=1
    # Meaningful changing values stay separate; missing-font backdrops keep
    # the existing baseline result instead of disappearing.
    for use_metric in [metric,None]:
        p.write_text(header+ev(simple)+ev(r'\pos(300,150)','300/300','2',end='0:00:02.00')+
                     ev(r'\pos(300,150)','400/400','2',start='0:00:02.00'))
        old=Path(temp)/'old.ass';new=Path(temp)/'new.ass'
        s._simplify_text_and_vectors(p,old,s.SimplifyConfig(),font_metrics=use_metric, font_report=font_test_report(use_metric))
        s.simplify_ass(p,new,s.SimplifyConfig(),font_metrics=use_metric, font_report=font_test_report(use_metric))
        oldtexts=[e.fields() for e in s.load_subtitle_events(old)[1] if e.kind=='Dialogue' and not e.state.get('p',0)]
        newtexts=[e.fields() for e in s.load_subtitle_events(new)[1] if e.kind=='Dialogue' and not e.state.get('p',0)]
        assert oldtexts==newtexts
        assert any(e.state.get('p',0) for e in s.load_subtitle_events(new)[1]);checks+=1
    p.write_text(header+ev(simple))
    old=Path(temp)/'old2.ass';new=Path(temp)/'new2.ass'
    s._simplify_text_and_vectors(p,old,s.SimplifyConfig(level=2),font_metrics=metric, font_report=font_test_report(metric))
    s.simplify_ass(p,new,s.SimplifyConfig(level=2),font_metrics=metric, font_report=font_test_report(metric))
    assert old.read_bytes()==new.read_bytes();checks+=1
    # The original encoding is honored; the temporary baseline is always UTF-8.
    p.write_bytes((header+ev(simple)+ev(r'\pos(300,150)','Caf\xe9','2')).encode('cp1252'))
    s.simplify_ass(p,new,s.SimplifyConfig(encoding='cp1252'),font_metrics=metric, font_report=font_test_report(metric))
    assert 'Caf\xe9' in new.read_text(encoding='utf-8-sig');checks+=1
    assert s.script_resolution(['PlayResY: bad'],'y')==288
    assert s.script_resolution(['PlayResX: nan'],'x')==384;checks+=1
    p.write_text(header+ev(simple)+ev(r'\pos(300,150)','Hello','2')+
                 ev(r'\an7\pos(100,300)\p1\bord0\shad0')+
                 ev(r'\pos(300,350)','World','2'))
    stats=s.simplify_ass(p,new,s.SimplifyConfig(max_vectors_per_cue=1),font_metrics=metric, font_report=font_test_report(metric))
    assert stats['vector_output']==1 and stats['drawing_events_capped']==1;checks+=1
    stats=s.simplify_ass(p,new,s.SimplifyConfig(max_drawing_chars=10),font_metrics=metric, font_report=font_test_report(metric))
    assert stats['vector_output']==0;checks+=1
    p.write_text(header+ev(r'\pos(300,150)','Hello','2')+
                 ev(r'\an7\pos(340,145)\p1\bord0\shad0','m 0 0 l 25 5 0 10','3'))
    s._simplify_text_and_vectors(p,old,s.SimplifyConfig(),font_metrics=metric, font_report=font_test_report(metric))
    stats=s.simplify_ass(p,new,s.SimplifyConfig(),font_metrics=metric, font_report=font_test_report(metric))
    oldtexts=[e.fields() for e in s.load_subtitle_events(old)[1] if e.kind=='Dialogue' and not e.state.get('p',0)]
    newtexts=[e.fields() for e in s.load_subtitle_events(new)[1] if e.kind=='Dialogue' and not e.state.get('p',0)]
    assert stats['vector_output']==1 and oldtexts==newtexts;checks+=1
    # A masked solid can be the actual caption; its unmasked faint copy is a
    # glow, even when both have precisely the same text layout and lifetime.
    mask='m 100 100 l 500 120 490 220 110 200'
    pose=r'\pos(300,150)\frz343.8\frx1.77\fry1.84\fax0.18\q2'
    solid=load(ev(pose+r'\clip('+mask+')','Sword Mastery III','2'))
    faint=load(ev(pose+r'\1a&HD2&','Sword Mastery III','3'))
    fixed,count=s.restore_masked_caption_foregrounds(solid,faint)
    assert count==1 and fixed[0].state['1a']==0 and fixed[0].layer=='2'
    assert fixed[0].state['clip']==solid[0].state['clip'];checks+=1
    assert s.text_layout_key(fixed[0])==s.text_layout_key(faint[0]);checks+=1
    # Shared mask/drawing contours prove an authored association, without
    # pretending to measure perspective lettering or dropping its clipping.
    backing=vectors(ev(r'\an7\pos(0,0)\p1\bord0\shad0',mask,'1'))
    assert s.caption_bounds(fixed[0],measurement_fonts(metric)) is None
    assert len(s.select_caption_supports(backing,fixed,measurement_fonts(metric))[0])==1;checks+=1
    assert len(s.select_caption_supports(backing,fixed,None)[0])==1;checks+=1
    elsewhere=vectors(ev(r'\an7\pos(1000,0)\p1\bord0\shad0',mask,'1'))
    assert not s.select_caption_supports(elsewhere,fixed,measurement_fonts(metric))[0];checks+=1
    different=vectors(ev(r'\an7\pos(0,0)\p1\bord0\shad0',mask.replace('490','480'),'1'))
    assert not s.select_caption_supports(different,fixed,measurement_fonts(metric))[0];checks+=1
    foreground=vectors(ev(r'\an7\pos(0,0)\p1\bord0\shad0',mask,'4'))
    assert not s.select_caption_supports(foreground,fixed,measurement_fonts(metric))[0];checks+=1
    separate=vectors(ev(r'\an7\pos(0,0)\p1\bord0\shad0',mask,'1',start='0:00:04.00',end='0:00:05.00'))
    assert not s.select_caption_supports(separate,fixed,measurement_fonts(metric))[0];checks+=1
    for changed in [ev(pose,'Sword Mastery III','3'),
                    ev(pose+r'\1a&HD2&','Sword Mastery IV','3'),
                    ev(pose+r'\1a&HD2&\1c&H0000FF&','Sword Mastery III','3'),
                    ev(pose+r'\1a&HD2&\fs60','Sword Mastery III','3'),
                    ev(pose+r'\1a&HD2&','Sword Mastery III','3',end='0:00:05.00')]:
        assert s.restore_masked_caption_foregrounds(solid,load(changed))[1]==0;checks+=1
    ambiguous=solid+load(ev(pose+r'\clip('+mask.replace('490','480')+')','Sword Mastery III','2'))
    assert s.restore_masked_caption_foregrounds(ambiguous,faint)[1]==0;checks+=1
    animated=load(ev(pose+r'\clip('+mask+r')\t(\1a&H80&)','Sword Mastery III','2'))
    assert s.restore_masked_caption_foregrounds(animated,faint)[1]==0;checks+=1
    # Scaled clip coordinates denote the same scene contour.
    doubled='m 200 200 l 1000 240 980 440 220 400'
    scaled=load(ev(pose+r'\clip(2,'+doubled+')','Sword Mastery III','2'))
    assert s.caption_clip_outline(scaled[0])==s.caption_clip_outline(solid[0]);checks+=1
    assert len(s.select_caption_supports(backing,scaled,measurement_fonts(metric))[0])==1;checks+=1
    p.write_text(header+ev(r'\an7\pos(0,0)\p1\bord0\shad0',mask,'1')+
                 ev(pose+r'\clip('+mask+')','Sword Mastery III','2')+
                 ev(pose+r'\1a&HD2&\blur6','Sword Mastery III','3'))
    stats=s.simplify_ass(p,new,s.SimplifyConfig(),font_metrics=metric, font_report=font_test_report(metric))
    generated=s.load_subtitle_events(new)[1]
    assert stats['masked_foregrounds_restored']==1
    assert len(generated)==2 and generated[0].state.get('p')==1
    assert generated[1].state['1a']==0 and generated[1].layer=='2'
    assert generated[1].state['clip']==solid[0].state['clip'];checks+=1
    # A held panel with a short shrinking exit is static for most of its cue.
    # Keep the exact original scale, not the tiny exit target.
    leaving=vectors(ev(simple+r'\fscx104\fscy104\t(2700,3000,\fscx25\fscy25)'))
    assert len(leaving)==1 and leaving[0].state['fscx']==104 and leaving[0].state['fscy']==104;checks+=1
    assert len(vectors(ev(simple+r'\t(2700,3018,\fscx3\fscy4)')))==1;checks+=1
    one_axis=vectors(ev(simple+r'\t(2700,3000,\fscx25)'))
    assert len(one_axis)==1 and one_axis[0].state['fscy']==100;checks+=1
    for change in [r'\t(0,3000,\fscx25\fscy25)',
                   r'\t(2399,3000,\fscx25\fscy25)',
                   r'\t(2700,2949,\fscx25\fscy25)',
                   r'\t(2700,3051,\fscx25\fscy25)',
                   r'\t(2700,3000,\fscx125\fscy125)',
                   r'\t(2700,3000,\fscx0\fscy0)',
                   r'\t(2700,3000,\fscx25\frz90)',
                   r'\t(2700,3000,-1,\fscx25\fscy25)']:
        assert not vectors(ev(simple+change));checks+=1
    # Short scale entrances and exits can share a long stable middle pose.
    paired = simple+r'\fscx30\fscy20\t(0,80,\fscx100\fscy100)\t(2850,2980,\fscx30,\fscy30)'
    middle_pose=vectors(ev(paired))
    assert len(middle_pose)==1 and middle_pose[0].state['fscx']==middle_pose[0].state['fscy']==100;checks+=1
    stretched=vectors(ev(simple+r'\fscx20\fscy30\t(0,80,\fscx101\fscy132)\t(2850,2980,\fscx20,\fscy30)'))
    assert len(stretched)==1 and (stretched[0].state['fscx'],stretched[0].state['fscy'])==(101,132);checks+=1
    assert len(vectors(ev(simple+r'\t(0,200,\fscx120)\t(2700,3000,\fscx25)')))==1;checks+=1
    for change in [r'\t(0,200,\fscx120)\t(2400,3000,\fscx25)',
                   r'\t(0,200,\fscx120)\t(2700,2949,\fscx25)',
                   r'\t(100,200,\fscx120)\t(2700,3000,\fscx25)',
                   r'\t(0,200,\fscx120)\t(2700,3000,\fscx125)',
                   r'\t(0,200,\fscx120)\t(2700,3000,\fscx0)',
                   r'\t(0,200,\fscx120)\t(2700,3000,\fscx25oops)',
                   r'\t(0,200,\fscx120)\t(2700,3000,\fscx25,,)',
                   r'\t(0,200,\fscx120)\t(2700,3000,\fscx25\frz90)',
                   r'\t(0,200,\fscx120)\t(1000,1100,\fscx110)\t(2700,3000,\fscx25)']:
        assert not vectors(ev(simple+change));checks+=1
    # A small amount of literal text still establishes support for a large
    # panel. A front panel overlapping its upper area cannot erase it.
    middle=vectors(ev(r'\an7\pos(400,200)\p1\bord0\shad0',
                      'm 0 0 l 900 0 900 600 0 600','1')+
                   ev(r'\an7\pos(300,250)\p1\bord0\shad0',
                      'm 0 0 l 800 0 800 480 0 480','8'))
    bottom=load(ev(r'\pos(600,770)','Hi','2'))
    kept,_=s.select_caption_supports(middle,bottom,measurement_fonts(metric))
    assert any(e.layer=='1' for e in kept);checks+=1
    # The opaque shadow supplies these captions' visible glyphs. Its offset
    # moves the ink; it is not clearance to add on all sides of a primary box.
    white=load(ev(r'\pos(299.99,150)','Vigilance','2'))
    shadow=load(ev(r'\pos(300,150)\1a&HFE&\xshad-0.01\4c&HFFFFFF&','Vigilance','2'))
    assert s.caption_bounds(white[0],measurement_fonts(metric))==s.caption_bounds(shadow[0],measurement_fonts(metric));checks+=1
    bad=load(ev(r'\pos(300,150)\fscx5\1a&HFE&\xshad-75\4c&HFFFFFF&'
                r'\t(0,100,\xshad-0.01,\fscx100)','Vigilance','2'))
    baseline=load(ev(r'\pos(300,150)\1a&HFE&\xshad-75\4c&HFFFFFF&','Vigilance','2'))
    fixed,count=s.repair_caption_shadow_offsets(bad,baseline)
    assert count==1 and fixed[0].state['xshad']==-.01
    assert fixed[0].state['1a']==254 and fixed[0].state['4c']=='FFFFFF';checks+=1
    assert s.caption_bounds(fixed[0],measurement_fonts(metric))==s.caption_bounds(white[0],measurement_fonts(metric));checks+=1
    other=load(ev(r'\pos(300,150)\1a&HFE&\xshad-75\4c&HFFFFFF&','Other caption','2'))
    assert s.repair_caption_shadow_offsets(bad,other)[1]==0;checks+=1
    opaque=load(ev(r'\pos(300,150)\xshad-75\4c&HFFFFFF&','Vigilance','2'))
    assert s.repair_caption_shadow_offsets(bad,opaque)[1]==0;checks+=1
    # Short explicitly timed entrances may move a panel, then hold it still.
    moving=r'\an7\move(50,50,100,100,64,105)\p1\bord0\shad0'
    moved=vectors(ev(moving))
    assert len(moved)==1 and s.get_pos(moved[0].text)==(100,100);checks+=1
    entered=vectors(ev(moving+r'\fscx1\t(0,105,\fscx100)'))
    assert len(entered)==1 and entered[0].state['fscx']==100;checks+=1
    for motion in [r'\move(50,50,100,100)',r'\move(50,50,100,100,0,601)',
                   r'\move(50,50,100,100,601,700)',r'\move(50,50,100,100,105,64)',
                   r'\move(50,50,100,100,0,0)']:
        assert not vectors(ev(r'\an7\p1\bord0\shad0'+motion));checks+=1
    # Several similarly coloured curved erasure patches can reconstruct one
    # backing around a measured caption. Keep unrelated contours out of it.
    patch=r'\an7\pos(0,0)\p1\bord0\shad0.01\1a&HFE&\3a&HFE&\4c&H99AABB&'
    def curved(x0,x1):
        return f'm {x0} 120 b {x0} 120 {x1} 120 {x1} 120 l {x1} 180 {x0} 180'
    fragments=load(''.join(ev(patch,curved(x0,x1),'1') for x0,x1 in [(240,280),(270,320),(310,360)]))
    caption=load(ev(r'\pos(300,150)','Hello','2'))
    combined=s.reconstruct_composite_backdrops(fragments,caption,measurement_fonts(metric))
    assert len(combined)==1 and combined[0].state['1c']=='99AABB' and combined[0].state['1a']==0;checks+=1
    assert len(s.select_caption_supports(combined,caption,measurement_fonts(metric))[0])==1;checks+=1
    assert not s.reconstruct_composite_backdrops(fragments,caption,None);checks+=1
    assert not s.reconstruct_composite_backdrops(fragments[:2],caption,measurement_fonts(metric));checks+=1
    unrelated=load(ev(patch,curved(1000,1200),'1'))
    assert s.reconstruct_composite_backdrops(fragments+unrelated,caption,measurement_fonts(metric))[0].text==combined[0].text;checks+=1
    # A distant separator inside the same raw drawing is measured separately.
    multi=load(ev(patch,curved(240,280)+' m 0 500 b 0 500 1920 500 1920 500 l 1920 510 0 510','1'))
    assert s.reconstruct_composite_backdrops(multi+fragments[1:],caption,measurement_fonts(metric))[0].text==combined[0].text;checks+=1
    foreground=load(''.join(ev(patch,curved(x0,x1),'3') for x0,x1 in [(240,280),(270,320),(310,360)]))
    assert not s.reconstruct_composite_backdrops(foreground,caption,measurement_fonts(metric));checks+=1
    animated=load(''.join(ev(patch+r'\t(0,100,\fscx200)',curved(x0,x1),'1') for x0,x1 in [(240,280),(270,320),(310,360)]))
    assert not s.reconstruct_composite_backdrops(animated,caption,measurement_fonts(metric));checks+=1
    contrasting=load(ev(patch+r'\4c&H000000&',curved(310,360),'1'))
    assert not s.reconstruct_composite_backdrops(fragments[:2]+contrasting,caption,measurement_fonts(metric));checks+=1

    # Review regressions: literal single-glyph captions need support too.
    for literal in ('9', 'A'):
        one=load(ev(r'\pos(300,150)',literal,'2'))
        assert len(s.select_caption_supports(vectors(ev(simple)),one,measurement_fonts(metric))[0])==1;checks+=1
    # Soft breaks are spaces except with q2; hard breaks always split lines.
    soft=load(ev(r'\pos(300,150)',r'Hello\nWorld','2'))[0]
    space=s.replace_event(soft,text=soft.text.replace(r'\n',' '))
    hard=s.replace_event(soft,text=soft.text.replace(r'\n',r'\N'))
    split=s.replace_event(soft,text=r'{\q2}'+soft.text)
    assert s.caption_bounds(soft,measurement_fonts(metric))==s.caption_bounds(space,measurement_fonts(metric));checks+=1
    assert s.caption_bounds(split,measurement_fonts(metric))==s.caption_bounds(hard,measurement_fonts(metric));checks+=1
    assert s.caption_bounds(soft,measurement_fonts(metric))[2]-s.caption_bounds(soft,measurement_fonts(metric))[0] > s.caption_bounds(hard,measurement_fonts(metric))[2]-s.caption_bounds(hard,measurement_fonts(metric))[0];checks+=1
    p.write_text(header.replace('ScriptType: v4.00+', 'ScriptType: v4.00+\nWrapStyle: 2')+
                 ev(r'\pos(300,150)',r'Hello\nWorld','2'))
    global_split=s.load_subtitle_events(p)[1][0]
    assert s.caption_bounds(global_split,measurement_fonts(metric))==s.caption_bounds(hard,measurement_fonts(metric));checks+=1
    global_space=s.replace_event(global_split,text=r'{\q0}'+global_split.text)
    assert s.caption_bounds(global_space,measurement_fonts(metric))==s.caption_bounds(space,measurement_fonts(metric));checks+=1
    # Validate the actual comma-terminated scale, including invalid exits.
    assert len(vectors(ev(simple+r'\t(2700,3000,\fscx25,\fscy25)')))==1;checks+=1
    for target in ('0,','125,','25oops','25,,'):
        assert not vectors(ev(simple+r'\t(2700,3000,\fscx'+target+r'\fscy25)'));checks+=1
    assert not vectors(ev(simple,r'm 0 0 l 400 0 400 100 {\fscx50}l 0 100'));checks+=1
    # Repeated coincident clipped fills are composed before strip averaging.
    clip=simple+r'\clip(100,100,500,200)'
    duplicate=vectors(ev(clip)+ev(clip))
    assert len(duplicate)==1 and duplicate[0].state['1a']==0;checks+=1
    transparent=vectors(ev(clip+r'\1a&H80&')+ev(clip+r'\1a&H80&'))
    assert len(transparent)==1 and transparent[0].state['1a']==64;checks+=1
    gradient=vectors(ev(simple+r'\clip(100,100,300,200)\1c&H0000FF&')+
                     ev(simple+r'\clip(100,100,300,200)\1c&HFF0000&')+
                     ev(simple+r'\clip(300,100,500,200)\1c&H00FF00&'))
    assert len(gradient)==1 and gradient[0].state['1c']=='808000';checks+=1
    # Complete-path fallback: another caption's known font cannot remove the
    # support of unknown-font text elsewhere in the same sign style.
    p.write_text(header+ev(simple)+ev(r'\pos(300,150)\fnMissing Font','Hello','2')+
                 ev(r'\pos(1000,650)','Elsewhere','2'))
    old=Path(temp)/'mixed-old.ass';new=Path(temp)/'mixed-new.ass'
    s._simplify_text_and_vectors(p,old,s.SimplifyConfig(),font_metrics=metric, font_report=font_test_report(metric))
    stats=s.simplify_ass(p,new,s.SimplifyConfig(),font_metrics=metric, font_report=font_test_report(metric))
    assert stats['vector_output']==1 and stats['unmeasured_backdrops_retained']==1;checks+=1
    oldvectors=[e.fields() for e in s.load_subtitle_events(old)[1] if e.state.get('p',0)]
    newvectors=[e.fields() for e in s.load_subtitle_events(new)[1] if e.state.get('p',0)]
    assert oldvectors==newvectors;checks+=1
    # A shared masked caption selects its panel even without text bounds.
    # The equal baseline rectangle must not then appear a second time.
    rect='m 100 100 l 500 100 500 200 100 200'
    for use_metric in (metric,None):
        p.write_text(header+ev(r'\an7\pos(0,0)\p1\bord0\shad0',rect,'1')+
                     ev(r'\pos(300,150)\clip('+rect+')','Hello','2'))
        stats=s.simplify_ass(p,new,s.SimplifyConfig(),font_metrics=use_metric, font_report=font_test_report(use_metric))
        assert stats['vector_output']==1 and stats['unmeasured_backdrops_retained']==0;checks+=1
    # Equal fills may use different anchors, contour starts and direction.
    base=load(ev(r'\an7\pos(100,100)\p1\bord0\shad0'))
    other=vectors(ev(r'\an7\pos(0,0)\p1\bord0\shad0',
                     'm 500 200 l 500 100 100 100 100 200'))
    assert not s.retain_unmeasured_backdrops(base,[],other,None);checks+=1
    for changed in (s.replace_event(base[0],layer='1'),
                    s.replace_event(base[0],text=base[0].text.replace('400 100','399 100')),
                    s.replace_event(base[0],text=r'{\1c&H0000FF&}'+base[0].text),
                    s.replace_event(base[0],text=base[0].text.replace(r'\shad0',r'\shad0\xshad10')),
                    s.replace_event(base[0],end='0:00:05.00',end_s=5)):
        assert len(s.retain_unmeasured_backdrops([changed],[],other,None))==1;checks+=1
    # Promoted outputs retain one normal marker under case-insensitive
    # Script Info parsing, without an experimental release comment.
    p.write_text(header.replace('[Script Info]','[script info]')+ev(simple)+ev(r'\pos(300,150)','Hello','2'))
    s.simplify_ass(p,new,s.SimplifyConfig(),font_metrics=metric, font_report=font_test_report(metric))
    rendered=new.read_text(encoding='utf-8-sig')
    assert rendered.count(s.GENERATED_MARKER)==1 and "Static vector support prototype" not in rendered;checks+=1

    # Collective scrolling: source frames are tested before v100 can freeze
    # them. All thresholds are relative to PlayRes, with actual font evidence.
    def scroll_frames(labels=('One','Two','Three'), distance=700, duration=2,
                      positions=(300,550,1200), horizontal=False, reverse=(), extra='', origins=False):
        data='';n=round(duration/.05)
        for row,literal in enumerate(labels):
            for i in range(n):
                at=1+i*.05
                moving=positions[row]+((-1 if row not in reverse else 1)*distance*i/(n-1))
                x,y=(moving,100+row*200) if horizontal else (400,moving)
                origin=fr'\org({x:g},{y:g})' if origins else ''
                data+=ev(fr'\an5\pos({x:g},{y:g})'+origin+extra,literal,'2',s.format_time(at),s.format_time(at+.05))
        return data
    def drop(data,x=1920,y=1080,font=measurement_fonts(metric)):
        original=load(data)
        # A deliberately low limit exercises the motion/edge classifier.
        return original,*s.drop_overloaded_scrolling_blocks(original,x,y,font,concurrency_limit=1)
    scroll=scroll_frames()
    original,kept,report=drop(scroll)
    assert not kept and len(report)==1;checks+=1
    # Two spatial lines, even with many coincident paint variants, are not three.
    pairs=scroll_frames(labels=('One','Two'),positions=(300,550))
    assert len(drop(pairs)[1])==80;checks+=1
    duplicate=pairs+pairs.replace(r'\an5',r'\1c&H0000FF&\an5')
    assert len(drop(duplicate)[1])==160;checks+=1
    # Half-screen travel, one second, direction and edge evidence are all needed.
    assert len(drop(scroll_frames(distance=400))[1])==120;checks+=1
    assert len(drop(scroll_frames(duration=.8))[1])==48;checks+=1
    assert len(drop(scroll_frames(reverse=(2,)))[1])==120;checks+=1
    assert len(drop(scroll_frames(distance=540,positions=(850,900,980)))[1])==120;checks+=1
    assert len(drop(scroll,font=None)[1])==120;checks+=1
    assert len(drop(scroll_frames(extra=r'\frx40'))[1])==120;checks+=1
    changing_origins=scroll.replace(r'\an5',r'\frz180\org(400,300)\an5')
    assert len(drop(changing_origins)[1])==120;checks+=1
    assert len(drop(scroll_frames(extra=r'\clip(0,0,1920,1080)'))[1])==120;checks+=1
    # Outside anchors are insufficient when the glyphs still cover the edge.
    assert len(drop(scroll_frames(extra=r'\fs1200'))[1])==120;checks+=1
    # Near-coincident moving captions cannot pose as three independent rows.
    assert len(drop(scroll_frames(positions=(300,301,302)))[1])==120;checks+=1
    incoherent=scroll_frames(labels=('One','Two'),positions=(300,550))
    incoherent+=scroll_frames(labels=('Three',),positions=(1200,),distance=1400)
    assert len(drop(incoherent)[1])==120;checks+=1
    assert len(drop(scroll_frames(extra=r'\t(\fs50)'))[1])==120;checks+=1
    # Paint-only spans may travel; changing inline fonts/layout are unproved.
    painted=scroll.replace('One','O{\\1c&H0000FF&}ne')
    assert not drop(painted)[1];checks+=1
    inline=scroll.replace('One','O{\\fs80}ne')
    assert len(drop(inline)[1])==120;checks+=1
    # An unrelated stationary cue, even with the same literal text, survives.
    static=ev(r'\pos(1500,800)','One','2')
    assert [s.OVERRIDE_RE.sub('',e.text) for e in drop(scroll+static)[1]]==['One'];checks+=1
    # Same words in separate spatial rows are separate tracks, not global text deletion.
    repeated=scroll_frames(labels=('Repeated',)*3)
    assert not drop(repeated)[1];checks+=1
    # Small motion and single travelling captions are never dropped.
    assert len(drop(scroll_frames(distance=2))[1])==120;checks+=1
    assert len(drop(scroll_frames(labels=('Solo',),positions=(300,)))[1])==40;checks+=1
    # A disconnected copy of the same literal remains outside the scroll block.
    disconnected=scroll_frames(labels=('One',),distance=2,positions=(700,)).replace('0:00:01.','0:00:10.').replace('0:00:02.','0:00:11.').replace('0:00:03.','0:00:12.')
    assert len(drop(scroll+disconnected)[1])==40;checks+=1
    # Horizontal scrolling uses width, including a small-resolution subtitle.
    assert not drop(scroll_frames(distance=1250,positions=(400,800,2100),horizontal=True))[1];checks+=1
    small=scroll_frames(distance=200,positions=(90,150,340)).replace('\\pos(400,','\\pos(100,')
    assert not drop(small,x=640,y=360)[1];checks+=1
    # A pause/missing frames breaks the track; no bridging an arbitrary gap.
    gap=scroll_frames().replace('0:00:02.','0:00:04.').replace('0:00:03.','0:00:05.')
    assert len(drop(gap)[1])==120;checks+=1
    # Ordinary reduction must run first. These ordinary frames reduce to
    # three captions; even a low fallback limit cannot erase their text.
    p.write_text(header+scroll+ev(r'\pos(1500,800)','Unrelated','2'))
    stats=s.simplify_ass(p,new,s.SimplifyConfig(),font_metrics=metric, font_report=font_test_report(metric))
    assert stats['scrolling_events_dropped']==0 and stats['output']==4;checks+=1
    assert stats['original']==121 and stats['scrolling_blocks_dropped']==0;checks+=1
    assert {s.OVERRIDE_RE.sub('',e.text) for e in s.load_subtitle_events(new)[1]}=={'One','Two','Three','Unrelated'};checks+=1
    stats=s.simplify_ass(p,new,s.SimplifyConfig(scroll_concurrency_limit=2),font_metrics=metric, font_report=font_test_report(metric))
    assert stats['scrolling_events_dropped']==0 and stats['output']==4;checks+=1

    # Concurrency, not the number of successive frames, controls removal.
    residual=load(scroll_frames(duration=5,origins=True))
    kept,report=s.drop_overloaded_scrolling_blocks(residual,1920,1080,measurement_fonts(metric))
    assert len(kept)==300 and report[0]['peak_concurrent']==3 and report[0]['action']=='retained';checks+=1
    stationary=load(''.join(ev(r'\pos(1500,800)',f'Unrelated {i}','2') for i in range(80)))
    # Give each unrelated cue its own document index when combining fixtures.
    stationary=[s.dataclass_replace(e,source_index=e.source_index+10000) for e in stationary]
    kept,report=s.drop_overloaded_scrolling_blocks(residual+stationary,1920,1080,measurement_fonts(metric))
    assert len(kept)==380 and report[0]['peak_concurrent']==3;checks+=1
    # Exact limit remains; only a genuinely excessive residual block is dropped.
    crowded=scroll_frames(labels=tuple(f'Row {i}' for i in range(33)),
                         positions=tuple(300+60*i for i in range(33)),origins=True)
    crowded_events=load(crowded)
    kept,report=s.drop_overloaded_scrolling_blocks(crowded_events,1920,1080,measurement_fonts(metric),concurrency_limit=33)
    assert len(kept)==1320 and report[0]['peak_concurrent']==33 and report[0]['action']=='retained';checks+=1
    kept,report=s.drop_overloaded_scrolling_blocks(crowded_events,1920,1080,measurement_fonts(metric))
    assert not kept and report[0]['action']=='removed';checks+=1
    kept,report=s.drop_overloaded_scrolling_blocks(crowded_events,1920,1080,measurement_fonts(metric),concurrency_limit=0)
    assert len(kept)==1320 and report[0]['action']=='retained';checks+=1
    # Nonmoving identical words and unrelated effects survive the fallback.
    p.write_text(header+crowded+static)
    stats=s.simplify_ass(p,new,s.SimplifyConfig(),font_metrics=metric, font_report=font_test_report(metric))
    assert stats['scrolling_events_dropped']==1320 and stats['output']==1;checks+=1
    assert stats['scrolling_peak_after_reduction']==33 and stats['scrolling_blocks_dropped']==1;checks+=1
    assert s.OVERRIDE_RE.sub('',s.load_subtitle_events(new)[1][0].text)=='One';checks+=1
    # A high source peak that reduces safely below the limit cannot trigger it.
    p.write_text(header+s.re.sub(r'\\org\([^)]*\)', '', crowded)+static)
    stats=s.simplify_ass(p,new,s.SimplifyConfig(),font_metrics=metric, font_report=font_test_report(metric))
    assert stats['scrolling_events_dropped']==0 and stats['output']==34;checks+=1
    # Many redundant copies reduce to three moving rows. Compare the residual
    # peak, not the source peak (36), and preserve all three moving rows.
    tracked=scroll_frames(origins=True)
    p.write_text(header+tracked*12)
    stats=s.simplify_ass(p,new,s.SimplifyConfig(),font_metrics=metric, font_report=font_test_report(metric))
    assert stats['max_concurrent_in']==36 and stats['scrolling_peak_after_reduction']==3;checks+=1
    assert stats['scrolling_events_dropped']==0 and stats['output']==120;checks+=1
    p.write_text(header+crowded+static)
    stats=s.simplify_ass(p,new,s.SimplifyConfig(scroll_concurrency_limit=0),font_metrics=metric, font_report=font_test_report(metric))
    assert stats['scrolling_events_dropped']==0 and stats['output']==1321;checks+=1
    # Production legacy simplification delegates without this exclusion.
    stats=s.simplify_ass(p,new,s.SimplifyConfig(level=2),font_metrics=metric, font_report=font_test_report(metric))
    assert 'scrolling_events_dropped' not in stats and stats['output']>1;checks+=1

    # Multi-contour panels: only tiny attached exterior triangles may be
    # detached. Neither contained holes nor filled overlaps can become panels.
    main='m 0 0 l 400 0 400 100 0 100'
    for triangle in ['m 0 40 l -2 41 -2 39', 'm 0 40 l -2 39 -2 41']:
        events=load(ev(simple,main+' '+triangle))
        detached,count=s.detach_drawing_edge_slivers(events[0])
        assert count==1 and s.geometry_key(detached.text)==s.geometry_key(main);checks+=1
        kept,_=s.select_caption_supports(s.reduce_supporting_drawings(events)[0],caption,measurement_fonts(metric))
        assert len(kept)==1;checks+=1
    for extra in [
        'm 1 40 l 3 41 3 39',  # contained tiny hole, either orientation
        'm 1 40 l 3 39 3 41',
        'm 0 40 l 2 41 2 39',  # attached but inside the panel
        'm 0 40 l 2 41 -2 39', # straddling the boundary
        'm -1 40 l -3 41 -3 39', # separate decoration
        'm 0 40 l -20 50 -20 30', # excessive footprint
        'm 0 40 l -2 41 -3 40 -2 39', # not a triangle
        'm 0 40 b -2 41 -2 39 0 40', # curve
    ]:
        events=load(ev(simple,main+' '+extra))
        detached,count=s.detach_drawing_edge_slivers(events[0])
        assert count==0 and detached.text==events[0].text;checks+=1
        assert not s.reduce_supporting_drawings(events)[0];checks+=1
    # A crossing triangle can have all three vertices outside the fill.
    # The segment-partition test must still reject its overlap.
    events=load(ev(simple,main+' m 0 0 l 2 -1 -1 2'))
    assert s.detach_drawing_edge_slivers(events[0])[1]==0;checks+=1
    # A substantial second panel cannot be treated as an edge sliver.
    events=load(ev(simple,main+' m 400 0 l 800 0 800 100 400 100'))
    assert s.detach_drawing_edge_slivers(events[0])[1]==0;checks+=1

    # Animated glyphs painted only by their shadow use a wider layer below
    # the thin foreground stroke for colour. No palette value is privileged.
    def shadow_stack(contour, fill='FFFFFF', *, extra='', thin='.25', border='3.4'):
        tags=r'\an5\pos(300,150)\1a&HFE&\3a&HFE&\4a&H00&\xshad-.01\yshad.01'
        events=load(extra+ev(tags+rf'\4c&H{contour}&\bord{border}','Hi',layer='3')+
                    ev(tags+rf'\4c&H{fill}&\bord{thin}','Hi',layer='4'))
        visible={e.source_index:'Hi' for e in events}
        out,removed=s.flatten_stacked_text_copies(events,visible,{e.source_index for e in events})
        return out,removed
    for color in ['3F29CA','CA293F','008000']:
        out,removed=shadow_stack(color)
        assert removed==1 and len(out)==1;checks+=1
        assert out[0].state['1c']=='FFFFFF' and out[0].state['3c']==color;checks+=1
        assert out[0].state['1a']==out[0].state['3a']==0 and out[0].state['bord']==2
        assert out[0].state['shad']==0 and out[0].state.get('blur',0)==0;checks+=1
    out,_=shadow_stack('3F29CA','CFC9F5')
    assert out[0].state['1c']=='CFC9F5' and out[0].state['3c']=='3F29CA';checks+=1
    low=r'\an5\pos(300,150)\1a&HFE&\3a&HFE&\4a&H00&\xshad-.01\yshad.01\4c&H000000&\bord8'
    out,removed=shadow_stack('3F29CA',extra=ev(low,'Hi',layer='2'))
    assert removed==2 and out[0].state['3c']=='3F29CA';checks+=1
    out,_=shadow_stack('3F29CA',thin='2',border='1')
    assert out[0].state['3c']=='000000';checks+=1
    # A normal filled caption must not inherit a hidden lower shadow colour.
    tags=r'\an5\pos(300,150)\1c&HFFFFFF&\1a&H00&\3c&H000000&\3a&H00&\4a&HFF&\bord2'
    events=load(ev(tags,'Hi',layer='3')+ev(tags,'Hi',layer='4'))
    out,_=s.flatten_stacked_text_copies(events,{e.source_index:'Hi' for e in events},{e.source_index for e in events})
    assert len(out)==1 and out[0].state['1c']=='FFFFFF' and out[0].state['3c']=='000000';checks+=1

    # A nearly invisible full-line scaffold supplies literal text; its
    # already-proven opaque glyph row supplies the foreground and outline.
    def scaffold_row(*, solid=False, mismatch=False, tracking=False):
        literal='Colorful row'
        full=r'\an5\pos(300,150)\bord0\1a&HFE&\3a&HFE&\4a&HFE&\xshad-.01\yshad.01'
        if solid:
            full=r'\an5\pos(300,150)\bord2\1a&H00&\3a&H00&\1c&HFFFFFF&\3c&H000000&'
        glyph=r'\an5\bord2\1c&HCFC9F5&\3c&H3F29CA&\1a&H00&\3a&H00&'
        payload=r'Colorful r{\fsp-10}o{\fsp0}w' if tracking else literal
        events=load(ev(full,payload)+''.join(
            ev(glyph+rf'\pos({220+16*i},150)'+(r'\fs41' if mismatch and i==0 else ''),c,layer='4')
            for i,c in enumerate(literal.replace(' ',''))))
        result=s.remove_letters_over_full_lines(events,{e.source_index:s.OVERRIDE_RE.sub('',e.text) for e in events})
        return result.events,result.removed_count
    out,removed=scaffold_row()
    assert removed==11 and len(out)==1;checks+=1
    assert s.OVERRIDE_RE.sub('',out[0].text)=='Colorful row' and s.get_pos(out[0].text)==(300,150);checks+=1
    assert out[0].state['1c']=='CFC9F5' and out[0].state['3c']=='3F29CA';checks+=1
    out,removed=scaffold_row(solid=True)
    assert removed==11 and out[0].state['1c']=='FFFFFF' and out[0].state['3c']=='000000';checks+=1
    out,removed=scaffold_row(mismatch=True)
    assert out[0].state['3c']=='000000';checks+=1
    out,removed=scaffold_row(tracking=True)
    assert removed==11 and out[0].state['3c']=='3F29CA';checks+=1
    assert out[0].text.endswith(r'Colorful r{\fsp-10}o{\fsp0}w');checks+=1
    out,removed=scaffold_row(tracking=True,mismatch=True)
    assert out[0].state['3c']=='000000';checks+=1

    # A scaled glow at the same anchor does not block the matching shadow
    # contour/fill pair. The separate geometry is retained for later proofs.
    glow=low+r'\fscx110\fscy110'
    out,removed=shadow_stack('3F29CA',extra=ev(glow,'Hi',layer='2'))
    assert removed==1 and len(out)==2;checks+=1
    fill=[e for e in out if e.state.get('1a',0)==0]
    assert len(fill)==1 and fill[0].state['3c']=='3F29CA';checks+=1
    assert s.get_pos(fill[0].text)==(300,150) and fill[0].state['shad']==0;checks+=1
    assert any(e.state['fscx']==110 and e.layer=='2' for e in out);checks+=1
    # Ordinary static shadows with different geometry remain independent.
    tags=r'\an5\pos(300,150)\1a&HFE&\3a&HFE&\4a&H00&\xshad-10\yshad.01'
    events=load(ev(tags+r'\bord3.4\4c&H008000&','Hi',layer='3')+
                ev(tags+r'\bord.25\fscx110','Hi',layer='4'))
    out,n=s.flatten_stacked_text_copies(events,{e.source_index:'Hi' for e in events})
    assert n==0 and len(out)==2;checks+=1

    def shadow_source(*, change='', begin='50', end='100', start='0:00:01.00', finish='0:00:04.00'):
        tags=(r'\an5\pos(300,150)\1a&HFE&\3a&HFE&\4a&HFE&\xshad-150\yshad.01\fad(0,200)'
              +rf'\t({begin},{end},\4a&H00&)\t(150,10000,\xshad50)'+change)
        return load(ev(tags,'Hi',layer='4',start=start,end=finish))[0]
    core=s.shadow_lyric_fade_core(shadow_source())
    assert core is not None and core[1:]==(1.1,3.8);checks+=1
    assert core[0]['1a']==0 and core[0]['shad']==core[0]['xshad']==core[0]['yshad']==0;checks+=1
    assert s.shadow_lyric_fade_core(shadow_source(end='1500')) is not None;checks+=1
    for extra in [r'\t(2000,2200,\4a&HFF&)',r'\t(100,200,\fscx110)',
                  r'\t(100,200,\alpha&H00&)',r'\clip(0,0,500,500)',
                  r'\org(0,0)',r'\move(300,150,400,150)',r'\frz10',r'\rSign',
                  r'\fade(255,0,255,0,100,2800,3000)']:
        assert s.shadow_lyric_fade_core(shadow_source(change=extra)) is None;checks+=1
    assert s.shadow_lyric_fade_core(shadow_source(begin='200',end='100')) is None;checks+=1
    assert s.shadow_lyric_fade_core(shadow_source(end='1501')) is None;checks+=1
    no_ink=shadow_source()
    no_ink=s.replace_event(no_ink,text=no_ink.text.replace(r'\xshad-150\yshad.01',r'\xshad0\yshad0'))
    assert s.shadow_lyric_fade_core(no_ink) is None;checks+=1
    quote=shadow_source()
    quote=s.replace_event(quote,text=quote.text[:-3]+r'\fsp-40}’{\fsp0}')
    # Make one literal punctuation glyph with a dormant tracking reset.
    trimmed=s.without_inert_spacing_tail(quote)
    assert trimmed.text.endswith('’') and trimmed.state['fsp']==-40;checks+=1
    assert s.shadow_lyric_fade_core(quote) is not None;checks+=1
    live=s.replace_event(quote,text=quote.text+'a')
    assert s.without_inert_spacing_tail(live).text==live.text;checks+=1
    assert s.shadow_lyric_fade_core(live) is None;checks+=1
    other=s.replace_event(quote,text=quote.text.removesuffix(r'{\fsp0}')+r'{\fnArial}')
    assert s.without_inert_spacing_tail(other).text==other.text;checks+=1

    # Every retained glyph must have complete matching source timing. Short
    # cue fades can then hand off cleanly despite staggered shadow entrances.
    def shadow_handoff(*, next_start=3.9, missing=False, late=False, moved=False, assembled=False):
        source=[];captions=[];rows=[]
        for cue,text in enumerate(['Alpha beta','Gamma delta']):
            start,end=(1.,4.) if cue==0 else (next_start,6.9)
            raw=''
            for i,c in enumerate(text.replace(' ','')):
                x=200+20*i+(400 if moved and cue else 0)
                ingress=1900 if late and cue and i==0 else 60+i*5
                raw+=ev(rf'\an5\pos({x},150)\1a&HFE&\3a&HFE&\4a&HFE&\xshad-100\yshad.01\fad(0,200)\t(0,{ingress},\4a&H00&)',
                        c,layer='4',start=s.format_time(start),end=s.format_time(end))
            glyphs=load(raw)
            offset=100*cue
            glyphs=[s.dataclass_replace(e,source_index=e.source_index+offset) for e in glyphs]
            source.extend(glyphs[:-1] if missing and cue else glyphs)
            fixed=[s.replace_event(e,text=s.render_simplified_caption({**e.state,'1a':0,'3a':0},
                    s.simplify_text(e.text,visible_only=True)[1])) for e in glyphs]
            if assembled:
                base=s.replace_event(fixed[0],text=s.render_simplified_caption(fixed[0].state,text,pos=(300+(400 if moved and cue else 0),150)))
                captions.append(base)
                rows.append(s.TextRow(base,[(e,s.OVERRIDE_RE.sub('',e.text),s.get_pos(e.text)) for e in fixed]))
            else:
                captions.extend(fixed)
        result,count=s.trim_faded_cue_overlaps(captions,rows,{e.source_index:e for e in source})
        return result,count,captions
    out,n,before=shadow_handoff()
    assert n==1 and max(e.end_s for e in out if e.start_s<2)==min(e.start_s for e in out if e.end_s>6);checks+=1
    assert all(e.text==b.text and e.layer==b.layer for e,b in zip(out,before));checks+=1
    out,n,_=shadow_handoff(assembled=True)
    assert n==1 and out[0].end_s==out[1].start_s;checks+=1
    for opts in [{'missing':True},{'next_start':3.5},{'moved':True},{'late':True}]:
        out,n,before=shadow_handoff(**opts)
        assert n==0 and [e.fields() for e in out]==[e.fields() for e in before],opts;checks+=1

    # Vector reconstruction and the text ownership proofs retain their guards.

print(checks,'regression checks passed')
