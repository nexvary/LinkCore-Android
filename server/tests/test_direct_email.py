from datetime import timedelta
import pytest
from fastapi import HTTPException
from app import direct_email
from test_legacy_direct import deployed, new_user, MAC

OTHER = 'AABBCCDDEEFF'

@pytest.fixture
def mail(deployed, monkeypatch):
    client, factory, owner, calls = deployed
    monkeypatch.setenv('FGRCK_DIRECT_EMAIL_WORKER_ENABLED', 'false')
    monkeypatch.setattr(direct_email, 'smtp_ready', lambda: True)
    sent = []
    monkeypatch.setattr(direct_email, 'send_email', lambda *args: sent.append(args))
    return client, factory, owner, sent


def test_mail_requires_personal_login_and_configured_smtp(mail, monkeypatch):
    client, factory, owner, sent = mail
    alice = new_user(client, owner, 'emailalice')
    endpoint = '/api/v1/direct/email-settings'
    assert client.get(endpoint).status_code == 401
    assert client.get(endpoint, headers=owner).status_code == 401
    monkeypatch.setattr(direct_email, 'smtp_ready', lambda: False)
    body = {'email': 'alice@example.com', 'enabled': True}
    assert client.put(endpoint, headers=alice['headers'], json=body).status_code == 503
    body['enabled'] = False
    assert client.put(endpoint, headers=alice['headers'], json=body).status_code == 200
    assert not sent
    body['email'] = 'bad\nBcc:other@example.com'
    assert client.put(endpoint, headers=alice['headers'], json=body).status_code == 422


def test_settings_and_test_delivery_are_scoped_to_account(mail):
    client, factory, owner, sent = mail
    alice = new_user(client, owner, 'emailalice')
    bob = new_user(client, owner, 'emailbob')
    path = '/api/v1/direct/email-settings'
    assert client.put(path, headers=alice['headers'], json={'email': 'alice@example.com', 'enabled': True}).status_code == 200
    assert client.get(path, headers=bob['headers']).json()['email'] == ''
    assert client.post(path + '/test', headers=bob['headers']).status_code == 409
    response = client.post(path + '/test', headers=alice['headers'])
    assert response.status_code == 200 and response.json()['status'] == 'sent'
    assert sent[0][0] == 'alice@example.com'
    assert client.post(path + '/test', headers=alice['headers']).status_code == 429


def test_visible_outlets_only_deduplicate_and_ignore_unknown_values(mail, monkeypatch):
    client, factory, owner, sent = mail
    alice = new_user(client, owner, 'emailalice', view=1)
    path = '/api/v1/direct/email-settings'
    client.put(path, headers=alice['headers'], json={'email': 'alice@example.com', 'enabled': True})
    snapshot = {'connected': True, 'outlets': [
        {'channel': 1, 'overload': '1', 'power_w': None, 'temperature_c': None},
        {'channel': 2, 'overload': '1', 'power_w': 5000, 'temperature_c': 100}]}
    monkeypatch.setattr(direct_email.adapter, 'status_many_strict', lambda macs: {mac: snapshot for mac in macs})
    monitor = client.app.state.fg_direct_email_monitor
    monitor.scan(); monitor.scan()
    assert len(sent) == 1
    assert 'protection_1' in sent[0][2] and 'protection_2' not in sent[0][2]
    client.patch('/panel/api/direct/users/' + alice['id'], headers=owner, json={'active': False})
    snapshot['outlets'][0]['power_w'] = 5000
    monitor.scan()
    assert len(sent) == 1


def test_baseline_offline_is_not_new_disconnect_and_ipc_errors_are_not_alerts(mail, monkeypatch):
    client, factory, owner, sent = mail
    alice = new_user(client, owner, 'emailalice')
    client.put('/api/v1/direct/email-settings', headers=alice['headers'], json={'email': 'alice@example.com', 'enabled': True})
    snapshot = {'connected': False, 'outlets': []}
    monkeypatch.setattr(direct_email.adapter, 'status_many_strict', lambda macs: {mac: snapshot for mac in macs})
    monitor = client.app.state.fg_direct_email_monitor
    monitor.scan(); assert not sent
    snapshot['connected'] = True; monitor.scan()
    snapshot['connected'] = False; monitor.scan(); assert not sent
    with factory() as db:
        state = db.get(direct_email.DirectEmailState, (alice['id'], MAC, 'offline'))
        state.changed_at = direct_email.now() - timedelta(minutes=3); db.commit()
    monitor.scan(); monitor.scan()
    assert len(sent) == 1 and 'offline' in sent[0][2]
    monkeypatch.setattr(direct_email.adapter, 'status_many_strict', lambda macs: (_ for _ in ()).throw(OSError('IPC unavailable')))
    with pytest.raises(OSError): monitor.scan()
    assert len(sent) == 1


def test_smtp_failure_never_claims_test_sent(mail, monkeypatch):
    client, factory, owner, sent = mail
    alice = new_user(client, owner, 'emailalice')
    path = '/api/v1/direct/email-settings'
    client.put(path, headers=alice['headers'], json={'email': 'alice@example.com', 'enabled': False})
    monkeypatch.setattr(direct_email, 'send_email', lambda *args: (_ for _ in ()).throw(HTTPException(502, 'SMTP delivery failed')))
    assert client.post(path + '/test', headers=alice['headers']).status_code == 502
    assert not sent
