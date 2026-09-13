"""Bounded keyset listing; business eligibility and human revision rules are reused."""
import base64
import hashlib
import json
from datetime import datetime
from uuid import UUID

from .knowledge import searchable_revision
from .repositories import InMemoryRepository, Repository

PAGE_SIZE = 20


def list_knowledge(repository: Repository, cursor: str | None = None,
                   tag: str = '', review_status: str = '', query: str = '') -> dict:
    fingerprint = hashlib.sha256(json.dumps([tag, review_status, query]).encode()).hexdigest()[:16]
    after = None
    if cursor:
        try:
            stamp, result_id, scope = json.loads(base64.urlsafe_b64decode(cursor))
            if not all(isinstance(value, str) for value in (stamp, result_id, scope)):
                raise ValueError()
            after = (datetime.fromisoformat(stamp), UUID(result_id))
            if scope != fingerprint or after[0].tzinfo is None:
                raise ValueError()
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            raise ValueError('INVALID_KNOWLEDGE_CURSOR') from exc
    items, keys = [], []
    while len(items) <= PAGE_SIZE:
        rows = repository.result_page(after, PAGE_SIZE + 1)
        if not rows:
            break
        for created, result, _job, asset, history in rows:
            after = (created, result.id)
            # A per-record snapshot avoids re-querying originals/history during review
            # replay and keeps eligibility identical to search, with bounded memory.
            snapshot = InMemoryRepository()
            snapshot.results[result.job_id] = result
            snapshot.feedback[result.id] = history
            revision = searchable_revision(snapshot, result)
            if revision is None:
                continue
            tags = revision.tags if revision.tags is not None else result.tags
            state = '已人工修改' if any(d.review_status == 'edit' for d in revision.dimensions) else '已确认'
            text = f"{asset.original_filename} {asset.id} {result.id} {' '.join(tags)} {result.summary} {' '.join(d.interpretation for d in revision.dimensions)}"
            if (tag and tag not in tags) or (review_status and review_status != state) or query.lower() not in text.lower():
                continue
            items.append(dict(asset_id=asset.id, result_id=result.id, original_filename=asset.original_filename,
                              preview_url=f'/api/v1/assets/{asset.id}/thumbnail', tags=tags,
                              revision=revision.revision, review_status=state,
                              updated_at=max((f.created_at for f in history), default=None),
                              preview_text=revision.dimensions[0].interpretation[:180]))
            keys.append(after)
            if len(items) > PAGE_SIZE:
                break
        if len(rows) < PAGE_SIZE + 1:
            break
    next_cursor = None
    if len(items) > PAGE_SIZE:
        stamp, result_id = keys[PAGE_SIZE - 1]
        next_cursor = base64.urlsafe_b64encode(json.dumps([stamp.isoformat(), str(result_id), fingerprint]).encode()).decode()
    return {'items': items[:PAGE_SIZE], 'next_cursor': next_cursor}
