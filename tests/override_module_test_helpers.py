"""Observe canonical interpreter calls and engine aliases without double wrapping."""
from contextlib import contextmanager, ExitStack
import inspect
from unittest.mock import patch


@contextmanager
def patch_interpreter_bindings(engine, name, *args, **kwargs):
    """Patch one callable's defining binding and its borrowed engine binding.

    Historical single-file engines have only one binding. Share the replacement
    across both current bindings so assertions count actual calls exactly once.
    """
    original = getattr(engine, name)
    owner = inspect.getmodule(original)
    assert owner is not None and getattr(owner, name, None) is original, name
    with ExitStack() as stack:
        replacement = stack.enter_context(patch.object(engine, name, *args, **kwargs))
        if owner is not engine:
            stack.enter_context(patch.object(owner, name, replacement))
        yield replacement
