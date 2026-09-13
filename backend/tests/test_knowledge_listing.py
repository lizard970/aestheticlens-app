from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import app.main as main
from app.knowledge_listing import list_knowledge
from app.models import Asset, FeedbackCreate
from app.repositories import InMemoryRepository
from app.reviews import ReviewService
from app.thumbnails import thumbnail
from test_semantic_search import add_case, confirm


def test_cursor_pages_are_twenty_lightweight_items_without_full_scan_or_details(monkeypatch):
    repository = InMemoryRepository()
    reviews = ReviewService(repository)
    cases = [add_case(repository, f'case {i}') for i in range(45)]
    for result in cases:
        confirm(reviews, result)
    def forbidden(*args):
        raise AssertionError('Listing must not load all results, bytes or call per-case detail queries')
    monkeypatch.setattr(repository, 'list_results', forbidden)
    monkeypatch.setattr(repository, 'get_result', forbidden)
    monkeypatch.setattr(repository, 'get_asset_bytes', forbidden)
    monkeypatch.setattr(main, 'repository', repository)
    client = TestClient(main.app)
    page1 = client.get('/api/v1/knowledge/cases').json()
    assert len(page1['items']) == 20
    assert page1['next_cursor']
    assert set(page1['items'][0]) == {'asset_id', 'result_id', 'original_filename', 'preview_url', 'tags', 'revision', 'review_status', 'updated_at', 'preview_text'}
    assert page1['items'][0]['preview_url'].endswith('/thumbnail')
    page2 = client.get('/api/v1/knowledge/cases', params={'cursor': page1['next_cursor']}).json()
    page3 = client.get('/api/v1/knowledge/cases', params={'cursor': page2['next_cursor']}).json()
    assert len(page2['items']) == 20
    assert len(page3['items']) == 5 and page3['next_cursor'] is None
    expected = sorted(cases, key=lambda result: (repository.result_created_at[result.id], result.id))
    assert [row['result_id'] for page in (page1, page2, page3) for row in page['items']] == [str(result.id) for result in expected]
    assert client.get('/api/v1/knowledge/cases', params={'cursor': 'invalid'}).status_code == 422
    assert client.get('/api/v1/knowledge/cases', params={'cursor': page1['next_cursor'], 'tag': 'changed'}).status_code == 422


def test_filters_and_eligibility_still_use_final_reviews_across_pages():
    repository = InMemoryRepository()
    reviews = ReviewService(repository)
    for i in range(23):
        confirm(reviews, add_case(repository, 'unrelated'))
    case = add_case(repository, 'original')
    confirm(reviews, case)
    reviews.save(case.id, FeedbackCreate(feedback_type='edit', target_path='/dimensions/style', base_revision=5,
        corrected_value={'observation': 'human', 'interpretation': 'unique human phrase', 'tags': ['human-tag']}))
    add_case(repository, 'unconfirmed', tags=['human-tag'])
    confirm(reviews, add_case(repository, 'mock', mode='mock', tags=['human-tag']))
    rejected = add_case(repository, tags=['human-tag'])
    confirm(reviews, rejected)
    reviews.save(rejected.id, FeedbackCreate(feedback_type='reject', target_path='/dimensions/style', base_revision=5))
    excluded = add_case(repository, tags=['human-tag'])
    confirm(reviews, excluded)
    reviews.save(excluded.id, FeedbackCreate(feedback_type='edit', target_path='/knowledge_excluded', corrected_value=True, base_revision=5))
    invalid = add_case(repository, tags=['human-tag'])
    confirm(reviews, invalid)
    repository.results[invalid.job_id].dimensions[0].evidence_refs = ['feature:missing#/value']
    page = list_knowledge(repository, tag='human-tag', review_status='已人工修改', query='unique human phrase')
    assert [item['result_id'] for item in page['items']] == [case.id]
    assert page['next_cursor'] is None
    assert list_knowledge(repository, tag='human-tag', review_status='已确认')['items'] == []


def test_cursor_survives_deleted_anchor_and_tied_creation_times():
    repository = InMemoryRepository()
    cases = [add_case(repository) for _ in range(22)]
    stamp = repository.result_created_at[cases[0].id]
    for case in cases:
        repository.result_created_at[case.id] = stamp
        confirm(ReviewService(repository), case)
    first = list_knowledge(repository)
    ids = [item['result_id'] for item in first['items']]
    repository.delete_knowledge_case(ids[-1])
    last = list_knowledge(repository, first['next_cursor'])
    assert len(last['items']) == 2
    assert not set(ids) & {item['result_id'] for item in last['items']}


def test_thumbnail_is_small_cached_and_does_not_modify_original(monkeypatch):
    repository = InMemoryRepository()
    output = BytesIO()
    Image.new('RGB', (1600, 800), 'red').save(output, format='PNG')
    original = output.getvalue()
    asset = Asset(original_filename='large.png', mime_type='image/png', size_bytes=len(original))
    repository.save_asset(asset, original)
    monkeypatch.setattr(main, 'repository', repository)
    calls = []
    get_bytes = repository.get_asset_bytes
    monkeypatch.setattr(repository, 'get_asset_bytes', lambda key: (calls.append(key), get_bytes(key))[1])
    thumbnail.cache_clear()
    client = TestClient(main.app)
    first = client.get(f'/api/v1/assets/{asset.id}/thumbnail')
    second = client.get(f'/api/v1/assets/{asset.id}/thumbnail')
    assert first.status_code == second.status_code == 200
    assert first.headers['content-type'] == 'image/webp'
    assert 'max-age' in first.headers['cache-control']
    assert len(calls) == 1
    with Image.open(BytesIO(first.content)) as image:
        assert image.size == (480, 240)
    assert get_bytes(asset.id) == original
    assert client.get(f'/api/v1/assets/{asset.id}').json()['original_filename'] == 'large.png'


@pytest.mark.parametrize('cursor', ['!!!!', 'bnVsbA==', 'W10=', 'WyIyMDI2LTA5LTE0VDAwOjAwOjAwKzAwOjAwIiwxLCJ4Il0='])
def test_invalid_cursor_is_rejected(cursor):
    with pytest.raises(ValueError, match='INVALID_KNOWLEDGE_CURSOR'):
        list_knowledge(InMemoryRepository(), cursor)
