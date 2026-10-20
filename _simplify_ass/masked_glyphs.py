"""Exact masked-glyph proofs and pass-owned replacement/resource lifetimes."""
from __future__ import annotations

from dataclasses import dataclass, field
import re
import statistics

from .ass_overrides import tokenize_override, OVERRIDE_RE, NUMBER, DEFAULT_STATE
from .font_metrics import FontMetrics
from .event_model import Event
from .event_operations import replace_event, state_key
from .caption_geometry import get_pos, inline_layout_key, text_height, placement_key, text_layout_key
from .caption_rendering import render_simplified_caption


@dataclass(frozen=True)
class MaskedGlyphContext:
    """Original geometry, texture indexes and exact-font caches for one mask pass."""
    visible: dict[int,str]
    metric: FontMetrics | None
    animated: set[int]
    positions: dict[int,tuple[float,float] | None]
    heights: dict[int,float]
    inline_layouts: dict[int,tuple]
    bases: dict[tuple,list[Event]]
    texture_peers: dict[tuple,list[Event]] = field(default_factory=dict,compare=False)
    shadow_masks: dict[tuple,list[Event]] = field(default_factory=dict,compare=False)
    mask_peers: dict[tuple,set[str]] = field(default_factory=dict,compare=False)
    captions: dict[tuple,list[Event]] = field(default_factory=dict,compare=False)
    shadow_sources: set[int] = field(default_factory=set,compare=False)
    layouts: dict[int,tuple] = field(default_factory=dict,compare=False)
    placements: dict[int,tuple] = field(default_factory=dict,compare=False)
    outlines: dict[tuple,tuple | None] = field(default_factory=dict,compare=False)
    fonts: dict[tuple,tuple] = field(default_factory=dict,compare=False)


@dataclass(frozen=True)
class ParsedGlyphMask:
    """Validated contour commands, screen points and command-to-point offsets."""
    commands: list[str]
    points: list[tuple[float,float]]
    offsets: list[int]


@dataclass(frozen=True)
class MaskedGlyphModel:
    """An exact font outline scaled into the retained glyph's authored geometry."""
    outline: tuple
    points: list[tuple[float,float]]
    center: tuple[float,float]
    variance: float
    scale: float


@dataclass(frozen=True)
class MaskedGlyphProof:
    """Accumulated command ownership and candidate glyph replacements for one mask."""
    covered: set[int] = field(default_factory=set)
    matched: dict[int,Event] = field(default_factory=dict)
    loose: set[int] = field(default_factory=set)


def _canonicalize_mask_contours(commands: list[str], points: list[tuple[float,float]]) -> tuple[list[str],list[tuple[float,float]]]:
    """Close identical explicit/implicit edges without approximating glyph contours."""
    # ASS clips may explicitly return to a contour's first point, whereas
    # the font pen closes that same straight edge implicitly. Canonicalize
    # only identical endpoints; all other vertices and curves remain exact.
    result, vertices = [], []
    offset, start = 0, None
    for command in commands:
        count = {"m":1,"l":1,"b":3,"z":0}[command]
        coords = points[offset:offset+count]
        offset += count
        if command == "m":
            start = coords[0]
        if (command == "z" and result and result[-1] == "l" and
                vertices[-1] == start):
            result.pop()
            vertices.pop()
        result.append(command)
        vertices.extend(coords)
    return result,vertices


def _prepare_masked_glyphs(events: list[Event], visible_map: dict[int,str], metric: FontMetrics | None,
    animated_sources: set[int] | None) -> MaskedGlyphContext:
    """Resolve original event geometry once and spatially index eligible unmasked text."""
    # Input events are borrowed read-only; replacements are separate objects.
    # Resolve repeated geometry once rather than for every mask/base pair.
    positions = {e.source_index: get_pos(e.text) for e in events}
    heights = {e.source_index: text_height(e) for e in events}
    inline_layouts = {e.source_index: inline_layout_key(e) for e in events}
    animated_sources = animated_sources or set()
    bases: dict[tuple,list[Event]] = {}
    for e in events:
        if (e.kind == "Dialogue" and positions[e.source_index] is not None and
                visible_map.get(e.source_index) and not inline_layouts[e.source_index] and
                "clip" not in e.state and "iclip" not in e.state and
                e.state.get("1a",0) < 255):
            x,y = positions[e.source_index]
            bases.setdefault((e.style,int(x//(20*e.unit)),int(y//(20*e.unit))),[]).append(e)
    return MaskedGlyphContext(visible_map,metric,animated_sources,
        positions,heights,inline_layouts,bases)


def _index_masked_texture_peers(events: list[Event], context: MaskedGlyphContext) -> None:
    """Index opaque captions, shadow-mask carriers and animated unmasked texture peers."""
    for peer in events:
        # Inline letter spacing does not change a caption's anchor or paint.
        # Other inline overrides cannot supply this texture-stack evidence.
        inline = OVERRIDE_RE.findall(peer.text)[1:]
        if (peer.kind == "Dialogue" and context.positions[peer.source_index] is not None and
                context.visible.get(peer.source_index) and peer.state.get("1a",0) == 0 and
                "clip" not in peer.state and "iclip" not in peer.state and
                all(all(k == "fsp" for k,v in tokenize_override(block)) for block in inline)):
            context.captions.setdefault((peer.style,peer.name),[]).append(peer)
        if (peer.kind == "Dialogue" and context.positions[peer.source_index] is not None and
                not context.inline_layouts[peer.source_index] and "clip" in peer.state and
                "iclip" not in peer.state and peer.state.get("1a",0) >= 254 and
                peer.state.get("3a",0) >= 254 and peer.state.get("4a",255) < 128 and
                peer.state.get("borderstyle",1) == 1 and
                0 < max(abs(peer.state.get(k,peer.state.get("shad",0)))
                        for k in ("xshad","yshad")) <= peer.unit and
                max(abs(peer.state.get(k,peer.state.get("bord",0)))
                    for k in ("xbord","ybord")) <= peer.unit):
            family = (peer.style,peer.name,context.positions[peer.source_index],
                      context.visible.get(peer.source_index),state_key(peer,{"clip","blur","be"}))
            context.shadow_masks.setdefault(family,[]).append(peer)
            context.shadow_sources.add(peer.source_index)
            key = (peer.style,peer.name,peer.start,peer.end,context.positions[peer.source_index],
                   text_layout_key(peer),peer.state["clip"])
            context.mask_peers.setdefault(key,set()).add(context.visible.get(peer.source_index))
        if (peer.source_index in context.animated and
                peer.kind == "Dialogue" and context.positions[peer.source_index] is not None and
                not context.inline_layouts[peer.source_index] and "clip" not in peer.state and
                "iclip" not in peer.state):
            key = (peer.style,peer.name,peer.start,peer.end,
                   context.visible.get(peer.source_index),peer.state.get("fn"),
                   context.positions[peer.source_index])
            context.texture_peers.setdefault(key,[]).append(peer)


def _parse_glyph_mask(e: Event) -> ParsedGlyphMask | None:
    """Parse valid scaled move/line/cubic contours and record command point offsets."""
    # Parse only closed move/line/cubic contours, including scaled clips.
    mask = re.fullmatch(r"\(\s*(?:(\d+)\s*,\s*)?(m\s+.*?)\s*\)",
                        str(e.state["clip"]), re.I)
    if mask is None:
        return None
    commands, points = [], []
    parts = re.findall(r"([mlb])\s+([^mlb]+)",mask[2],re.I)
    valid = bool(parts) and not re.sub(r"[mlb\s]|"+NUMBER,"",mask[2],flags=re.I)
    scale_number = int(mask[1] or 1)
    if not 1 <= scale_number <= 16:
        return None
    clip_scale = 2 ** (scale_number-1)
    for command, coords in parts:
        command = command.lower()
        nums = list(map(float,re.findall(NUMBER,coords)))
        size = 6 if command == "b" else 2
        if not nums or len(nums)%size or (command == "m" and len(nums)!=2):
            valid = False; break
        if command == "m" and commands:
            commands.append("z")
        commands.extend([command]*(len(nums)//size))
        points.extend((x/clip_scale,y/clip_scale) for x,y in zip(nums[::2],nums[1::2]))
    commands.append("z")
    if not valid or not points:
        return None
    commands,points = _canonicalize_mask_contours(commands,points)
    offsets = [0]
    for op in commands:
        offsets.append(offsets[-1]+{"m":1,"l":1,"b":3,"z":0}[op])
    return ParsedGlyphMask(commands,points,offsets)


def _match_masked_shadow_texture(context: MaskedGlyphContext, e: Event, mask: ParsedGlyphMask,
    removed: set[int], valid_shadow_masks: set[int]) -> None:
    """Prove multi-string shadow textures over a complete aligned opaque caption."""
    pos = context.positions[e.source_index]
    key = (e.style,e.name,e.start,e.end,pos,text_layout_key(e),e.state["clip"])
    if (e.source_index in context.shadow_sources and len(context.mask_peers.get(key,())) >= 2 and
            mask.commands.count("m") >= 2):
        valid_shadow_masks.add(e.source_index)
        # Distinct filler strings painted through the same multi-contour
        # mask form a texture stack, rather than alternate caption text.
        # Require an opaque caption throughout this phase and an aligned
        # mask around its anchor; no font-name or payload blacklist.
        xs,ys = zip(*mask.points)
        for base in context.captions.get((e.style,e.name),[]):
            bp = context.positions[base.source_index]
            radius = .25*min(context.heights[e.source_index],context.heights[base.source_index])
            if (base.start_s <= e.start_s+.001 and base.end_s >= e.end_s-.001 and
                    base.state.get("fn") != e.state.get("fn") and
                    context.visible[base.source_index] != context.visible[e.source_index] and
                    e.state.get("an",5) == base.state.get("an",5) == 5 and
                    all(abs(obj.state.get(k,0)) <= .001 for obj in (e,base)
                        for k in ("frz","frx","fry","fax","fay")) and
                    abs(pos[0]-bp[0]) <= radius and abs(pos[1]-bp[1]) <= radius and
                    min(xs) <= bp[0] <= max(xs) and min(ys) <= bp[1] <= max(ys) and
                    max(ys)-min(ys) <= 1.5*context.heights[base.source_index]):
                removed.add(e.source_index)
                break


def _masked_glyph_candidates(context: MaskedGlyphContext, e: Event, mask: ParsedGlyphMask) -> list[Event]:
    """Search both mask and carrier bounds, preserving lifetime and layer tie order."""
    pos = context.positions[e.source_index]
    # Clips use screen coordinates independently of the texture's position.
    # Search at the mask itself; actors may label phases of the same glyph.
    xs,ys = zip(*mask.points)
    radius, cell = context.heights[e.source_index], 20*e.unit
    # Spatial indexing changes only the search cost, not match tolerances.
    nearby = [base
              for x in range(int((min(xs)-radius)//cell),int((max(xs)+radius)//cell)+1)
              for y in range(int((min(ys)-radius)//cell),int((max(ys)+radius)//cell)+1)
              for base in context.bases.get((e.style,x,y),[])]
    nearby.extend(base
                  for x in range(int((pos[0]-radius)//cell),int((pos[0]+radius)//cell)+1)
                  for y in range(int((pos[1]-radius)//cell),int((pos[1]+radius)//cell)+1)
                  for base in context.bases.get((e.style,x,y),[]))
    # Reject lifetime-ineligible candidates before sorting or layout checks.
    # Dict insertion order preserves the existing tie order by layer.
    candidates = {b.source_index:b for b in nearby
                  if not (b.start_s > e.start_s+.001 or b.end_s < e.end_s-.001)}
    return sorted(candidates.values(),
                       key=lambda b:int(b.layer) if b.layer.lstrip("-").isdigit() else 0,
                       reverse=True)


def _masked_placement_matches(context: MaskedGlyphContext, e: Event, base: Event) -> bool:
    """Cache exact event placement keys before any text or outline proof."""
    if e.source_index not in context.placements:
        context.placements[e.source_index] = placement_key(e)
    if base.source_index not in context.placements:
        context.placements[base.source_index] = placement_key(base)
    if context.placements[e.source_index][0] != context.placements[base.source_index][0]:
        return False
    return True


def _same_masked_text_copy(context: MaskedGlyphContext, e: Event, base: Event) -> bool:
    """Prove repeated literal text with aligned anchors and exactly matching text layout."""
    pos = context.positions[e.source_index]
    bp = context.positions[base.source_index]
    tolerance = .12*min(context.heights[e.source_index],context.heights[base.source_index])
    if (e.name == base.name and abs(pos[0]-bp[0]) <= tolerance and
            abs(pos[1]-bp[1]) <= tolerance and
            context.visible.get(e.source_index) == context.visible[base.source_index]):
        if e.source_index not in context.layouts:
            context.layouts[e.source_index] = text_layout_key(e)
        if base.source_index not in context.layouts:
            context.layouts[base.source_index] = text_layout_key(base)
        if context.layouts[e.source_index] == context.layouts[base.source_index]:
            return True
    return False


def _masked_glyph_outline(context: MaskedGlyphContext, base: Event) -> tuple | None:
    """Cache exact-font cubic outlines and failures; retain opened fonts for this pass."""
    glyph = context.visible[base.source_index]
    state = base.state
    if (context.metric is None or not context.metric.available or len(glyph)!=1 or
            any(abs(state.get(k,0))>.001 for k in ("frz","frx","fry","fax","fay"))):
        return None
    face = context.metric.matching_face(str(state.get("fn","")),state.get("b",0),bool(state.get("i",0)))
    if face is None or ord(glyph) not in face.cmap:
        return None
    key = (face.key,glyph)
    if key not in context.outlines:
        context.outlines[key] = None
        try:
            from fontTools.pens.recordingPen import DecomposingRecordingPen, RecordingPen
            from fontTools.pens.qu2cuPen import Qu2CuPen
            if face.key not in context.fonts:
                font = context.metric.open_face(face)
                # Transfer only fully initialized handles into the pass cache.
                try:
                    context.fonts[face.key] = (font,font.getGlyphSet())
                except BaseException:
                    font.close()
                    raise
            font,glyphs = context.fonts[face.key]
            pen = DecomposingRecordingPen(glyphs)
            glyphs[font.getBestCmap()[ord(glyph)]].draw(pen)
            cubic = RecordingPen()
            pen.replay(Qu2CuPen(cubic,max_err=.01,all_cubic=True))
            ops, vertices = [], []
            for op, coords in cubic.value:
                ops.append({"moveTo":"m","lineTo":"l","curveTo":"b","closePath":"z"}[op])
                vertices.extend((x,-y) for x,y in coords)
            ops,vertices = _canonicalize_mask_contours(ops,vertices)
            os2,hhea = font['OS/2'],font['hhea']
            context.outlines[key] = (ops,vertices,font['head'].unitsPerEm,
                font['hmtx'].metrics[font.getBestCmap()[ord(glyph)]][0],
                ((os2.usWinAscent,os2.usWinDescent),
                 (hhea.ascent,-hhea.descent),
                 (os2.sTypoAscender,-os2.sTypoDescender)))
        except Exception:
            pass  # Corrupt/unsupported fonts cannot authorize deletion.
    outline = context.outlines[key]
    if outline is None or not outline[1] or int(state.get("an",5)) not in range(1,10):
        return None
    return outline


def _prepare_masked_outline_model(base: Event, outline: tuple) -> MaskedGlyphModel | None:
    """Scale the exact outline into authored glyph geometry without fitting its contour."""
    state = base.state
    # Fit just translation and one uniform font-size multiplier; never
    # warp unrelated contours into a match. ASS/em conventions vary.
    fs = state.get("fs",0)/outline[2]
    model = [(x*fs*state.get("fscx",100)/100,y*fs*state.get("fscy",100)/100)
             for x,y in outline[1]]
    mx,my = (statistics.mean(v) for v in zip(*model))
    denom = sum((x-mx)**2+(y-my)**2 for x,y in model)
    if denom <= 0:
        return None
    return MaskedGlyphModel(outline,model,(mx,my),denom,fs)


def _fit_masked_outline_segment(context: MaskedGlyphContext, base: Event, mask: ParsedGlyphMask,
    shape: MaskedGlyphModel, start: int) -> tuple[int,bool] | None:
    """Fit one contour with only translation and a uniform size factor, then prove its anchor."""
    outline,model,fs = shape.outline,shape.points,shape.scale
    mx,my = shape.center
    denom = shape.variance
    state = base.state
    bp = context.positions[base.source_index]
    stop = start+len(outline[0])
    segment = mask.points[mask.offsets[start]:mask.offsets[stop]]
    if len(segment) != len(model):
        return None
    px,py = (statistics.mean(v) for v in zip(*segment))
    factor = sum((x-mx)*(a-px)+(y-my)*(b-py)
                 for (x,y),(a,b) in zip(model,segment))/denom
    error = max(abs(v) for (x,y),(a,b) in zip(model,segment)
                for v in (a-px-factor*(x-mx),b-py-factor*(y-my)))
    an = int(state.get("an",5))
    ax,ay = ((an-1)%3)/2, 1-((an-1)//3)/2
    dx = bp[0]-ax*outline[3]*fs*state.get("fscx",100)/100*factor
    dy = [bp[1]+(asc-ay*(asc+desc))*fs*state.get("fscy",100)/100*factor
          for asc,desc in outline[4]]
    # Word masks can use shaped advances while the source glyphs
    # use individually rounded positions. Keep exact contour tests;
    # a wider anchor allowance needs a complete multi-glyph match.
    tolerance = max(1.5*base.unit,.04*context.heights[base.source_index])
    anchor_error = max(abs(px-factor*mx-dx),
        min(abs(py-factor*my-y) for y in dy))
    if (not .5 <= factor <= 1.5 or error > max(.03,.001*context.heights[base.source_index]) or
            anchor_error > max(tolerance,.12*context.heights[base.source_index])):
        return None
    return stop,anchor_error > tolerance


def _match_masked_glyph_contours(context: MaskedGlyphContext, base: Event, mask: ParsedGlyphMask,
    outline: tuple, proof: MaskedGlyphProof) -> None:
    """Accumulate exact contour coverage without rematching already claimed command spans."""
    glyph = context.visible[base.source_index]
    state = base.state
    starts = [i for i in range(len(mask.commands)-len(outline[0])+1)
              if mask.commands[i:i+len(outline[0])] == outline[0] and
              not any(j in proof.covered for j in range(i,i+len(outline[0])))]
    if not starts:
        return
    shape = _prepare_masked_outline_model(base,outline)
    if shape is None:
        return
    for start in starts:
        fit = _fit_masked_outline_segment(context,base,mask,shape,start)
        if fit is None:
            continue
        stop,loose = fit
        if loose:
            proof.loose.add(base.source_index)
        proof.covered.update(range(start,stop))
        proof.matched[base.source_index] = replace_event(base,
            text=render_simplified_caption(state,glyph,measurement=base.measurement))


def _match_masked_glyph_bases(context: MaskedGlyphContext, e: Event, mask: ParsedGlyphMask, removed: set[int]) -> MaskedGlyphProof:
    """Try identical text before exact font contours in the original candidate order."""
    proof = MaskedGlyphProof()
    for base in _masked_glyph_candidates(context,e,mask):
        if not _masked_placement_matches(context,e,base):
            continue
        if _same_masked_text_copy(context,e,base):
            removed.add(e.source_index)
            break
        outline = _masked_glyph_outline(context,base)
        if outline is None:
            continue
        _match_masked_glyph_contours(context,base,mask,outline,proof)
    return proof


def _remove_masked_texture_companions(context: MaskedGlyphContext, e: Event, matched: dict[int,Event], removed: set[int]) -> None:
    """Remove only matching animated unmasked companions of a fully proved glyph mask."""
    pos = context.positions[e.source_index]
    # A texture may have both a glyph-shaped mask and an unmasked
    # animated copy. Only remove that companion when the proven mask
    # traces a different font, and timing, actor, glyph and anchor agree.
    # Do not extend this evidence to other phases or nearby objects.
    if (matched and e.source_index in context.animated and
            all(base.state.get("fn") != e.state.get("fn")
                for base in matched.values())):
        key = (e.style,e.name,e.start,e.end,
               context.visible.get(e.source_index),e.state.get("fn"),pos)
        for peer in context.texture_peers.get(key,[]):
            if (all(peer.state.get(k,DEFAULT_STATE.get(k)) ==
                    e.state.get(k,DEFAULT_STATE.get(k))
                    for k in ("an","fsp","b","i","u","s","1a",
                              "bord","shad","frx","fry","fax","fay"))):
                removed.add(peer.source_index)


def _apply_masked_glyph_proof(context: MaskedGlyphContext, e: Event, mask: ParsedGlyphMask, proof: MaskedGlyphProof,
    removed: set[int], replacements: dict[int,Event]) -> None:
    """Remove fully covered masks and keep their proven retained glyphs readable."""
    if len(proof.covered) == len(mask.commands) and (not proof.loose or
            len({get_pos(base.text) for base in proof.matched.values()}) >= 3):
        removed.add(e.source_index)
        # The mask can be the principal visible fill over a transparent
        # glyph. Keep the proven text readable when removing that fill.
        replacements.update(proof.matched)
        _remove_masked_texture_companions(context,e,proof.matched,removed)


def _follow_proven_shadow_mask_phases(context: MaskedGlyphContext, valid_shadow_masks: set[int], removed: set[int]) -> None:
    """Follow only touching phases of the same already-proved shadow texture carrier."""
    # Follow only touching phases of the same proven texture carrier. This
    # removes its clipped wipe-out too, without affecting a later unrelated cue.
    for family in context.shadow_masks.values():
        runs = []
        for e in sorted((obj for obj in family if obj.source_index in valid_shadow_masks),
                        key=lambda obj:(obj.start_s,obj.end_s)):
            if not runs or e.start_s > max(obj.end_s for obj in runs[-1])+.001:
                runs.append([])
            runs[-1].append(e)
        for run in runs:
            if any(e.source_index in removed for e in run):
                removed.update(e.source_index for e in run)


def _close_masked_glyph_fonts(context: MaskedGlyphContext) -> None:
    """Close the exact fonts opened by this mask-removal pass."""
    for font,_ in context.fonts.values():
        font.close()


def remove_masked_glyph_effects(events: list[Event],
                                visible_map: dict[int,str],
                                metric: FontMetrics | None = None,
                                animated_sources: set[int] | None = None) -> tuple[list[Event],int]:
    """Remove matching text copies or masks proven to trace an underlying glyph.

    Outline matching uses the exact font, contour topology and every control
    point. Shadow-only texture stacks can also be identified by their shared
    mask over a retained caption. Other unavailable-font or unsupported masks
    stay intact.
    This is a standard simplification effect substitution, not an assertion of occlusion.
    """
    context = _prepare_masked_glyphs(events,visible_map,metric,animated_sources)
    removed, replacements, valid_shadow_masks = set(), {}, set()
    try:
        _index_masked_texture_peers(events,context)
        for e in events:
            pos = context.positions[e.source_index]
            if (e.kind != "Dialogue" or pos is None or context.inline_layouts[e.source_index] or
                    "iclip" in e.state or "clip" not in e.state):
                continue
            mask = _parse_glyph_mask(e)
            if mask is None:
                continue
            _match_masked_shadow_texture(context,e,mask,removed,valid_shadow_masks)
            proof = _match_masked_glyph_bases(context,e,mask,removed)
            _apply_masked_glyph_proof(context,e,mask,proof,removed,replacements)
        _follow_proven_shadow_mask_phases(context,valid_shadow_masks,removed)
    finally:
        _close_masked_glyph_fonts(context)
    return [replacements.get(e.source_index,e) for e in events
            if e.source_index not in removed],len(removed)
