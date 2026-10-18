"""Observe canonical interpreter calls and imported test bindings once."""
from contextlib import contextmanager, ExitStack
import inspect
from unittest.mock import patch


@contextmanager
def patch_interpreter_bindings(engine, name, *args, **kwargs):
    """Patch the defining binding and known consumers with one replacement.

    Samplers, selection and freezing import interpreter functions directly. Resolve
    their actual owners through engine exports so historical single-file engines
    still need only one binding; do not add production forwarding for test spies.
    """
    original = getattr(engine, name)
    owner = inspect.getmodule(original)
    assert owner is not None and getattr(owner, name, None) is original, name
    bindings = []
    consumers = [engine, owner, *(
        inspect.getmodule(getattr(engine, entry, None))
        for entry in ('sample_transform_state', 'sample_transform_states', 'select_static_state', 'freeze_block'))]
    for consumer in consumers:
        if (consumer is not None and consumer not in bindings and
                getattr(consumer, name, None) is original):
            bindings.append(consumer)
    with ExitStack() as stack:
        replacement = stack.enter_context(patch.object(engine, name, *args, **kwargs))
        for binding in bindings:
            if binding is not engine:
                stack.enter_context(patch.object(binding, name, replacement))
        yield replacement
