"""Discovery uses the same authenticated case scope as detailed evidence."""
import pytest
from fastapi import HTTPException
from app.models import Case
from app.models.evaluation import Evaluation
from app.services import evaluations as service
from test_evaluations import setup, imported
from test_evaluation_hardening import limited_history


def test_index_authentication_and_empty_state(client, account):
    assert client.get('/api/v1/evaluations').status_code == 401
    for role in ['Admin', 'DataScientist', 'Researcher', 'Clinician']:
        _, headers = account(role)
        response = client.get('/api/v1/evaluations', headers=headers)
        assert response.status_code == 200
        assert response.json() == dict(items=[], limit=20, offset=0, next_offset=None, offset_limit_reached=False)
        assert response.headers['cache-control'] == 'no-store'


@pytest.mark.parametrize('layout', [[False], [True, False], [False, True, False, True, False]])
def test_index_access_filter_before_limit_and_offset(client, setup, limited_history, layout):
    ids = limited_history(layout)
    visible = [identifier for identifier, allowed in zip(ids, layout) if allowed]
    hidden = [identifier for identifier, allowed in zip(ids, layout) if not allowed]
    for offset in range(len(visible) + 1):
        response = client.get(f'/api/v1/evaluations?limit=1&offset={offset}', headers=setup['headers'])
        assert response.status_code == 200
        body = response.json()
        assert [r['id'] for r in body['items']] == visible[offset:offset+1]
        assert body['next_offset'] == (offset+1 if offset+1 < len(visible) else None)
        assert not any(identifier in response.text for identifier in hidden)
        assert 'total' not in body


def test_index_access_rechecked_after_sql_selection(client, setup, monkeypatch):
    imported(client, setup)
    original = service.case_access.get_case
    def deny(db, case_id):
        if case_id == setup['cases'][1].id:
            raise HTTPException(404, 'Case not found')
        return original(db, case_id)
    monkeypatch.setattr(service.case_access, 'get_case', deny)
    response = client.get('/api/v1/evaluations?limit=1', headers=setup['headers'])
    assert response.status_code == 404
    assert 'items' not in response.json()


def test_index_excludes_partial_case_access(client, setup, monkeypatch):
    _, value = imported(client, setup)
    original = service.case_access.readable_cases
    monkeypatch.setattr(service.case_access, 'readable_cases', lambda: original().where(Case.id != setup['cases'][1].id))
    response = client.get('/api/v1/evaluations?limit=1', headers=setup['headers'])
    assert response.status_code == 200 and response.json()['items'] == []
    assert value['id'] not in response.text and value['source_artifact_id'] not in response.text


@pytest.mark.parametrize('query', ['limit=0', 'limit=101', 'offset=-1', 'offset=1000001'])
def test_index_query_bounds(client, setup, query):
    assert client.get('/api/v1/evaluations?' + query, headers=setup['headers']).status_code == 422


def test_index_continuation_never_exceeds_accepted_bound(client, setup, limited_history, monkeypatch):
    limited_history([True, True])
    monkeypatch.setattr(service, 'MAX_HISTORY_OFFSET', 0)
    # Exercise the boundary policy with real rows, avoiding a million fixtures.
    response = client.get('/api/v1/evaluations?limit=1', headers=setup['headers'])
    assert response.status_code == 200
    body = response.json()
    assert body['next_offset'] is None and body['offset_limit_reached'] is True


def test_index_tampered_header_does_not_publish_partial_results(client, setup, db):
    _, value = imported(client, setup)
    row = db.get(Evaluation, value['id'])
    row.threshold = 0.1
    db.commit()
    response = client.get('/api/v1/evaluations', headers=setup['headers'])
    assert response.status_code == 409
    assert 'items' not in response.json()
