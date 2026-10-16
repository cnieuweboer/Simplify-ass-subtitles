"""Private exact-font discovery, shaping and measurement owner.

Consumers borrow immutable faces/results; subtitle reconstruction policy and
caller-owned reports remain in simplify_ass.py. Optional backends stay lazy.
"""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import math
import unicodedata


@dataclass(frozen=True)
class FontFace:
    """An exact collection face and its requested variable-font coordinates."""
    path: str
    index: int
    cmap: frozenset[int]
    coordinates: tuple[tuple[str,float],...] = ()

    @property
    def key(self):
        # Keep static-face cache identities unchanged.
        return (self.path,self.index,self.coordinates) if self.coordinates else (self.path,self.index)


@dataclass(frozen=True)
class FontCapabilities:
    """Installed measurement backends, independent of per-face cache contents."""
    available: bool = False
    raqm: bool = False
    harfbuzz: bool = False


@dataclass(frozen=True)
class FontLineInkMetrics:
    """Immutable baseline-relative boxes in line order and ASS ascent ratio."""
    ascent_ratio: float
    boxes: tuple[tuple[int,int,int,int] | None,...]


class FontMetrics:
    """Exact-font discovery, instances, shaping and outline measurements.

    One owner retains reusable font caches across a conversion batch. Consumers
    borrow immutable faces/measurement results; open_face() leases a font whose
    caller must close it. Subtitle timing and replacement policy live elsewhere.
    """
    def __init__(self, directories=()):
        self._faces = {}
        self._cmaps = {}
        self._loaded = {}
        self._font_bytes = {}
        self._variable_axes = {}
        self._variable_slants = {}
        self._instance_bytes = {}
        self._glyph_fragments = {}
        self._cubic_outlines = {}
        self._ass_em_scales = {}
        self.available = False
        self._line_ascent_ratios = {}
        self.capabilities = FontCapabilities()
        try:
            from PIL import ImageFont
            from fontTools.ttLib import TTFont, TTCollection
        except ImportError:
            return
        self._imagefont = ImageFont
        self._harfbuzz = None
        self._shaping_fonts = {}
        try:
            import uharfbuzz
            self._harfbuzz = uharfbuzz
        except ImportError:
            pass  # RAQM installations do not require an additional backend.
        self.available = True
        from PIL import features
        self.capabilities = FontCapabilities(True,features.check_feature("raqm"),
                                            self._harfbuzz is not None)
        import os
        roots = list(directories) + [Path(__file__).resolve().parent.parent / "fonts"]
        if os.name == "nt":
            roots += [Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"]
            if os.environ.get("LOCALAPPDATA"):
                roots += [Path(os.environ["LOCALAPPDATA"]) / "Microsoft/Windows/Fonts"]
        else:
            roots += [Path('/usr/share/fonts'), Path('/usr/local/share/fonts'),
                      Path.home()/'.local/share/fonts', Path('/Library/Fonts'),
                      Path('/System/Library/Fonts'), Path.home()/'Library/Fonts']
        # Resolve path aliases while preserving the first directory's priority.
        roots = list(dict.fromkeys(Path(root).resolve() for root in roots))
        seen = set()
        for root in roots:
            if not root.is_dir():
                continue
            for path in sorted(root.rglob('*')):
                if path.suffix.lower() not in {'.ttf','.otf','.ttc','.otc'} or path in seen:
                    continue
                seen.add(path)
                collection = None
                faces = []
                try:
                    if path.suffix.lower() in {'.ttc','.otc'}:
                        collection = TTCollection(str(path), lazy=True)
                        faces = collection.fonts
                    else:
                        faces = [TTFont(str(path), lazy=True)]
                    for index, face in enumerate(faces):
                        names = {n.toUnicode().strip().casefold() for n in face['name'].names
                                 if n.nameID in {1,4,6,16} and n.toUnicode().strip()}
                        flags = face['head'].macStyle
                        selection = face['OS/2'].fsSelection if 'OS/2' in face else 0
                        bold = bool(flags & 1 or selection & 32)
                        italic = bool(flags & 2 or selection & 1)
                        if 'fvar' in face:
                            axes = {a.axisTag:(a.minValue,a.defaultValue,a.maxValue)
                                    for a in face['fvar'].axes}
                            self._variable_axes[(str(path),index)] = axes
                            self._variable_slants[(str(path),index)] = [
                                (i.coordinates.get('wght',400),i.coordinates['slnt'])
                                for i in face['fvar'].instances if i.coordinates.get('slnt',0)]
                            families = {n.toUnicode().strip().casefold() for n in face['name'].names
                                        if n.nameID in {1,16} and n.toUnicode().strip()}
                            # Named instances retain their authored coordinates
                            # when selected by a full/PostScript instance name.
                            instance_names = set()
                            for instance in face['fvar'].instances:
                                subfamily = face['name'].getDebugName(instance.subfamilyNameID)
                                aliases = {family+' '+subfamily.casefold() for family in families
                                           if subfamily}
                                ps_name = face['name'].getDebugName(instance.postscriptNameID)
                                if ps_name:
                                    aliases.add(ps_name.casefold())
                                coords = tuple(sorted(instance.coordinates.items()))
                                values = dict(coords)
                                ib = values.get('wght',700 if bold else 400) >= 600
                                ii = bool(values.get('ital',int(italic)) or values.get('slnt',0))
                                # The variable file's own regular face names
                                # still accept b/i requests. A default-instance
                                # PostScript alias must not lock them to regular.
                                if not ib and not ii and values == {tag:a[1] for tag,a in axes.items()}:
                                    aliases -= names
                                for name in aliases:
                                    self._faces.setdefault((name,ib,ii),[]).append((str(path),index,coords))
                                instance_names.update(aliases)
                            for name in names-instance_names:
                                for requested_bold in (False,True):
                                    for requested_italic in (False,True):
                                        coordinates = self.variable_coordinates(axes,requested_bold,
                                            requested_italic,bold,italic)
                                        if coordinates is not None:
                                            self._faces.setdefault((name,requested_bold,requested_italic),[]).append(
                                                (str(path),index))
                            continue
                        for name in names:
                            self._faces.setdefault((name,bold,italic),[]).append((str(path),index))
                except Exception:
                    # An unreadable font must not prevent subtitle processing.
                    pass
                finally:
                    if collection is not None:
                        collection.close()
                    else:
                        for face in faces:
                            face.close()

    @staticmethod
    def requested_weight(bold) -> float:
        """ASS boolean bold is 700; explicit positive weights stay numeric."""
        return 700 if bold in (-1,1,True) else float(bold) if bold > 1 else 400

    @staticmethod
    def variable_coordinates(axes, bold, italic, default_bold=False, default_italic=False):
        """Select authored weight/style; leave unrelated axes at their defaults.

        Follow the requested variable variant, independent of libass's
        current regular-only behavior. No replacement font files are written.
        """
        coords = {tag:bounds[1] for tag,bounds in axes.items()}
        weight = FontMetrics.requested_weight(bold)
        if 'wght' in axes:
            lo,_,hi = axes['wght']
            coords['wght'] = min(hi,max(lo,weight))
            if (weight >= 600) != (coords['wght'] >= 600):
                return None
        elif bool(bold) != default_bold:
            return None
        if 'ital' in axes:
            lo,_,hi = axes['ital']
            coords['ital'] = min(hi,max(lo,int(bool(italic))))
        if 'slnt' in axes:
            lo,default,hi = axes['slnt']
            needs_slant = italic and not coords.get('ital',0)
            coords['slnt'] = (default if default else min(hi,max(lo,-12))) if needs_slant else min(hi,max(lo,0))
            # Some fonts expose only positive slant angles.
            if needs_slant and coords['slnt'] == 0 and hi > 0:
                coords['slnt'] = min(hi,12)
        actual_italic = bool(coords.get('ital',0) or coords.get('slnt',0))
        if not {'ital','slnt'} & axes.keys():
            actual_italic = default_italic
        if actual_italic != bool(italic):
            return None
        return tuple(sorted(coords.items()))

    def matching_face(self, family: str, bold, italic: bool):
        """Prefer the requested weight, falling back within the exact name.

        Renderers can embolden a regular face when no bold face is embedded.
        A bold-only named face can also be used with ASS's bold flag unset.
        Its advances are only a candidate: the row must still pass the font
        measurement and position checks. Never change family or italic style.
        """
        requested_bold = self.requested_weight(bold) >= 600
        for weight in (requested_bold,not requested_bold):
            for candidate in self._faces.get((family.strip().casefold(),weight,bool(italic)),()):
                path,index = candidate[:2]
                coordinates = candidate[2] if len(candidate) == 3 else ()
                if len(candidate) == 2 and (path,index) in self._variable_axes:
                    coordinates = self.variable_coordinates(self._variable_axes[(path,index)],
                        bold if weight == requested_bold else weight,italic,weight,italic)
                    if coordinates is None:
                        continue
                    slants = self._variable_slants.get((path,index),())
                    values = dict(coordinates)
                    if slants and values.get('slnt',0) and not values.get('ital',0):
                        values['slnt'] = min(slants,key=lambda item:abs(item[0]-self.requested_weight(bold)))[1]
                        coordinates = tuple(sorted(values.items()))
                cmap = self.codepoints(path,index)
                if cmap is not None:
                    return FontFace(path,index,cmap,coordinates)
        return None

    def face_data(self, face):
        """Share one in-memory instance across shaping, metrics and outlines."""
        if face.path not in self._font_bytes:
            self._font_bytes[face.path] = Path(face.path).read_bytes()
        if not face.coordinates:
            return self._font_bytes[face.path],face.index
        if face.key not in self._instance_bytes:
            from fontTools.ttLib import TTFont
            from fontTools.varLib.instancer import instantiateVariableFont
            try:
                with TTFont(BytesIO(self._font_bytes[face.path]),fontNumber=face.index) as font:
                    instantiateVariableFont(font,dict(face.coordinates),inplace=True)
                    data = BytesIO()
                    font.save(data)
                    self._instance_bytes[face.key] = data.getvalue()
            except Exception as exc:
                raise ValueError('Cannot measure requested variable-font instance') from exc
        # An instance serialized from a collection is a single in-memory face.
        return self._instance_bytes[face.key],0

    def open_face(self, face):
        from fontTools.ttLib import TTFont
        data,index = self.face_data(face)
        return TTFont(BytesIO(data),fontNumber=index,lazy=True)

    def codepoints(self, path: str, index: int):
        """Cache coverage only for matched faces; None marks an unreadable face."""
        key = (path,index)
        if key not in self._cmaps:
            from fontTools.ttLib import TTFont
            face = None
            try:
                # fontNumber selects TTC/OTC faces without opening their peers.
                face = TTFont(path,fontNumber=index,lazy=True)
                self._cmaps[key] = frozenset((face.getBestCmap() or {}).keys())
            except Exception:
                # Retain later candidates for the same exact name and weight.
                self._cmaps[key] = None
            finally:
                if face is not None:
                    face.close()
        return self._cmaps[key]

    def measure(self, face, text: str, kerning: bool = False, *,
                ligatures: bool = True) -> float:
        """Return exact-face shaped advances at 1024 px using RAQM or HarfBuzz.

        Direct HarfBuzz avoids RAQM's separate FriBiDi DLL on Windows. The
        caller still validates direction, glyph coverage and the complete row;
        this method never substitutes fonts or estimates spaces geometrically.
        """
        if not text:
            return 0.0
        key = face.key
        data,index = self.face_data(face)
        if key not in self._loaded:
            self._loaded[key] = self._imagefont.truetype(BytesIO(data),1024,index=index)
        font = self._loaded[key]
        if font.layout_engine == self._imagefont.Layout.RAQM:
            features = ["kern" if kerning else "-kern"]
            if not ligatures:
                features.extend(("-liga","-clig"))
            return font.getlength(text,features=features)
        hb = self._harfbuzz
        if hb is None:
            raise ValueError("Font measurement needs RAQM or uharfbuzz")
        if key not in self._shaping_fonts:
            hb_face = hb.Face(data,index)
            if not hb_face.upem:
                raise ValueError("Invalid font face")
            hb_font = hb.Font(hb_face)
            hb.ot_font_set_funcs(hb_font)
            # 26.6 pixel units retain subpixel precision like FreeType/Pillow.
            hb_font.scale = (1024*64,1024*64)
            self._shaping_fonts[key] = hb_font
        buffer = hb.Buffer()
        buffer.add_str(text)
        buffer.guess_segment_properties()
        if buffer.direction != "ltr":
            raise ValueError("This row reconstruction requires horizontal LTR text")
        features = {"kern":bool(kerning)}
        if not ligatures:
            features.update(liga=False,clig=False)
        hb.shape(self._shaping_fonts[key],buffer,features)
        if any(info.codepoint == 0 for info in buffer.glyph_infos):
            raise ValueError("Shaping produced a missing glyph")
        if any(position.y_advance for position in buffer.glyph_positions):
            raise ValueError("Vertical glyph advances are unsupported")
        return sum(position.x_advance for position in buffer.glyph_positions)/64

    def fragmented_glyph(self, face, glyph: str) -> bool | None:
        """Inspect only requested exact-face outlines; unreadable stays unknown.

        A stamp has at least 64 closed contours, with at least 90 percent
        smaller than one percent of its overall control-point bounding box.
        This alone never authorizes deleting text: the decoration pass also
        requires dense scattered placement and an independent held caption.
        """
        key = (face.key,glyph)
        if key not in self._glyph_fragments:
            self._glyph_fragments[key] = None
            font = None
            try:
                from fontTools.pens.recordingPen import DecomposingRecordingPen
                font = self.open_face(face)
                glyphs = font.getGlyphSet()
                pen = DecomposingRecordingPen(glyphs)
                glyphs[font.getBestCmap()[ord(glyph)]].draw(pen)
                contours,points = [],[]
                for op,coords in pen.value:
                    if op == "closePath":
                        if points:
                            contours.append(points)
                        points = []
                    elif op == "endPath":
                        raise ValueError("Open glyph contour")
                    else:
                        points.extend(p for p in coords if p is not None)
                def box_area(points):
                    xs,ys = zip(*points)
                    return (max(xs)-min(xs))*(max(ys)-min(ys))
                if not contours or any(not math.isfinite(v)
                        for contour in contours for point in contour for v in point):
                    raise ValueError("Empty or invalid glyph outline")
                self._glyph_fragments[key] = False
                if len(contours) >= 64:
                    area = box_area([p for contour in contours for p in contour])
                    self._glyph_fragments[key] = area > 0 and sum(
                        box_area(contour) <= .01*area for contour in contours) >= .9*len(contours)
            except Exception:
                self._glyph_fragments[key] = None
            finally:
                if font is not None:
                    font.close()
        return self._glyph_fragments[key]

    def cubic_outline(self, face, text: str) -> tuple | None:
        """Cache exact-face contour topology and points for requested text.

        Font coordinates remain unscaled; callers must prove size, placement
        and cue ownership separately. Quadratic curves are converted exactly
        to cubics, and composite glyphs use the same decomposed pen path.
        Contextual shaping and missing glyphs cannot authorize recovery.
        """
        cmap = face.cmap
        key = (face.key,text)
        if key not in self._cubic_outlines:
            self._cubic_outlines[key] = None
            font = None
            try:
                from fontTools.pens.basePen import BasePen
                if any(ord(c) not in cmap or unicodedata.combining(c) or
                       unicodedata.bidirectional(c) in {'R','AL','AN'} for c in text):
                    return None
                font = self.open_face(face)
                glyphs, mapping = font.getGlyphSet(),font.getBestCmap()
                class CubicPen(BasePen):
                    def __init__(self):
                        super().__init__(glyphs)
                        self.offset, self.tokens = 0.0, []
                    def add(self, op, *points):
                        self.tokens.append(op)
                        for x,y in points:
                            self.tokens.extend((x+self.offset,-y))
                    def _moveTo(self,p): self.add('m',p)
                    def _lineTo(self,p): self.add('l',p)
                    def _curveToOne(self,a,b,c): self.add('b',a,b,c)
                    def _qCurveToOne(self,b,c):
                        a = self._getCurrentPoint()
                        self._curveToOne(tuple((x+2*y)/3 for x,y in zip(a,b)),
                                         tuple((x+2*y)/3 for x,y in zip(c,b)),c)
                    def _closePath(self): pass
                    def _endPath(self): raise ValueError('Open font contour')
                pen = CubicPen()
                for char in text:
                    glyph = glyphs[mapping[ord(char)]]
                    glyph.draw(pen)
                    pen.offset += glyph.width
                if (not pen.tokens or not pen.offset or
                        abs(self.measure(face,text,False)*font['head'].unitsPerEm/1024-
                            pen.offset) > font['head'].unitsPerEm/1024):
                    return None
                self._cubic_outlines[key] = (tuple(pen.tokens),font['head'].unitsPerEm)
            except Exception:
                pass  # Unreadable/unsupported outlines are not evidence.
            finally:
                if font is not None:
                    font.close()
        return self._cubic_outlines[key]

    def ass_em_scale(self, face) -> float | None:
        """Cache exact-face Windows line metrics used for ASS font sizing."""
        key = face.key
        if key not in self._ass_em_scales:
            self._ass_em_scales[key] = None
            font = None
            try:
                font = self.open_face(face)
                height = font['OS/2'].usWinAscent+font['OS/2'].usWinDescent
                em = font['head'].unitsPerEm
                if height > 0 and em > 0:
                    self._ass_em_scales[key] = em/height
            except Exception:
                pass  # Unsupported metrics cannot prove identical placement.
            finally:
                if font is not None:
                    font.close()
        return self._ass_em_scales[key]

    def line_ink_metrics(self, face: FontFace, lines: list[str], *,
                         kerning: bool = False) -> FontLineInkMetrics | None:
        """Return baseline-relative ink at 1024 px for an already measured face.

        RAQM supplies raster bounds; direct HarfBuzz supplies outward-rounded
        shaped glyph bounds when RAQM is absent. Both borrow the exact face
        already loaded by measure(). Unsupported or unmeasured faces stay
        unknown. Blank lines retain their slot without requesting ink.
        """
        font = self._loaded.get(face.key)
        if font is None:
            return None
        raqm = font.layout_engine == self._imagefont.Layout.RAQM
        hb_font = self._shaping_fonts.get(face.key)
        if not raqm and (self._harfbuzz is None or hb_font is None):
            return None
        if face.key not in self._line_ascent_ratios:
            with self.open_face(face) as tf:
                os2 = tf['OS/2']
                self._line_ascent_ratios[face.key] = os2.usWinAscent/(os2.usWinAscent+os2.usWinDescent)
        if raqm:
            features = ['kern' if kerning else '-kern']
            boxes = tuple(font.getbbox(line,anchor='ls',features=features)
                          if line.strip() else None for line in lines)
            return FontLineInkMetrics(self._line_ascent_ratios[face.key],boxes)
        boxes = []
        for line in lines:
            if not line.strip():
                boxes.append(None)
                continue
            buffer = self._harfbuzz.Buffer()
            buffer.add_str(line)
            buffer.guess_segment_properties()
            if buffer.direction != 'ltr':
                return None
            self._harfbuzz.shape(hb_font,buffer,{'kern':bool(kerning)})
            x, glyph_boxes = 0, []
            for info, position in zip(buffer.glyph_infos,buffer.glyph_positions):
                if not info.codepoint or position.y_advance:
                    return None
                extents = hb_font.get_glyph_extents(info.codepoint)
                if extents is None:
                    return None
                # Cached HarfBuzz fonts use 26.6 units at 1024 px. Their y
                # axis points up; caption geometry uses baseline-relative y down.
                if extents.width and extents.height:
                    left = x+position.x_offset+extents.x_bearing
                    top = -position.y_offset-extents.y_bearing
                    right, bottom = left+extents.width, top-extents.height
                    glyph_boxes.append((min(left,right),min(top,bottom),
                                        max(left,right),max(top,bottom)))
                x += position.x_advance
            if not glyph_boxes:
                return None
            # Pillow bounds include leading/trailing advances as well as ink
            # overhangs. Preserve that conservative horizontal convention.
            boxes.append((math.floor(min(0,min(b[0] for b in glyph_boxes))/64),
                          math.floor(min(b[1] for b in glyph_boxes)/64),
                          math.ceil(max(x,max(b[2] for b in glyph_boxes))/64),
                          math.ceil(max(b[3] for b in glyph_boxes)/64)))
        return FontLineInkMetrics(self._line_ascent_ratios[face.key],tuple(boxes))
