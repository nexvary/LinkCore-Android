import base64
import json
from datetime import timedelta

import pytest
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient
from sqlalchemy import String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app import legacy_direct
from app.legacy_direct_users import DirectUser, DirectSession

MAC = '2CE032C7A520'


class LegacyBase(DeclarativeBase):
    pass


class ExistingActivity(LegacyBase):
    __tablename__ = 'activity_log'
    id: Mapped[int] = mapped_column(primary_key=True)
    event_type: Mapped[str] = mapped_column(String)
    detail_json: Mapped[str] = mapped_column(String)


@pytest.fixture
def deployed(tmp_path, monkeypatch):
    engine = create_engine('sqlite:///' + str(tmp_path / 'existing.db'), connect_args={'check_same_thread': False})
    factory = sessionmaker(engine, expire_on_commit=False)
    LegacyBase.metadata.create_all(engine)
    app = FastAPI(title='FG Link Server', version='0.5.0')
    def guard(x_fg_panel_token: str | None = Header(default=None)):
        if x_fg_panel_token != 'fixture-owner-token':
            raise HTTPException(403, 'Panel access denied')
    @app.get('/panel')
    def panel(_=Depends(guard)):
        return HTMLResponse('<html lang="ar" dir="rtl"><body><h1>Original accounts panel</h1></body></html>')
    @app.get('/healthz')
    def health():
        return {'status': 'ok', 'service': 'FG Link Server'}
    @app.post('/api/v1/client/commands/poll')
    def legacy_poll():
        return {'commands': [], 'legacy': True}
    def log(db, event_type, *, account_id=None, detail=None):
        db.add(ExistingActivity(event_type=event_type, detail_json=json.dumps(detail)))
    monkeypatch.setenv('FGRCK_DIRECT_MTTL_MACS', MAC)
    monkeypatch.setattr(legacy_direct.adapter, 'status', lambda mac: {
        'connected': True, 'control_enabled': True, 'outlets': [], 'last_seen': 1})
    monkeypatch.setattr(legacy_direct.adapter, 'status_many',
                        lambda macs: {mac: legacy_direct.adapter.status(mac) for mac in macs})
    calls = []
    def control(mac, outlet, state):
        calls.append((mac, outlet, state))
        return {'status': 'confirmed', 'ok': True}
    monkeypatch.setattr(legacy_direct.adapter, 'control', control)
    legacy_direct.install(app, engine, factory, guard, log)
    legacy_direct.install(app, engine, factory, guard, log)
    headers = {'X-FG-Panel-Token': 'fixture-owner-token',
               'Authorization': 'Basic ' + base64.b64encode(b'owner:fixture-password').decode()}
    with TestClient(app) as client:
        yield client, factory, headers, calls
    engine.dispose()


def test_panel_injection_and_existing_routes(deployed):
    client, factory, headers, calls = deployed
    assert client.get('/panel').status_code == 403
    response = client.get('/panel', headers=headers)
    assert response.status_code == 200
    assert 'Original accounts panel' in response.text
    assert response.text.count('id="fg-direct-vps"') == 1
    assert 'fg-panel-header' in response.text
    assert 'fg-panel-audit' in response.text
    assert 'fgdu-permission-title' in response.text
    assert response.headers['content-length'] == str(len(response.content))
    assert client.get('/healthz').json()['service'] == 'FG Link Server'
    assert client.post('/api/v1/client/commands/poll').json()['legacy']
    devices = client.get('/panel/api/direct/devices', headers=headers).json()['devices']
    assert devices[0]['mac'] == MAC
    assert devices[0]['transport'] == 'direct-vps'


def test_owner_guard_mac_registration_policy_and_confirmation(deployed):
    client, factory, headers, calls = deployed
    path = f'/panel/api/direct/devices/{MAC}/outlets/1?state=on'
    assert client.post(path, headers={'Authorization': 'Bearer viewer-client-token'}).status_code == 403
    assert client.post(path, headers={'X-FG-Panel-Token': 'wrong'}).status_code == 403
    assert client.post('/panel/api/direct/devices/AABBCCDDEEFF/outlets/1?state=on', headers=headers).status_code == 404
    assert client.post(f'/panel/api/direct/devices/{MAC}/outlets/5?state=on', headers=headers).status_code == 422
    with factory() as db:
        policy = db.get(legacy_direct.DirectRegistration, MAC)
        policy.outlet_mask = 2
        db.commit()
    assert client.post(path, headers=headers).status_code == 403
    assert not calls
    result = client.post(f'/panel/api/direct/devices/{MAC}/outlets/2?state=off', headers=headers)
    assert result.status_code == 200, result.text
    assert result.json()['status'] == 'confirmed'
    assert calls == [(MAC, 2, 'off')]
    with factory() as db:
        logs = list(db.scalars(select(ExistingActivity)))
        assert [log.event_type for log in logs] == ['direct_command_queued', 'direct_command_confirmed']
        detail = json.loads(logs[-1].detail_json)
        assert detail['user'] == 'owner'
        assert detail['mac'] == MAC and detail['source'] == 'direct-vps'
        assert detail['outlet'] == 2 and detail['requested_state'] == 'off'
        assert 'fixture-password' not in logs[-1].detail_json


def test_offline_disabled_timeout_and_interrupted_status(deployed, monkeypatch):
    client, factory, headers, calls = deployed
    path = f'/panel/api/direct/devices/{MAC}/outlets/1?state=on'
    monkeypatch.setattr(legacy_direct.adapter, 'status', lambda mac: {'connected': False, 'control_enabled': True})
    assert client.post(path, headers=headers).status_code == 409
    monkeypatch.setattr(legacy_direct.adapter, 'status', lambda mac: {'connected': True, 'control_enabled': False})
    assert client.post(path, headers=headers).status_code == 409
    monkeypatch.setattr(legacy_direct.adapter, 'status', lambda mac: {'connected': True, 'control_enabled': True})
    monkeypatch.setattr(legacy_direct.adapter, 'control', lambda *args: {'status': 'timeout', 'ok': False, 'error': 'no fresh device confirmation'})
    result = client.post(path, headers=headers).json()
    assert not result['ok'] and result['status'] == 'timeout'
    command_id = result['command_id']
    assert client.get('/panel/api/direct/commands/' + command_id).status_code == 403
    with factory() as db:
        command = db.get(legacy_direct.DirectCommand, command_id)
        command.status = 'sent'
        command.created_at = legacy_direct.now() - timedelta(seconds=30)
        db.commit()
    status = client.get('/panel/api/direct/commands/' + command_id, headers=headers).json()
    assert status['status'] == 'timeout'
    assert 'interrupted' in status['detail']


def new_user(client, owner, name, *, mac=MAC, view=15, control=0):
    created = client.post('/panel/api/direct/users', headers=owner,
                          json={'username': name, 'display_name': 'اختبار ' + name}).json()
    assert 'password' in created, created
    if mac:
        result = client.put(f'/panel/api/direct/users/{created["id"]}/devices/{mac}', headers=owner,
                            json={'view_mask': view, 'control_mask': control})
        assert result.status_code == 200, result.text
    response = client.post('/api/v1/direct/auth/login', json={
        'username': created['username'], 'password': created['password']})
    assert response.status_code == 200, response.text
    created['token'] = response.json()['access_token']
    created['headers'] = {'Authorization': 'Bearer ' + created['token']}
    return created


def test_customer_isolation_visible_outlets_and_private_metadata(deployed, monkeypatch):
    client, factory, owner, calls = deployed
    other = 'AABBCCDDEEFF'
    monkeypatch.setattr(legacy_direct.adapter, 'allow', lambda mac: {'ok': True})
    assert client.post('/panel/api/direct/registrations', headers=owner, json={'mac': other}).status_code == 200
    monkeypatch.setattr(legacy_direct.adapter, 'status', lambda mac: {
        'connected': True, 'control_enabled': True, 'peer': 'private-peer',
        'outlets': [{'channel': n, 'relay': 'off'} for n in range(1, 5)], 'pending_outlets': [2]})
    alice = new_user(client, owner, 'alice', view=5, control=1)
    bob = new_user(client, owner, 'bob', mac=other)
    result = client.get('/api/v1/direct/devices', headers=alice['headers'])
    assert result.status_code == 200
    assert result.headers['cache-control'] == 'no-store'
    devices = result.json()['devices']
    assert [d['mac'] for d in devices] == [MAC]
    assert devices[0]['visible_outlets'] == [1, 3]
    assert devices[0]['allowed_outlets'] == [1]
    assert [o['channel'] for o in devices[0]['outlets']] == [1, 3]
    assert 'peer' not in devices[0] and devices[0]['pending_outlets'] == []
    assert devices[0]['device_busy']
    assert client.post(f'/api/v1/direct/devices/{other}/outlets/1?state=on', headers=alice['headers']).status_code == 404
    assert client.post(f'/api/v1/direct/devices/{MAC}/outlets/1?state=on', headers=bob['headers']).status_code == 404
    assert not calls
    assert client.get('/panel/api/direct/users', headers=alice['headers']).status_code == 403
    assert client.post('/panel/api/direct/registrations', headers=bob['headers'], json={'mac': '112233445566'}).status_code == 403
    assert client.get('/api/v1/direct/devices', headers=owner).status_code == 401


def test_customer_control_confirmation_audit_and_command_ownership(deployed):
    client, factory, owner, calls = deployed
    alice = new_user(client, owner, 'alice', control=1)
    bob = new_user(client, owner, 'bob', control=1)
    result = client.post(f'/api/v1/direct/devices/{MAC}/outlets/1?state=on', headers=alice['headers'])
    assert result.status_code == 200, result.text
    assert result.json()['status'] == 'confirmed'
    command_id = result.json()['command_id']
    path = '/api/v1/direct/commands/' + command_id
    assert client.get(path, headers=alice['headers']).json()['status'] == 'confirmed'
    assert client.get(path, headers=bob['headers']).status_code == 404
    assert client.post(f'/api/v1/direct/devices/{MAC}/outlets/1?state=off', headers=alice['headers']).status_code == 429
    with factory() as db:
        logs = list(db.scalars(select(ExistingActivity)))
        detail = json.loads(next(log.detail_json for log in reversed(logs) if log.event_type == 'direct_command_confirmed'))
        assert detail['user'] == 'direct-user:' + alice['id']
        assert detail['mac'] == MAC and detail['source'] == 'direct-vps'
        assert all(alice['password'] not in log.detail_json and alice['token'] not in log.detail_json for log in logs)


def test_view_role_outlet_policy_and_grant_revocation(deployed):
    client, factory, owner, calls = deployed
    viewer = new_user(client, owner, 'viewer', control=0)
    partial = new_user(client, owner, 'partial', view=3, control=2)
    path = f'/api/v1/direct/devices/{MAC}/outlets/1?state=on'
    assert client.post(path, headers=viewer['headers']).status_code == 403
    assert client.post(path, headers=partial['headers']).status_code == 403
    assert not calls
    assert client.put(f'/panel/api/direct/users/{viewer["id"]}/devices/{MAC}', headers=owner,
                      json={'view_mask': 1, 'control_mask': 2}).status_code == 422
    assert client.delete(f'/panel/api/direct/users/{viewer["id"]}/devices/{MAC}', headers=owner).status_code == 200
    assert client.get('/api/v1/direct/devices', headers=viewer['headers']).json()['devices'] == []
    blocked = new_user(client, owner, 'blocked', control=15)
    assert client.put(f'/panel/api/direct/registrations/{MAC}/policy', headers=owner,
                      json={'control_mask': 0}).status_code == 200
    assert client.post(path, headers=blocked['headers']).status_code == 403
    assert client.get('/api/v1/direct/devices', headers=blocked['headers']).json()['devices'][0]['allowed_outlets'] == []


def test_disable_reset_logout_and_expiry_invalidate_sessions(deployed):
    client, factory, owner, calls = deployed
    alice = new_user(client, owner, 'alice')
    assert client.patch('/panel/api/direct/users/' + alice['id'], headers=owner, json={'active': False}).status_code == 200
    assert client.get('/api/v1/direct/devices', headers=alice['headers']).status_code == 401
    assert client.patch('/panel/api/direct/users/' + alice['id'], headers=owner, json={'active': True}).status_code == 200
    assert client.get('/api/v1/direct/devices', headers=alice['headers']).status_code == 401
    reset = client.post('/panel/api/direct/users/' + alice['id'] + '/reset-password', headers=owner).json()
    assert client.post('/api/v1/direct/auth/login', json={'username': 'alice', 'password': alice['password']}).status_code == 401
    login = client.post('/api/v1/direct/auth/login', json={'username': 'alice', 'password': reset['password']}).json()
    token = {'Authorization': 'Bearer ' + login['access_token']}
    assert client.post('/api/v1/direct/auth/logout', headers=token).status_code == 200
    assert client.get('/api/v1/direct/devices', headers=token).status_code == 401
    bob = new_user(client, owner, 'bob')
    with factory() as db:
        user = db.get(DirectUser, bob['id'])
        assert user.password_hash.startswith('pbkdf2-sha256$600000$')
        assert bob['password'] not in user.password_hash
        session = db.scalar(select(DirectSession).where(DirectSession.user_id == bob['id']))
        assert bob['token'] not in session.token_hash
        session.expires_at = legacy_direct.now() - timedelta(seconds=1)
        db.commit()
    assert client.get('/api/v1/direct/devices', headers=bob['headers']).status_code == 401


def test_registration_guard_persistence_errors_and_csrf(deployed, monkeypatch):
    client, factory, owner, calls = deployed
    attempted = []
    def unavailable(mac):
        attempted.append(mac)
        raise OSError('daemon unavailable')
    monkeypatch.setattr(legacy_direct.adapter, 'allow', unavailable)
    assert client.post('/panel/api/direct/registrations', headers=owner, json={'mac': 'bad'}).status_code == 422
    assert not attempted
    other = 'AABBCCDDEEFF'
    assert client.post('/panel/api/direct/registrations', headers=owner, json={'mac': other}).status_code == 503
    with factory() as db:
        assert db.get(legacy_direct.DirectRegistration, other) is None
    assert client.post('/panel/api/direct/users', headers={**owner, 'Origin': 'https://evil.example'},
                       json={'username': 'attacker'}).status_code == 403
    created = client.post('/panel/api/direct/users', headers=owner, json={'username': 'alice'})
    assert created.status_code == 200
    assert created.headers['cache-control'] == 'no-store'
    assert client.post('/panel/api/direct/users', headers=owner, json={'username': 'alice'}).status_code == 409
    assert client.get('/panel/api/direct/users', headers=owner).json()['users'][0]['username'] == 'alice'
    assert 'password_hash' not in client.get('/panel/api/direct/users', headers=owner).text


def test_login_attempts_are_limited_and_unknown_user_is_generic(deployed):
    client, factory, owner, calls = deployed
    for _ in range(10):
        response = client.post('/api/v1/direct/auth/login', json={'username': 'unknown', 'password': 'wrong'})
        assert response.status_code == 401 and response.json()['detail'] == 'Invalid username or password'
    assert client.post('/api/v1/direct/auth/login', json={'username': 'unknown', 'password': 'wrong'}).status_code == 429


def test_customer_batch_assignment_is_validated_and_scoped(deployed, monkeypatch):
    client, factory, owner, calls = deployed
    user = client.post('/panel/api/direct/users', headers=owner, json={'username': 'fleetowner'}).json()
    path = '/panel/api/direct/users/' + user['id'] + '/devices'
    allowed = []
    monkeypatch.setattr(legacy_direct.adapter, 'allow_many', lambda macs: allowed.append(macs))
    body = {'macs': [MAC, 'aabbccddeeff', MAC], 'view_mask': 15, 'control_mask': 3}
    assert client.put(path, json=body).status_code == 403
    assert client.put(path, headers=owner, json={**body, 'macs': [MAC, 'bad']}).status_code == 422
    assert client.put(path, headers=owner, json={**body, 'view_mask': 1}).status_code == 422
    assert not allowed
    response = client.put(path, headers=owner, json=body)
    assert response.status_code == 200 and response.json()['count'] == 2
    assert allowed == [[MAC, 'AABBCCDDEEFF']]
    assert client.put(path, headers=owner, json=body).status_code == 200
    grants = client.get('/panel/api/direct/users', headers=owner).json()['users'][0]['grants']
    assert len(grants) == 2 and all(g['control_mask'] == 3 for g in grants)
    login = client.post('/api/v1/direct/auth/login', json={'username': 'fleetowner', 'password': user['password']}).json()
    token = {'Authorization': 'Bearer ' + login['access_token']}
    visible = client.get('/api/v1/direct/devices', headers=token).json()['devices']
    assert {d['mac'] for d in visible} == {MAC, 'AABBCCDDEEFF'}
    def unavailable(macs):
        raise OSError('daemon unavailable')
    monkeypatch.setattr(legacy_direct.adapter, 'allow_many', unavailable)
    assert client.put(path, headers=owner, json={**body, 'macs': ['112233445566']}).status_code == 503
    with factory() as db:
        assert db.get(legacy_direct.DirectRegistration, '112233445566') is None
    assert len(client.get('/panel/api/direct/users', headers=owner).json()['users'][0]['grants']) == 2


def test_owner_chosen_customer_password_authenticates_without_plaintext_storage(deployed):
    client, factory, owner, calls = deployed
    password = 'ChosenFixturePassword123'
    response = client.post('/panel/api/direct/users', headers=owner,
                           json={'username': 'chosenpassword', 'password': password})
    assert response.status_code == 200 and response.json()['password'] == password
    user_id = response.json()['id']
    login = client.post('/api/v1/direct/auth/login',
                        json={'username': 'chosenpassword', 'password': password})
    assert login.status_code == 200 and login.json()['access_token']
    with factory() as db:
        assert password not in db.get(DirectUser, user_id).password_hash
    assert password not in client.get('/panel/api/direct/users', headers=owner).text
