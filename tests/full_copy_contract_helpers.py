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


def copy_cluster_ids(clusters):
    """Retain call and vote order when deciding whether a historical proof agrees."""
    return tuple(tuple(e.source_index for e in cluster) for cluster in clusters)


def assert_anchored_copy_contract(module, inputs, visible, result, clusters):
    """Check source authority and complete, once-only family handoff behavior."""
    originals={e.source_index:e for e in inputs}
    claimed=set();retained=set()
    for cluster in clusters:
        ids={e.source_index for e in cluster}
        assert len(ids)==len(cluster) and len(ids)>1
        assert not claimed & ids,('source belongs to two accepted families',claimed,ids)
        assert all(originals[e.source_index] is e for e in cluster)
        assert any(anchor.duration>0 and all(other.duration>=0 and
            min(anchor.end_s,other.end_s)-max(anchor.start_s,other.start_s)>=
            .8*min(anchor.duration,other.duration) for other in cluster) for anchor in cluster),ids
        def group(e):
            pos=module.get_pos(e.text)
            return (e.style,e.name,''.join(visible.get(e.source_index,'').split()).casefold(),
                    e.row if pos is not None else None,pos,module.placement_key(e))
        assert len({group(e) for e in cluster})==1
        assert all(e.kind=='Dialogue' and e.lyric and group(e)[2] for e in cluster)
        first=min(ids);retained.add(first);claimed.update(ids)
        caption=next(e for e in result.events if e.source_index==first)
        best=max(cluster,key=lambda e:(visible[e.source_index].count(' '),e.effect=='',-e.source_index))
        assert module.OVERRIDE_RE.sub('',caption.text)==visible[best.source_index]
        assert result.visibility_updates[first]==visible[best.source_index]
        assert caption.layer=='0' and caption.effect==''
    assert_copy_family_coverage(inputs,result.events,clusters)
    assert set(result.visibility_updates)==retained
    assert result.removed_count==len(inputs)-len(result.events)==len(claimed)-len(retained)
    assert [e.source_index for e in result.events]==[e.source_index for e in inputs
        if e.source_index not in claimed or e.source_index in retained]
    assert all(e is originals[e.source_index] for e in result.events if e.source_index not in claimed)
