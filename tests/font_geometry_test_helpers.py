"""Adapt immutable historical engines and provide row-algorithm test doubles.

Production tests call the current API directly. Only historical modules receive
API adapters; mocks dispatch existing recorded/failure doubles at the extracted
function boundary instead of requiring production methods on FontMetrics.
"""
import functools, inspect, sys, importlib.util, types
from pathlib import Path
from contextlib import contextmanager
from unittest.mock import patch

ROW_NAMES = {'recover':'recover_font_row', 'recover_tracked':'recover_tracked_font_row',
    'fragment_anchor':'fit_fragment_anchor', 'authored_glyph_positions':'authored_glyph_positions',
    'matches_authored_glyph_positions':'matches_authored_glyph_positions',
    'fit_fullwidth_run':'fit_fullwidth_run'}
_reports = {}
_reference_rows = {}

@contextmanager
def historical_final_tag_policy(module):
    """Bound older byte oracles to pre-v189 serialization, keeping live pass logic."""
    original = module.compact_static_overrides
    def compact(events,max_blur,**kwargs):
        return events if kwargs.pop('final',False) else original(events,max_blur,**kwargs)
    with patch.object(module,'compact_static_overrides',compact):
        yield

@contextmanager
def historical_static_phase_policy(module):
    """Keep old whole-file oracles at their original finalization boundary.

    Rebind only immutable v185 finalization/merging code to the live module so
    pass-specific capture/ownership checks still call current implementations.
    New stage handoffs and merging are tested by unmodified v186 conversions.
    """
    name = 'historical_static_phase_v185'
    if name not in sys.modules:
        path = Path(__file__).resolve().parents[1]/'tests/references/simplify_ass_v185.py'
        spec = importlib.util.spec_from_file_location(name,path)
        reference = importlib.util.module_from_spec(spec)
        sys.modules[name] = reference
        spec.loader.exec_module(reference)
    reference = sys.modules[name]
    def bind(function):
        bound = types.FunctionType(function.__code__,module.__dict__,function.__name__,
                                   function.__defaults__,function.__closure__)
        bound.__kwdefaults__ = function.__kwdefaults__
        return bound
    original_merge = bind(reference.merge_static_timed_copies)
    def merge(events,styles,*,font_metrics=None,text_only=False):
        return (events,0) if text_only else original_merge(events,styles)
    with patch.object(module,'_finalize_text_layout',bind(reference._finalize_text_layout)), patch.object(
            module,'merge_static_timed_copies',merge), historical_final_tag_policy(module):
        yield

def font_test_report(metric):
    import simplify_ass as current
    if metric is None:return None
    if id(metric) not in _reports:_reports[id(metric)] = (metric,current.FontProcessingReport())
    return _reports[id(metric)][1]

def measurement_fonts(metric):
    if metric is None:return None
    return metric.metrics if hasattr(metric,'metrics') else metric

def row_test_call(metric,name,*args,**kwargs):
    if hasattr(metric,name):return getattr(metric,name)(*args,**kwargs)
    # Row calls use engine exports, independently of the font owner's
    # defining module. Historical owners still dispatch their methods above.
    import simplify_ass as module
    function=getattr(module,ROW_NAMES[name])
    if name in {'recover','recover_tracked','fit_fullwidth_run'}:
        kwargs['font_report']=font_test_report(metric)
    return function(metric,*args,**kwargs)

def install_row_test_doubles(module, *, historical_fade_timing=False):
    """Install normal mocks at the new function boundary, never a runtime shim."""
    if historical_fade_timing and hasattr(module,'derive_staggered_fade_cores'):
        # Historical conversion equivalence audits preserve their release's
        # timing policy. Direct pass tests still exercise the current helper;
        # check_staggered_fade_cores exercises real timing conversions.
        # v185 final phase joins are outside these old whole-file oracles;
        # check_late_static_phases_render exercises the unmodified pipeline.
        simplify = module.simplify_ass
        # Resolve before conversion observers wrap the trimming entry point.
        synchronization_owner = inspect.getmodule(getattr(
            module,'synchronize_faded_cue_handoffs',module.derive_staggered_fade_cores))
        @functools.wraps(simplify)
        def historical_conversion(*args,**kwargs):
            with patch.object(module,'derive_staggered_fade_cores',
                              lambda events,rows,sources: rows), patch.object(
                    synchronization_owner,'synchronize_faded_cue_handoffs',
                    lambda context,pairs,proven: {},create=True), historical_static_phase_policy(module):
                return simplify(*args,**kwargs)
        module.simplify_ass = historical_conversion
    if getattr(module,'_row_test_doubles_installed',False):return
    module._row_test_doubles_installed=True
    for old,new in ROW_NAMES.items():
        real=getattr(module,new)
        def dispatch(metric,*args,_old=old,_real=real,**kwargs):
            if not isinstance(metric,module.FontMetrics) and hasattr(metric,_old):
                kwargs.pop('font_report',None)
                return getattr(metric,_old)(*args,**kwargs)
            return _real(metric,*args,**kwargs)
        patch.object(module,new,dispatch).start()
        if new in ('recover_font_row','recover_tracked_font_row','fit_fullwidth_run'):
            owner=inspect.getmodule(real)
            if owner is not None and owner is not module and getattr(owner,new,None) is real:
                patch.object(owner,new,dispatch).start()
    # Vector recovery imports fitting functions directly after extraction.
    owner=inspect.getmodule(getattr(module,'recover_vector_text_cues',None))
    if owner is not None and owner is not module:
        for name in ('recover_font_row','fit_fragment_anchor'):
            patch.object(owner,name,getattr(module,name)).start()

    # Shared-interval reconstruction also imports row fitting directly.
    owner=inspect.getmodule(getattr(module,'merge_shared_interval_rows',None))
    if owner is not None and owner is not module:
        for name in ('recover_font_row','recover_tracked_font_row'):
            patch.object(owner,name,getattr(module,name)).start()

    # Fragment-phase proof imports both exact anchors and complete row fitting.
    owner=inspect.getmodule(getattr(module,'collapse_fragment_phase_rows',None))
    if owner is not None and owner is not module:
        for name in ('recover_font_row','fit_fragment_anchor'):
            patch.object(owner,name,getattr(module,name)).start()

    # Translated-phase proof imports exact authored glyph helpers directly.
    owner=inspect.getmodule(getattr(module,'collapse_translated_phase_rows',None))
    if owner is not None and owner is not module:
        for name in ('authored_glyph_positions','fit_fragment_anchor','matches_authored_glyph_positions'):
            patch.object(owner,name,getattr(module,name)).start()

    # Complete lifecycle reconstruction borrows exact glyph and row fitting.
    owner=inspect.getmodule(getattr(module,'reconstruct_glyph_lifecycles',None))
    if owner is not None and owner is not module:
        for name in ('recover_font_row','authored_glyph_positions','matches_authored_glyph_positions'):
            patch.object(owner,name,getattr(module,name)).start()

def adapt_reference_font_api(module):
    """Bridge API shape only on an immutable reference, preserving its engine."""
    if not hasattr(module,'FontSpacing') or getattr(module,'_font_reference_adapted',False):return
    module._font_reference_adapted=True
    if not hasattr(module,'FontMetrics'):module.FontMetrics=module.FontSpacing
    def row_owner(metric):
        if metric is None or isinstance(metric,module.FontSpacing):return metric
        # Recorded doubles already implement the historical row interface.
        if not isinstance(metric,module.FontMetrics):return metric
        key=(id(module),id(metric))
        if key not in _reference_rows:_reference_rows[key]=(metric,module.FontSpacing(metrics=metric))
        return _reference_rows[key][1]
    for old,new in ROW_NAMES.items():
        def row_function(metric,*args,_name=old,**kwargs):
            report=kwargs.pop('font_report',None);owner=row_owner(metric)
            try:return getattr(owner,_name)(*args,**kwargs)
            finally:
                if report is not None:report.missing_families.update(getattr(owner,'missing',()))
        setattr(module,new,row_function)
    for name,function in list(vars(module).items()):
        if not inspect.isfunction(function) or function.__module__!=module.__name__:continue
        signature=inspect.signature(function)
        row_args={key for key,param in signature.parameters.items()
            if key=='font_spacing' or 'FontSpacing' in str(param.annotation)}
        if not row_args:continue
        @functools.wraps(function)
        def adapted(*args,_function=function,_signature=signature,_row_args=row_args,**kwargs):
            report=kwargs.pop('font_report',None);kwargs.pop('outline_matcher',None)
            if 'font_metrics' in kwargs:kwargs['font_spacing']=kwargs.pop('font_metrics')
            bound=_signature.bind(*args,**kwargs)
            owners=[]
            for key in _row_args:
                if key in bound.arguments:
                    owner=row_owner(bound.arguments[key]);bound.arguments[key]=owner
                    if owner is not None and all(owner is not x for x in owners):owners.append(owner)
            before=[getattr(x,'merged',0) for x in owners]
            try:return _function(*bound.args,**bound.kwargs)
            finally:
                if report is not None:
                    report.rows_joined+=sum(getattr(x,'merged',0)-n for x,n in zip(owners,before))
                    for owner in owners:report.missing_families.update(getattr(owner,'missing',()))
        setattr(module,name,adapted)
