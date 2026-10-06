import pytest


@pytest.mark.integration
def test_receivables_all_time_transfer_directions_and_grouping(inprocess_app):
    database, client = inprocess_app
    database.reset()
    source = client.post('/accounts', json={'name': 'BCA', 'type': 'bank'}).json()['id']
    target = client.post('/accounts', json={'name': 'Receivables', 'type': 'cash'}).json()['id']
    for name, amount, incoming in [(' Andi ', 1000, True), ('Andi', 400, False),
                                    ('Budi', 500, True), ('Budi', 500, False),
                                    ('andi', 20, True), (None, 50, True),
                                    ('   ', 10, False), ('Credit', 30, False)]:
        response = client.post('/transfers', json={
            'type': 'transfer', 'account_id': source if incoming else target,
            'related_account_id': target if incoming else source,
            'amount': amount, 'description': name, 'occurred_at': '2020-01-01T00:00:00Z'})
        assert response.status_code == 201, response.text
    client.post('/transactions', json={'type': 'income', 'account_id': target, 'amount': 99, 'description': 'Andi'})
    response = client.get(f'/reports/receivables?account_id={target}')
    assert response.status_code == 200
    rows = response.json()['items']
    by_name = {row['description']: row for row in rows}
    assert by_name['Andi'] == {'description': 'Andi', 'lent': 1000, 'repaid': 400, 'outstanding': 600, 'transaction_count': 2}
    assert by_name['Budi']['outstanding'] == 0
    assert by_name['andi']['outstanding'] == 20
    assert by_name[None]['outstanding'] == 40
    assert by_name['Credit']['outstanding'] == -30
    assert [row['outstanding'] for row in rows] == sorted([row['outstanding'] for row in rows], reverse=True)
    assert client.get('/reports/receivables?account_id=99999').status_code == 404
    assert client.get('/reports/receivables?account_id=0').status_code == 422
    assert client.get(f'/reports/receivables?account_id={source}').json()['items'][0]['description'] == 'Credit'
    assert client.get(f'/demo/reports/receivables?account_id={target}').status_code == 200


@pytest.mark.integration
def test_receivables_workspace_isolation_and_empty_account(inprocess_app):
    database, client = inprocess_app
    database.reset()
    account = client.post('/accounts', json={'name': 'Empty', 'type': 'cash'}).json()['id']
    assert client.get(f'/reports/receivables?account_id={account}').json()['items'] == []
    database.connection.execute("INSERT INTO users (id, auth_subject) VALUES (5, 'other')")
    database.connection.execute("INSERT INTO workspaces (id, owner_user_id, name) VALUES (5, 5, 'Other')")
    database.connection.execute("INSERT INTO accounts (id, workspace_id, name, type) VALUES (999, 5, 'Private', 'cash')")
    database.connection.commit()
    assert client.get('/reports/receivables?account_id=999').status_code == 404
    assert client.get('/demo/reports/receivables?account_id=999').status_code == 404
    assert client.get(f'/reports/receivables?account_id={account}', headers={'X-Test-Workspace': '5'}).status_code == 404


@pytest.mark.integration
def test_receivables_rejects_crypto_account(inprocess_app):
    database, client = inprocess_app
    database.reset()
    account = client.post('/accounts', json={'name': 'Crypto', 'type': 'investment', 'valuation_mode': 'crypto'}).json()['id']
    assert client.get(f'/reports/receivables?account_id={account}').status_code == 400
