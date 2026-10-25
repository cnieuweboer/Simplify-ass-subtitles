"""Conservative drawing geometry and bounded contour normalization.

Inputs stay borrowed and working buffers stay call-local. Supporting-drawing
producers retain source admission, original-contour evidence, measurements,
movement/compositing proofs, counters and pipeline order.
"""
from __future__ import annotations

import math
import re
from .ass_overrides import NUMBER, OVERRIDE_RE
from .caption_geometry import get_pos, inline_layout_key
from .event_model import Event
from .event_operations import replace_event
from .static_objects import geometry_key


def coverage_geometry(e: Event, scaled_borders: bool = True):
    """Conservative bounds for a single top-left, unrotated drawing.

    Curves may be covered (their control points bound them); covering shapes
    must be straight-sided. Unsupported drawing syntax is never guessed.
    """
    state = e.state
    if not e.layer.lstrip("-").isdigit():
        return None
    if (state.get("an", 2) != 7 or state.get("p", 0) < 1
            or state.get("borderstyle", 1) != 1
            or any(state.get(k, 0) != 0 for k in
                   ("frz", "frx", "fry", "fax", "fay", "pbo", "blur", "be", "fsp"))):
        return None
    pos = get_pos(e.text)
    match = re.fullmatch(r"(?:\{[^}]*\})*([^{}]+)", e.text)
    if pos is None or match is None:
        return None
    raw = match.group(1).strip()
    tokens = re.findall(NUMBER + r"|[A-Za-z]", raw)
    if re.sub(NUMBER + r"|[A-Za-z]|\s+", "", raw):
        return None
    if not tokens or tokens[0].lower() != "m":
        return None
    points, curved, i = [], False, 0
    while i < len(tokens):
        command = tokens[i].lower()
        i += 1
        if command not in {"m", "l", "b"} or (command == "m" and points):
            return None  # Multiple contours, holes and splines stay untouched.
        coords = []
        while i < len(tokens) and re.fullmatch(NUMBER, tokens[i]):
            coords.append(float(tokens[i])); i += 1
        if ((command == "m" and len(coords) != 2)
                or (command == "l" and (len(coords) < 2 or len(coords) % 2))
                or (command == "b" and (len(coords) < 6 or len(coords) % 6))):
            return None
        points.extend(zip(coords[::2], coords[1::2]))
        curved |= command == "b"
    if len(points) < 3:
        return None
    scale = 2 ** (state["p"] - 1)
    sx, sy = state.get("fscx", 100) / (100 * scale), state.get("fscy", 100) / (100 * scale)
    if sx <= 0 or sy <= 0:
        return None
    points = [(pos[0] + x*sx, pos[1] + y*sy) for x,y in points]
    bx = abs(state.get("xbord", state.get("bord", 0)))
    by = abs(state.get("ybord", state.get("bord", 0)))
    dx = state.get("xshad", state.get("shad", 0))
    dy = state.get("yshad", state.get("shad", 0))
    if not scaled_borders and any((bx, by, dx, dy)):
        return None
    # Include the entire stroke and shadow even when their alpha is hidden.
    # Extra clearance keeps anti-aliased edges outside the coverage boundary.
    pad = max(2.0, 2*e.unit)
    xs, ys = zip(*points)
    bounds = (min(xs)-bx+min(0,dx)-pad, min(ys)-by+min(0,dy)-pad,
              max(xs)+bx+max(0,dx)+pad, max(ys)+by+max(0,dy)+pad)
    opaque = (state.get("1a", 0) == 0 and not curved
              and "clip" not in state and "iclip" not in state)
    return points, bounds, opaque


def polygon_covers_box(points, box) -> bool:
    """Require the whole box inside the fill, with no contour crossing it."""
    x0,y0,x1,y1 = box
    edges = list(zip(points, points[1:] + points[:1]))
    # Segment/rectangle intersection (including boundaries).
    for (ax,ay),(bx,by) in edges:
        lo, hi = 0.0, 1.0
        for origin, delta, low, high in ((ax,bx-ax,x0,x1),(ay,by-ay,y0,y1)):
            if delta == 0:
                if origin < low or origin > high:
                    lo,hi = 1.0,0.0
                    break
            else:
                t0,t1 = sorted(((low-origin)/delta,(high-origin)/delta))
                lo,hi = max(lo,t0),min(hi,t1)
        if lo <= hi:
            return False
    # With no boundary in the box, its interior has uniform fill. Require
    # both winding and odd/even rules to consider the test point filled.
    x,y = (x0+x1)/2,(y0+y1)/2
    crossings = winding = 0
    for (ax,ay),(bx,by) in edges:
        if (ay <= y < by) or (by <= y < ay):
            hit = ax + (y-ay)*(bx-ax)/(by-ay)
            if hit > x:
                crossings += 1
                winding += 1 if by > ay else -1
    return bool(crossings % 2 and winding)


def drawing_polygon(event, *, max_vertices=8):
    """One finite straight-sided contour with at most eight distinct vertices."""
    raw = OVERRIDE_RE.sub('', event.text).strip()
    tokens = geometry_key(event.text)
    if (re.sub(NUMBER+r'|[A-Za-z]|\s+', '', raw) or not tokens or
            tokens[0] != 'm' or sum(x == 'm' for x in tokens) != 1 or
            any(isinstance(x, str) and x not in {'m', 'l'} for x in tokens)):
        return None
    points = []
    i = 0
    while i < len(tokens):
        command = tokens[i]; i += 1
        coords = []
        while i < len(tokens) and isinstance(tokens[i], float):
            coords.append(tokens[i]); i += 1
        if ((command == 'm' and len(coords) != 2) or
                (command == 'l' and (len(coords) < 2 or len(coords) % 2)) or
                any(not math.isfinite(v) for v in coords)):
            return None
        points.extend(zip(coords[::2], coords[1::2]))
    if points and points[-1] == points[0]:
        points.pop()
    if (len(set(points)) < 3 or (max_vertices is not None and
            (len(set(points)) > max_vertices or len(points) > max_vertices+1))):
        return None
    area = abs(sum(ax*by-bx*ay for (ax, ay), (bx, by) in
                   zip(points, points[1:]+points[:1]))) / 2
    return points if area > 0 else None


def flatten_rectangular_border(event, *, scaled_borders=True):
    """Fold a same-colour rectangular stroke into its simple solid fill."""
    st = event.state
    points = drawing_polygon(event)
    if (not scaled_borders or points is None or len(points) != 4 or st.get('borderstyle', 1) != 1 or
            st.get('1c', 'FFFFFF') != st.get('3c', '000000') or
            st.get('1a', 0) != st.get('3a', 0) or st.get('1a', 0) >= 254 or
            any(st.get(k, 0) for k in ('frz', 'frx', 'fry', 'fax', 'fay', 'pbo'))):
        return event
    xs, ys = sorted({x for x, y in points}), sorted({y for x, y in points})
    if (len(xs) != 2 or len(ys) != 2 or
            set(points) != {(x, y) for x in xs for y in ys} or
            any(ax != bx and ay != by for (ax, ay), (bx, by) in
                zip(points, points[1:]+points[:1]))):
        return event
    sx = st.get('fscx', 100)/(100*2**(st.get('p', 1)-1))
    sy = st.get('fscy', 100)/(100*2**(st.get('p', 1)-1))
    bx, by = abs(st.get('xbord', st.get('bord', 0))), abs(st.get('ybord', st.get('bord', 0)))
    if min(sx, sy) <= 0 or not (bx or by):
        return event
    # Preserve the drawing anchor before expanding its stroked footprint.
    event = normalize_drawing_alignment(event)
    x0, x1 = xs[0]-bx/sx, xs[1]+bx/sx
    y0, y1 = ys[0]-by/sy, ys[1]+by/sy
    block = OVERRIDE_RE.match(event.text)
    raw = f'm {x0:g} {y0:g} l {x1:g} {y0:g} {x1:g} {y1:g} {x0:g} {y1:g}'
    tags = block.group()[:-1]+r'\bord0\xbord0\ybord0'+'}'
    return replace_event(event, text=tags+raw)


def normalize_drawing_alignment(event):
    """Express an unrotated drawing's alignment as an equivalent an7 pose."""
    st = event.state
    alignment = st.get('an', 7)
    if alignment == 7 or alignment not in range(1, 10):
        return event
    if any(st.get(k, 0) for k in ('frz', 'frx', 'fry', 'fax', 'fay', 'pbo')):
        return event
    points = drawing_polygon(event, max_vertices=None)
    pos = get_pos(event.text)
    if points is None or pos is None or st.get('p', 0) < 1:
        return event
    scale = 2 ** (st['p']-1)
    sx, sy = st.get('fscx', 100)/(100*scale), st.get('fscy', 100)/(100*scale)
    if sx <= 0 or sy <= 0:
        return event
    xs, ys = zip(*points)
    x = pos[0] - ((alignment-1) % 3)/2 * (max(xs)-min(xs))*sx
    y = pos[1] - (2-(alignment-1)//3)/2 * (max(ys)-min(ys))*sy
    block = OVERRIDE_RE.match(event.text)
    if block is None:
        return event
    tags = re.sub(r'\\an\d+|\\pos\([^)]*\)', '', block.group()[:-1], flags=re.I)
    return replace_event(event, text=tags+f'\\an7\\pos({x:g},{y:g})}}'+event.text[block.end():])


def fit_rectangular_contour(points):
    """Prefer the original bounds when a contour closely follows a rectangle."""
    xs, ys = zip(*points)
    x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
    side, box_area = min(x1-x0, y1-y0), (x1-x0)*(y1-y0)
    if side <= 0:
        return None
    area = abs(sum(ax*by-bx*ay for (ax, ay), (bx, by) in
                   zip(points, points[1:]+points[:1])))/2
    if not .85*box_area <= area <= box_area*(1+1e-9):
        return None
    tolerance = .15*side+1e-9
    for a, b in zip(points, points[1:]+points[:1]):
        # Also test the segment midpoint: matching the four extremes alone
        # would turn diagonal sides or a deep inward notch into a rectangle.
        for x, y in (a, ((a[0]+b[0])/2, (a[1]+b[1])/2)):
            if min(x-x0, x1-x, y-y0, y1-y) > tolerance:
                return None
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def detach_drawing_edge_slivers(event):
    """Separate tiny exterior triangles from one nearly rectangular panel.

    Do not discard holes, intersecting contours or independent artwork. The
    triangle must touch the main boundary but have no filled interior in it.
    Test every boundary-partitioned segment, including collinear/tangent hits,
    rather than relying on vertices or the overall drawing bounds.
    """
    raw = OVERRIDE_RE.sub('', event.text).strip()
    block = OVERRIDE_RE.match(event.text)
    parts = [part.strip() for part in re.split(r'(?=\bm\s)', raw, flags=re.I)
             if part.strip()]
    if block is None or not 2 <= len(parts) <= 5:
        return event, 0
    fragments = [replace_event(event, text=block.group()+part) for part in parts]
    polygons = [drawing_polygon(e, max_vertices=None) for e in fragments]
    if any(p is None or len(p) > 4096 for p in polygons):
        return event, 0
    def area(p):
        return abs(sum(ax*by-bx*ay for (ax, ay), (bx, by) in
                       zip(p, p[1:]+p[:1])))/2
    index = max(range(len(polygons)), key=lambda i: area(polygons[i]))
    main = polygons[index]
    if fit_rectangular_contour(main) is None or coverage_geometry(fragments[index]) is None:
        return event, 0
    xs, ys = zip(*main)
    side = min(max(xs)-min(xs), max(ys)-min(ys))
    eps = 1e-8*max(1, side)
    def cross(a, b):
        return a[0]*b[1]-a[1]*b[0]
    def sub(a, b):
        return a[0]-b[0], a[1]-b[1]
    def on_edge(p, a, b):
        return (abs(cross(sub(p, a), sub(b, a))) <= eps*max(1, math.dist(a, b)) and
                min(a[0], b[0])-eps <= p[0] <= max(a[0], b[0])+eps and
                min(a[1], b[1])-eps <= p[1] <= max(a[1], b[1])+eps)
    edges = list(zip(main, main[1:]+main[:1]))
    def inside(p, polygon):
        if any(on_edge(p, a, b) for a, b in zip(polygon, polygon[1:]+polygon[:1])):
            return False  # Boundary contact is permitted, filled overlap is not.
        crossings = winding = 0
        for a, b in zip(polygon, polygon[1:]+polygon[:1]):
            if a[1] <= p[1] < b[1] or b[1] <= p[1] < a[1]:
                hit = a[0]+(p[1]-a[1])*(b[0]-a[0])/(b[1]-a[1])
                if hit > p[0]:
                    crossings += 1
                    winding += 1 if b[1] > a[1] else -1
        return bool(crossings % 2 or winding)
    for i, triangle in enumerate(polygons):
        if i == index:
            continue
        tx, ty = zip(*triangle)
        if (len(triangle) != 3 or area(triangle) > .001*area(main) or
                max(max(tx)-min(tx), max(ty)-min(ty)) > .05*side or
                not any(on_edge(p, a, b) for p in triangle for a, b in edges) or
                any(inside(p, main) for p in triangle) or
                any(inside(p, triangle) for p in main)):
            return event, 0
        for a, b in zip(triangle, triangle[1:]+triangle[:1]):
            delta = sub(b, a)
            length2 = delta[0]**2+delta[1]**2
            if length2 <= eps**2:
                return event, 0
            cuts = {0.0, 1.0}
            for c, d in edges:
                other = sub(d, c)
                determinant = cross(delta, other)
                if abs(determinant) > eps*max(1, math.dist(a, b), math.dist(c, d)):
                    t = cross(sub(c, a), other)/determinant
                    u = cross(sub(c, a), delta)/determinant
                    if 0 <= t <= 1 and 0 <= u <= 1:
                        cuts.add(t)
                else:
                    for p in (c, d):
                        if on_edge(p, a, b):
                            cuts.add(max(0, min(1, (sub(p, a)[0]*delta[0]+sub(p, a)[1]*delta[1])/length2)))
            ordered = sorted(cuts)
            if any(inside((a[0]+(lo+hi)/2*delta[0], a[1]+(lo+hi)/2*delta[1]), main)
                   for lo, hi in zip(ordered, ordered[1:])):
                return event, 0
    return fragments[index], len(parts)-1


def simplify_drawing_contour(event):
    """Simplify a jagged single outer contour with bounded geometric error.

    Nearly rectangular contours prefer a rectangle with their original bounds.
    Other shapes retain the bounded contour reduction. Both the original fill
    and the reduced fill must later cover the measured text.
    """
    points = drawing_polygon(event, max_vertices=None)
    info = coverage_geometry(event)
    if points is None or info is None or len(points) > 4096:
        return None
    rectangle = fit_rectangular_contour(points)
    if rectangle is not None:
        raw = 'm '+f'{rectangle[0][0]:g} {rectangle[0][1]:g} l '+ ' '.join(
            f'{x:g} {y:g}' for x, y in rectangle[1:])
        return raw, info[0]
    def area(poly):
        return abs(sum(ax*by-bx*ay for (ax, ay), (bx, by) in
                       zip(poly, poly[1:]+poly[:1])))/2
    def segment_distance(point, a, b):
        vx, vy = b[0]-a[0], b[1]-a[1]
        d = vx*vx+vy*vy
        t = max(0, min(1, ((point[0]-a[0])*vx+(point[1]-a[1])*vy)/d)) if d else 0
        return math.hypot(point[0]-a[0]-t*vx, point[1]-a[1]-t*vy)
    def reduce_open(poly, tolerance):
        retain, todo = {0, len(poly)-1}, [(0, len(poly)-1)]
        while todo:
            first, last = todo.pop()
            if last <= first+1:
                continue
            distance, i = max((segment_distance(poly[j], poly[first], poly[last]), j)
                              for j in range(first+1, last))
            if distance > tolerance:
                retain.add(i); todo.extend([(first, i), (i, last)])
        return [poly[i] for i in sorted(retain)]
    xs, ys = zip(*points)
    side = min(max(xs)-min(xs), max(ys)-min(ys))
    if side <= 0:
        return None
    split = max(range(1, len(points)), key=lambda i: math.dist(points[0], points[i]))
    original_area = area(points)
    for step in range(1, 11):
        ratio = step/100
        left = reduce_open(points[:split+1], ratio*side)
        right = reduce_open(points[split:]+points[:1], ratio*side)
        reduced = left[:-1]+right[:-1]
        if (3 <= len(reduced) <= 8 and
                abs(area(reduced)-original_area) <= .05*original_area):
            raw = 'm '+f'{reduced[0][0]:g} {reduced[0][1]:g} l '+ ' '.join(
                f'{x:g} {y:g}' for x, y in reduced[1:])
            return raw, info[0]
    return None


def merge_tiled_clips(rectangles, unit):
    """Accept a gapless, non-overlapping strip partition of one rectangle.

    Preserve the union clip. Removing it would expose unseen parts of paths.
    General tiled artwork and overlapping clips are not approximated here.
    """
    if not rectangles:
        return None
    eps = 1e-5 * unit
    for axis in (0, 1):
        other = 1-axis
        reference = rectangles[0]
        if any(abs(r[other]-reference[other]) > eps or
               abs(r[other+2]-reference[other+2]) > eps for r in rectangles):
            continue
        ordered = sorted(rectangles, key=lambda r: r[axis])
        # Tiny overlaps from decimal rounding are harmless for the union;
        # actual holes and substantial overlapping layers stay unsupported.
        if any(b[axis]-a[axis+2] > eps or a[axis+2]-b[axis] >
               min(.25*unit, .05*min(a[axis+2]-a[axis], b[axis+2]-b[axis]))+eps
               for a, b in zip(ordered, ordered[1:])):
            continue
        box = list(reference)
        box[axis], box[axis+2] = ordered[0][axis], ordered[-1][axis+2]
        return tuple(box)
    return None


def caption_clip_outline(event):
    """Return one static, straight-sided scene-coordinate clip contour.

    A shared authored contour can identify a panel without approximating the
    perspective of its text. Keep the clip on that text; do not expand its ink.
    """
    if (event.state.get('p', 0) or 'iclip' in event.state or
            inline_layout_key(event) or
            re.search(r'\\(?:t|move|fad|fade)\s*\(', event.text, re.I)):
        return None
    mask = re.fullmatch(r'\(\s*(?:(\d+)\s*,\s*)?(m\s+.*?)\s*\)',
                        str(event.state.get('clip', '')), re.I)
    if mask is None or not 1 <= int(mask[1] or 1) <= 16:
        return None
    points = drawing_polygon(replace_event(event, text='{\\p1}'+mask[2]))
    scale = 2**(int(mask[1] or 1)-1)
    return tuple((x/scale, y/scale) for x, y in points) if points else None
