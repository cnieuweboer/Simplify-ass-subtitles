"""ASS document decoding, records, resolved views and serialization.

Callers choose processing boundaries; each document owns its metadata and events.
Resolution returns independent formatting while borrowing lines and field order.
"""
from __future__ import annotations

import codecs
import math
import re
from dataclasses import dataclass, field, replace as dataclass_replace
from pathlib import Path
from typing import Iterable

from .event_model import Event, DocumentMeasurementContext
from .ass_overrides import (
    DEFAULT_STATE, parse_styles, resolve_event_style, evaluate_effective_state,
)

GENERATED_MARKER = "; Simplified by simplify_ass.py"


def mark_generated(lines: list[str]) -> list[str]:
    """Place one output marker inside Script Info, relocating legacy markers."""
    lines = [line for line in lines if not line.strip().casefold().startswith(
        "; static vector support prototype ")]
    if not any(line.strip().casefold() == "[script info]" for line in lines):
        return lines
    marked = [line for line in lines if line.strip() != GENERATED_MARKER]
    header = next(i for i,line in enumerate(marked)
                  if line.strip().casefold() == "[script info]")
    marked.insert(header+1,GENERATED_MARKER)
    return marked


@dataclass
class SubtitleDocument:
    """ASS records and metadata shared by parsing, processing and rendering.

    Event indices refer to lines in this document, never another document.
    Parsing leaves event state unresolved; each processing boundary prepares
    its own state without changing the original styles or event objects.
    """
    lines: list[str]
    styles: dict
    events: dict[int,Event]
    fields: list[str]
    scaled_borders: bool
    peak: int
    wrap_mode: int
    measurement: DocumentMeasurementContext = field(default_factory=DocumentMeasurementContext)


def peak_concurrent_events(events: Iterable[Event]) -> int:
    """Count active Dialogue events, including drawings, on [start, end).

    Comments and empty/reversed intervals do not render. Aggregate equal
    boundaries so touching captions never count as overlapping, regardless
    of source order. Use serialized times so rounding a generated boundary
    cannot create a phantom overlap. Only distinct timestamps are sorted.
    """
    boundaries: dict[float,int] = {}
    for e in events:
        if e.kind != "Dialogue":
            continue
        start,end = parse_time(e.start),parse_time(e.end)
        if start < end:
            boundaries[start] = boundaries.get(start,0)+1
            boundaries[end] = boundaries.get(end,0)-1
    active = peak = 0
    for time in sorted(boundaries):
        active += boundaries[time]
        peak = max(peak,active)
    return peak


def parse_time(value: str) -> float:
    h, m, s = value.strip().split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def format_time(seconds: float) -> str:
    # ASS convention normally uses centiseconds.
    seconds = max(0.0, seconds)
    centis = int(round(seconds * 100))
    h, rem = divmod(centis, 360000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


EVENT_FIELDS = ["layer", "start", "end", "style", "name", "marginl", "marginr", "marginv", "effect", "text"]


def parse_dialogue(line: str, index: int, fields: list[str] | None = None) -> Event | None:
    line = line.lstrip()
    if ":" not in line:
        return None
    kind, rest = line.split(":", 1)
    if kind.lower() not in {"dialogue", "comment"}:
        return None
    fields = fields or EVENT_FIELDS
    parts = rest.lstrip().split(",", len(fields)-1)
    if len(parts) != len(fields):
        return None
    data = dict(zip(fields, parts))
    try:
        start_s, end_s = parse_time(data["start"]), parse_time(data["end"])
    except (ValueError, KeyError):
        return None
    return Event(kind.title(), data.get("layer", "0").strip(),
                 format_time(start_s), format_time(end_s), data.get("style", "Default").strip(),
                 data.get("name", data.get("actor", "")).strip(),
                 data.get("marginl", "0").strip(), data.get("marginr", "0").strip(),
                 data.get("marginv", "0").strip(), data.get("effect", "").strip(),
                 data.get("text", ""), start_s, end_s, index)


def read_subtitle(path: Path, encoding: str | None = None) -> str:
    """Decode Unicode strictly; legacy encodings require an explicit choice."""
    data = path.read_bytes()
    if encoding is None:
        if data.startswith((codecs.BOM_UTF32_LE, codecs.BOM_UTF32_BE)):
            encoding = "utf-32"
        elif data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
            encoding = "utf-16"
        else:
            encoding = "utf-8-sig"
    try:
        text = data.decode(encoding).lstrip("\ufeff")
    except UnicodeError as exc:
        raise ValueError(f"{path}: cannot decode as {encoding}; specify the correct "
                         "--encoding (for example cp1252 or utf-16-le).") from exc
    if "\x00" in text:
        raise ValueError(f"{path}: decoded text contains NUL characters; check "
                         "--encoding (BOM-less UTF-16 needs utf-16-le or utf-16-be).")
    return text


def script_resolution(lines, axis):
    default = 384 if axis == 'x' else 288
    for line in lines:
        if line.strip().lower().startswith('playres'+axis+':'):
            try:
                value = float(line.split(':', 1)[1])
                return value if math.isfinite(value) and value > 0 else default
            except ValueError:
                return default
    return default


def parse_subtitle_document(raw: str) -> SubtitleDocument:
    """Parse ASS records once, retaining CR/LF boundaries and metadata lines.

    Unicode line/paragraph separators remain literal event text. A final
    empty split record is retained; the renderer chooses the newline policy.
    """
    lines = re.split(r'\r\n|\r|\n', raw)
    styles = parse_styles(lines)
    unit = script_resolution(lines, 'y')/1080
    section, fields, events, wrap_mode, canvas = '', EVENT_FIELDS, {}, 0, {}
    for index, line in enumerate(lines):
        clean = line.strip()
        if clean.startswith('['):
            section = clean.lower()
        elif section == '[script info]' and clean.casefold().startswith(('playresx:','playresy:')):
            key,value = clean.split(':',1)
            try:
                dimension = float(value)
                if math.isfinite(dimension) and dimension > 0:
                    canvas[key.casefold()] = dimension
            except ValueError:
                pass
        elif section.casefold() == '[script info]' and clean.casefold().startswith('wrapstyle:'):
            try:
                value = int(clean.split(':', 1)[1].strip())
                if value in range(4):
                    wrap_mode = value
            except ValueError:
                pass
        elif section == '[events]' and clean.lower().startswith('format:'):
            fields = [x.strip().lower() for x in clean.split(':', 1)[1].split(',')]
        elif section == '[events]':
            event = parse_dialogue(line, index, fields)
            if event is not None:
                event.unit = unit
                event.defaults = resolve_event_style(styles, event.style)
                event.styles = styles
                events[index] = event
    scaled_borders = any(line.strip().lower() == 'scaledborderandshadow: yes'
                         for line in lines)
    measurement = DocumentMeasurementContext(
        (canvas['playresx'],canvas['playresy'])
        if 'playresx' in canvas and 'playresy' in canvas else None)
    for event in events.values():
        event.measurement = measurement
    return SubtitleDocument(lines,styles,events,fields,scaled_borders,
                            peak_concurrent_events(events.values()),wrap_mode,measurement)


def read_subtitle_document(path: Path, encoding: str | None = None) -> SubtitleDocument:
    """Decode a source file and parse its ASS document."""
    return parse_subtitle_document(read_subtitle(path,encoding))


def _resolve_document_state(document: SubtitleDocument) -> SubtitleDocument:
    """Prepare independent, fully resolved events for measurement and supports.

    Script wrapping is measurement metadata, not an override tag default.
    Fresh event/state/style objects also isolate source drawing evidence from
    the text engine's temporary proof metadata.
    """
    styles = {name:state.copy() for name,state in document.styles.items()}
    default = DEFAULT_STATE.copy()
    measurement = dataclass_replace(document.measurement,script_wrap_mode=document.wrap_mode)
    events = {}
    for index,event in document.events.items():
        defaults = resolve_event_style(styles,event.style,default)
        evaluated = evaluate_effective_state(event.text,defaults,styles)
        events[index] = dataclass_replace(event,defaults=defaults,styles=styles,measurement=measurement,
            state=evaluated.formatting,continuation=evaluated.continuation)
    return dataclass_replace(document,styles=styles,events=events,measurement=measurement)


def render_subtitle_document(
    document: SubtitleDocument,
    events: Iterable[Event],
    *,
    final_newline: bool = False,
) -> str:
    """Replace the event region and mark generated output in one shared renderer.

    Preserve the established metadata boundaries and SSA Actor/Marked aliases.
    Text-engine output preserves source terminal newlines; final supported
    output ends with exactly one newline. All output uses LF records.
    """
    rendered = []
    for event in events:
        data = dict(zip(EVENT_FIELDS,event.fields()))
        data.update(actor=event.name,marked='Marked=0')
        rendered.append(f'{event.kind}: '+','.join(data.get(key,'')
                        for key in document.fields))
    lines = document.lines
    indices = sorted(document.events)
    if indices:
        lines = lines[:indices[0]]+rendered+lines[indices[-1]+1:]
    elif rendered:
        section = next(i for i,line in enumerate(lines)
                       if line.strip().lower() == '[events]')
        end = next((i for i in range(section+1,len(lines))
                    if lines[i].strip().startswith('[')),len(lines))
        lines = lines[:end]+rendered+lines[end:]
    output = '\n'.join(mark_generated(lines))
    if final_newline:
        return output.rstrip('\n')+'\n'
    # The split document retains all terminal empty records, including an
    # absent final newline. No phase-specific trimming is needed here.
    return output


def write_subtitle_document(
    output: Path,
    document: SubtitleDocument,
    events: Iterable[Event],
    *,
    final_newline: bool = False,
) -> None:
    """Write the shared rendering as UTF-8 with BOM."""
    output.write_text(render_subtitle_document(document,events,
                      final_newline=final_newline),encoding='utf-8-sig')


def load_subtitle_events(path, encoding=None):
    """Compatibility reader returning resolved events and their document indices."""
    document = _resolve_document_state(read_subtitle_document(path,encoding))
    return (document.lines,list(document.events.values()),document.fields,
            list(document.events))
