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
