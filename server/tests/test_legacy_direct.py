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
