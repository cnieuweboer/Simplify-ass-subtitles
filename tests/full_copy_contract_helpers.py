"""Behavioral copy-family timing expectations, independent of clustering policy."""
from contextlib import contextmanager
import inspect
from unittest.mock import patch

from event_evidence_test_helpers import event_comparison_fields
from _simplify_ass.subtitle_document import format_time


@contextmanager
def accepted_copy_clusters(module):
    """Observe already-authorized source membership without changing selection."""
    owner=inspect.getmodule(module.collapse_full_lyric_copies)
    select=owner.select_static_state
    clusters=[]
    def observed(*args,**kwargs):
        clusters.append(tuple(kwargs['paint_events']))
        return select(*args,**kwargs)
    with patch.object(owner,'select_static_state',observed):yield clusters


def assert_copy_family_coverage(inputs,outputs,clusters):
    """Each connected accepted family keeps exactly its authored time union."""
    originals={e.source_index:e for e in inputs}
    families=[]
    for cluster in clusters:
        members={e.source_index for e in cluster}
        touching=[family for family in families if family & members]
        families=[family for family in families if not family & members]
        members.update(*(touching or [set()]))
        families.append(members)
    for family in families:
        retained=[e for e in outputs if e.source_index in family]
        assert len(retained)==1,(family,[e.source_index for e in retained])
        caption=retained[0]
        expected=(min(originals[i].start_s for i in family),max(originals[i].end_s for i in family))
        assert (caption.start_s,caption.end_s)==expected,(family,expected,(caption.start_s,caption.end_s))
        assert (caption.start,caption.end)==tuple(map(format_time,expected))


def copy_paint_comparison_fields(event):
    """Compare every historical Event field except separately proved timing."""
    fields=event_comparison_fields(event)
    for key in ('start','end','start_s','end_s'):fields.pop(key)
    return fields
