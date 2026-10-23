"""Compare equivalent event semantics across evidence-storage boundaries."""

def static_span_comparison_fields(signature):
    """Preserve literal formatting and every migrated continuation distinction."""
    if not hasattr(signature,'formatting'):
        return signature
    values = dict(signature.formatting)
    continuation = signature.continuation
    if continuation.reset_style is not None:
        values['_reset_style'] = continuation.reset_style
    if continuation.alignment_set is not None:
        values['_alignment_set'] = continuation.alignment_set
    return tuple(sorted(values.items()))

def pose_comparison_fields(pose=None, state=None):
    """Compare the same proof values in typed or legacy state storage."""
    if pose is not None:
        return dict(upright_rotation=pose.upright_rotation,
                    sustained_geometry=(dict(pose.sustained_geometry)
                                        if pose.sustained_geometry is not None else None))
    state = state or {}
    return dict(upright_rotation=bool(state.get('_upright_rotation',False)),
                sustained_geometry=state.get('_sustained_geometry'))


def selection_comparison_fields(selection):
    """Retain selected history and evidence values across their storage boundary.

    Settled snapshots prove geometry/paint only: no production reader uses
    their former private parser entries. Compare all their rendered fields;
    selected parser history is compared separately by restoring its legacy
    representation in state, never by ignoring it.
    """
    fields = vars(selection).copy()
    state = dict(fields['state'])
    continuation = fields.pop('continuation',None)
    if continuation is not None:
        if continuation.reset_style is not None:
            state['_reset_style'] = continuation.reset_style
        if continuation.alignment_set is not None:
            state['_alignment_set'] = continuation.alignment_set
    if fields['settled_states'] is not None:
        fields['settled_states'] = tuple({k:v for k,v in snapshot.items()
            if k not in ('_reset_style','_alignment_set')} for snapshot in fields['settled_states'])
    fields['pose'] = pose_comparison_fields(fields.pop('pose',None),state)
    state.pop('_upright_rotation',None)
    state.pop('_sustained_geometry',None)
    fields['state'] = state
    return fields


def event_comparison_fields(event):
    """Retain history and context while canonicalizing their storage boundary."""
    fields = vars(event).copy()
    continuation = fields.pop('continuation', None)
    measurement = fields.pop('measurement', None)
    evidence = fields.pop('evidence', None)
    state = dict(fields['state'])
    if continuation is not None:
        if continuation.reset_style is not None:state['_reset_style'] = continuation.reset_style
        if continuation.alignment_set is not None:state['_alignment_set'] = continuation.alignment_set
    fields['measurement'] = ((measurement.canvas,measurement.script_wrap_mode)
        if measurement is not None else
        (fields['defaults'].get('_canvas'),fields['defaults'].get('_script_wrap_mode')))
    def formatting(values):
        return {key:value for key,value in values.items()
                if key not in ('_canvas','_script_wrap_mode')}
    state = formatting(state)
    fields['defaults'] = formatting(fields['defaults'])
    fields['styles'] = {name:formatting(style) for name,style in fields['styles'].items()}
    if evidence is not None and evidence.original_contour_points is not None:
        assert '_original_contour_points' not in state
        state['_original_contour_points'] = evidence.original_contour_points
    if evidence is not None and getattr(evidence, 'opaque_spans', None) is not None:
        assert '_opaque_spans' not in state
        state['_opaque_spans'] = evidence.opaque_spans
    # v148 wrote this value, but no production reader consumed it.
    state.pop('_composite_backdrop_bounds', None)
    fields['state'] = state
    return fields


def override_comparison_state(result):
    """Test-only legacy representation; production formatting stays clean."""
    state = result.formatting.copy()
    continuation = result.continuation
    if continuation.reset_style is not None:state['_reset_style'] = continuation.reset_style
    if continuation.alignment_set is not None:state['_alignment_set'] = continuation.alignment_set
    return state


def override_test_evaluation(module, state):
    """Decode historical test seeds explicitly, without a production adapter."""
    return module.OverrideEvaluation(
        {k:v for k,v in state.items() if k not in ('_reset_style','_alignment_set')},
        module.OverrideContinuation(state.get('_reset_style'),state.get('_alignment_set')))


def resolve_test_event(module, event):
    """Build a complete event cache for either historical or explicit ownership."""
    if hasattr(event,'continuation'):
        result = module.evaluate_effective_state(event.text,event.defaults,event.styles)
        event.state,event.continuation = result.formatting,result.continuation
    else:
        event.state = getattr(module,'_legacy_effective_state',module.effective_state)(
            event.text,event.defaults,event.styles)
    return event


def row_comparison_fields(row):
    """Compare row semantics while older engines have no backing ownership.

    An absent ownership field means an empty claim. Keep nonempty ownership
    visible to parity checks; focused tests exercise its timing handoff.
    """
    fields = vars(row).copy()
    fields.setdefault('owned_backing',())
    return fields



CONTOUR_FIELDS = frozenset({'3c', '3a', 'bord', 'xbord', 'ybord'})


def contour_independent_contract(value):
    """Compare historical reconstruction contracts across the v198 paint change.

    Exclude only contour color, opacity and width. Content, fill, timing,
    geometry, source evidence, visibility and ordering remain in the comparison.
    Use only for cross-version expectations; input immutability and live paint
    assertions must use their complete values. This never modifies an engine.
    """
    import re
    if isinstance(value, bytes):
        return contour_independent_contract(value.decode('utf-8-sig'))
    if isinstance(value, str):
        def header(match):
            tags = re.sub(r"\\(?:3c|3a|xbord|ybord|bord)[^\\}]*", '', match[0][1:-1])
            return '{'+tags+'}' if tags else ''
        return re.sub(r"\{[^}]*\}", header, value)
    if isinstance(value, dict):
        return {k:contour_independent_contract(v) for k,v in value.items()
                if k not in CONTOUR_FIELDS}
    if isinstance(value, (tuple, list)):
        return tuple(contour_independent_contract(v) for v in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(contour_independent_contract(v) for v in value)
    return value


def contour_independent_timeline(events):
    """Literal fill/layout multiplicity at every boundary, allowing phase joins."""
    from collections import Counter, defaultdict
    import simplify_ass as s
    changes = defaultdict(Counter)
    for e in events:
        if e.kind != 'Dialogue':
            continue
        obj = s.static_object_key(e,e.styles,allow_unpositioned=True)
        assert obj is not None, ('timeline requires static output',e.text)
        spans = []
        for sig,drawing,literal in obj[-1]:
            fields = tuple((k,v) for k,v in sig.formatting if k not in CONTOUR_FIELDS)
            key = (fields,sig.continuation,drawing)
            if spans and spans[-1][0] == key:
                spans[-1] = (key,spans[-1][1]+literal)
            else:
                spans.append((key,literal))
        key = obj[:-1]+(tuple(spans),)
        changes[e.start_s][key] += 1
        changes[e.end_s][key] -= 1
    live = Counter(); timeline = []
    for at,delta in sorted(changes.items()):
        live.update(delta); live = +live
        if not timeline or live != timeline[-1][1]:
            timeline.append((at,live.copy()))
    return timeline


def without_inactive_color_phase_reporting(stats):
    """Historical conversion contracts still run current paint policy.

    Assert that the newly reported limiter/emitter did nothing in these old
    fixtures, then compare their existing statistics independently of new
    effective-setting/report fields. Do not substitute any runtime behavior.
    """
    counters=('color_phase_captions_limited','color_phase_changes_removed',
              'color_phase_rate_limited','color_phase_hold_limited',
              'color_phase_captions_preserved','color_phase_changes_preserved')
    assert all(stats.get(key,0)==0 for key in counters),stats
    assert not stats.get('color_phase_limits'),stats
    reporting=set(counters)|{'color_phase_min_hold','color_phase_change_interval','color_phase_limits'}
    return {key:value for key,value in stats.items() if key not in reporting}


def prepared_source_comparison_fields(prepared):
    """Compare the source handoff before later consolidation changes its output."""
    from collections.abc import Mapping
    def snapshot(value):
        if type(value).__name__ == 'Event':
            return snapshot(event_comparison_fields(value))
        if type(value).__name__ == 'TextRow':
            return snapshot(row_comparison_fields(value))
        if isinstance(value,Mapping):
            return {k:snapshot(v) for k,v in value.items()}
        if isinstance(value,(list,tuple)):
            return tuple(snapshot(v) for v in value)
        if isinstance(value,(set,frozenset)):
            return frozenset(snapshot(v) for v in value)
        if hasattr(value,'__dict__'):
            return snapshot(vars(value))
        return value
    return snapshot((prepared.events,prepared.timing_sources,prepared.rows,
                     prepared.effects_removed,prepared.vector_captions))
