"""Independent deployment, administrator isolation and personal Direct API."""
import importlib
import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

@pytest.fixture
def independent(tmp_path, monkeypatch):
    monkeypatch.setenv('FGRCK_ENV', 'test')
    monkeypatch.setenv('FGRCK_DATABASE_URL', 'sqlite:///' + str(tmp_path/'panel.sqlite'))
    monkeypatch.setenv('FGRCK_ADMIN_EMAIL', 'owner@example.com')
    monkeypatch.setenv('FGRCK_DIRECT_PUBLIC_IP', '203.0.113.10')
    monkeypatch.setenv('FGRCK_JWT_SECRET', 'independent-fixture-secret-'+'x'*40)
    monkeypatch.setenv('FGRCK_DIRECT_EMAIL_WORKER_ENABLED', 'false')
    from app import main
    importlib.reload(main)
    import sys
    if 'app.standalone' in sys.modules:
        standalone = importlib.reload(sys.modules['app.standalone'])
    else:
        standalone = importlib.import_module('app.standalone')
    with TestClient(standalone.app) as client:
        with main.SessionLocal() as db:
            for address in ('owner@example.com', 'other@example.com'):
                db.add(main.User(email=address, password_hash=main.password_hasher.hash('FixturePassword123')))
            db.commit()
        def login(email):
            r=client.post('/api/v1/auth/login', json={'email':email,'password':'FixturePassword123'})
            assert r.status_code == 200
            return {'Authorization':'Bearer '+r.json()['access_token']}
        yield client, main, login('owner@example.com'), login('other@example.com')


def test_administrator_guard_and_closed_registration(independent):
    client, main, owner, other = independent
    assert client.post('/api/v1/auth/register',json={'email':'new@example.com','password':'FixturePassword123'}).status_code == 403
    for path in ('/panel/api/session','/panel/api/direct/users','/panel/api/direct/devices'):
        assert client.get(path).status_code == 401
        assert client.get(path,headers=other).status_code == 403
        assert client.get(path,headers=owner).status_code == 200
    assert client.get('/panel/api/direct/users',headers=owner).json()['users'] == []
    assert client.get('/api/v1/direct/devices',headers=owner).status_code == 401


def test_approved_layout_and_personal_account_flow(independent,monkeypatch):
    client, main, owner, other = independent
    from app import legacy_direct
    monkeypatch.setattr(legacy_direct.adapter,'status_many',lambda macs:{m:{'connected':False,'outlets':[]} for m in macs})
    monkeypatch.setattr(legacy_direct.adapter,'allow_many',lambda macs:{'ok':True})
    page=client.get('/panel').text
    for text in ('fg-direct-vps','fg-direct-users','fg-panel-header','fg-panel-audit','standalone-auth','DOMContentLoaded','fgpanel_token'):
        assert text in page
    assert '104.207.95.47' not in page and 'https://link.fgmachines.org' not in page
    assert '203.0.113.10' in page and 'location.origin' in page
    created=client.post('/panel/api/direct/users',headers=owner,json={'username':'customer','password':'PersonalPassword123'})
    assert created.status_code == 200
    uid=created.json()['id']
    assert client.put('/panel/api/direct/users/'+uid+'/devices',headers=other,json={'macs':['AABBCCDDEEFF']}).status_code == 403
    assert client.put('/panel/api/direct/users/'+uid+'/devices',headers=owner,json={'macs':['AABBCCDDEEFF'],'view_mask':1,'control_mask':0}).status_code == 200
    r=client.post('/api/v1/direct/auth/login',json={'username':'customer','password':'PersonalPassword123'})
    assert r.status_code == 200
    personal={'Authorization':'Bearer '+r.json()['access_token']}
    assert client.get('/panel/api/direct/users',headers=personal).status_code == 401
    devices=client.get('/api/v1/direct/devices',headers=personal).json()['devices']
    assert [d['mac'] for d in devices] == ['AABBCCDDEEFF']
    assert devices[0]['allowed_outlets'] == []
    assert client.get('/api/v1/direct/email-settings',headers=personal).status_code == 200
