from pathlib import Path
import sys,json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import simplify_ass as s
r=Path(__file__).resolve().parents[1]
d=s.parse_subtitle_document((r/'test-data/Attack-on-Titan-S02E01-opening-source.ass').read_text(encoding='utf-8-sig'))
m=s.FontMetrics([r/'fonts'])
x=s.reconstruct_glyph_lifecycles(d.events,m)
print('removed',x.removed_count,'rows',len(x.rows),flush=True)
for row in x.rows:print(row.base.start,row.base.end,row.base.text,flush=True)
