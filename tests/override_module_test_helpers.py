"""Observe canonical interpreter calls and imported test bindings once."""
from contextlib import contextmanager, ExitStack
import inspect
from unittest.mock import patch


@contextmanager
def patch_interpreter_bindings(engine, name, *args, **kwargs):
    """Patch the defining binding and known consumers with one replacement.

    Sampling, selection, freezing, static objects, compaction, karaoke, backed-glyph, moving-glyph, sliced-text and shrinking-row
    consumers import interpreter functions directly. Resolve their actual owners
    through engine exports so historical
    single-file engines still need only one binding; do not add production
    forwarding for test spies.
    """
    original = getattr(engine, name)
    owner = inspect.getmodule(original)
    assert owner is not None and getattr(owner, name, None) is original, name
    bindings = []
    consumers = [engine, owner, *(
        inspect.getmodule(getattr(engine, entry, None))
        for entry in ('sample_transform_state', 'sample_transform_states',
                      'select_static_state', 'freeze_block', 'static_object_key',
                      'compact_static_overrides', 'normalize_karaoke_completion_paint',
                      '_settled_caption_paint_samples', 'collapse_backed_glyph_pulses',
                      'literal_font_spans', 'collapse_moving_glyph_sequences',
                      'collapse_sliced_text_sequences', 'collapse_shrinking_glyph_rows',
                      'match_boundary_glyph_effects', '_glyph_replacement_row_is_clear',
                      'render_caption_spans', 'render_merged_caption',
                      'recover_vector_text_cues', 'merge_shared_interval_rows',
                      'collapse_fragment_phase_rows', 'collapse_translated_phase_rows',
                      'reconstruct_glyph_lifecycles', 'shadow_lyric_fade_core',
                      'without_inert_spacing_tail', 'upright_text_holds'))]
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
