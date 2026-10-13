"""Adapt immutable historical engines and provide row-algorithm test doubles.

Production tests call the current API directly. Only historical modules receive
API adapters; mocks dispatch existing recorded/failure doubles at the extracted
function boundary instead of requiring production methods on FontMetrics.
"""
import functools, inspect, sys
from unittest.mock import patch

ROW_NAMES = {'recover':'recover_font_row', 'recover_tracked':'recover_tracked_font_row',
    'fragment_anchor':'fit_fragment_anchor', 'authored_glyph_positions':'authored_glyph_positions',
    'matches_authored_glyph_positions':'matches_authored_glyph_positions',
    'fit_fullwidth_run':'fit_fullwidth_run'}
_reports = {}
_reference_rows = {}

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
    module=sys.modules[type(metric).__module__]
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
        @functools.wraps(simplify)
        def historical_conversion(*args,**kwargs):
            with patch.object(module,'derive_staggered_fade_cores',
                              lambda events,rows,sources: rows), patch.object(
                    module,'synchronize_faded_cue_handoffs',lambda context,pairs,proven: {},create=True), patch.object(
                    module,'merge_late_static_phases',lambda events,font_metrics:(events,0),create=True):
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
