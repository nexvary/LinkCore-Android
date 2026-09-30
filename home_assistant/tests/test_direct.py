"""Adapter and real Home Assistant entity/coordinator tests (no hardware claims)."""
import asyncio
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / 'custom_components'))
from fg_machines_rck.direct_api import DirectVpsApi, DirectAuthError, normalize_origin, normalize_devices
from fg_machines_rck.api import RckApiError
from fg_machines_rck.coordinator import RckCoordinator
from fg_machines_rck.switch import RckOutletSwitch, async_setup_entry
from fg_machines_rck.sensor import RckOutletSensor, OUTLET_SENSORS
from fg_machines_rck.config_flow import ConfigFlow
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ConfigEntryAuthFailed
from homeassistant.const import CONF_HOST

MAC='2CE032C7A520'
TOKEN='fgd_'+'x'*43
PAYLOAD={'source':'direct-vps','devices':[{'mac':MAC,'connected':True,'control_enabled':True,
 'visible_outlets':[1,2], 'allowed_outlets':[1], 'outlets':[
 {'channel':1,'relay':'on','power_w':12,'energy_wh':1500,'temperature_c':25},
 {'channel':2,'relay':'off'}, {'channel':3,'relay':'on','power_w':999}]}]}

class Content:
    def __init__(self, payload):
        import json
        self.body=json.dumps(payload).encode()
    async def iter_chunked(self, count):
        yield self.body
class Response:
    def __init__(self, status, data):
        self.status=status; self.content=Content(data); self.content_length=len(self.content.body)
    async def __aenter__(self): return self
    async def __aexit__(self,*args): pass
class Session:
    def __init__(self, queue=None): self.queue=list(queue or []); self.calls=[]
    def request(self, method, url, **kwargs):
        self.calls.append((method,url,kwargs))
        if self.queue: status,data=self.queue.pop(0)
        elif url.endswith('/auth/login'): status,data=200,{'source':'direct-vps','access_token':TOKEN}
        elif url.endswith('/auth/logout'): status,data=200,{'ok':True}
        elif method=='GET': status,data=200,deepcopy(PAYLOAD)
        else: status,data=200,{'source':'direct-vps','status':'confirmed'}
        return Response(status,data)

@pytest.mark.parametrize('origin',['http://host','https://user:secret@host','https://host/path','https://host?x=1','https://host#frag','https://host:0','https://host:99999'])
def test_https_origin_rejects_unsafe(origin):
    with pytest.raises(ValueError): normalize_origin(origin)

def test_normalization_filters_hidden_and_keeps_unknown():
    p=deepcopy(PAYLOAD); p['devices'][0]['outlets'][1]['relay']='?'
    d=normalize_devices(p)[0]
    assert d['allowed_outlets']==[1]
    assert len(d['telemetry']['outlets'])==2
    assert d['telemetry']['outlets'][0]['energy_kwh']==1.5
    assert d['telemetry']['outlets'][1]['on'] is None
    with pytest.raises(RckApiError): normalize_devices({'source':'android','devices':[]})

@pytest.mark.asyncio
async def test_login_control_confirm_and_logout():
    s=Session(); api=DirectVpsApi(s,'https://example.test','Client','secret')
    assert len(await api.devices())==1
    await api.set_outlet(MAC,1,False)
    await api.logout()
    assert api._token is None
    posts=[c for c in s.calls if c[0]=='POST']
    assert len(posts)==3
    assert posts[1][1].endswith('/outlets/1?state=off')
    assert posts[1][2]['headers']['Authorization']=='Bearer '+TOKEN
    assert all(c[2]['allow_redirects'] is False for c in s.calls)

@pytest.mark.asyncio
async def test_denied_outlet_never_posts_control():
    s=Session(); api=DirectVpsApi(s,'https://example.test','client','secret')
    with pytest.raises(RckApiError): await api.set_outlet(MAC,2,True)
    assert len([c for c in s.calls if '/outlets/' in c[1]])==0

@pytest.mark.asyncio
@pytest.mark.parametrize('status',['sent','queued','failed','timeout'])
async def test_no_success_without_confirmation(status):
    s=Session([(200,{'source':'direct-vps','access_token':TOKEN}), (200,PAYLOAD),
               (200,{'source':'direct-vps','status':status})])
    api=DirectVpsApi(s,'https://example.test','client','secret')
    with pytest.raises(RckApiError): await api.set_outlet(MAC,1,False)
    assert len([c for c in s.calls if '/outlets/' in c[1]])==1

@pytest.mark.asyncio
async def test_expired_token_reauths_get_once():
    s=Session([(200,{'source':'direct-vps','access_token':TOKEN}),(401,{}),
               (200,{'source':'direct-vps','access_token':TOKEN}),(200,PAYLOAD)])
    api=DirectVpsApi(s,'https://example.test','client','secret')
    await api.devices()
    assert len(s.calls)==4

@pytest.mark.asyncio
async def test_post_401_not_retried():
    s=Session([(200,{'source':'direct-vps','access_token':TOKEN}),(200,PAYLOAD),(401,{})])
    api=DirectVpsApi(s,'https://example.test','client','secret')
    with pytest.raises(DirectAuthError): await api.set_outlet(MAC,1,False)
    assert len(s.calls)==3

@pytest.mark.asyncio
async def test_offline_and_disabled_prevent_command():
    for field in ['connected','control_enabled']:
        p=deepcopy(PAYLOAD);p['devices'][0][field]=False
        s=Session([(200,{'source':'direct-vps','access_token':TOKEN}),(200,p)])
        with pytest.raises(RckApiError): await DirectVpsApi(s,'https://example.test','client','secret').set_outlet(MAC,1,True)
        assert not any('/outlets/' in c[1] for c in s.calls)

@pytest.mark.asyncio
async def test_real_homeassistant_entities_follow_fresh_session_permissions(tmp_path):
    hass=HomeAssistant(str(tmp_path))
    api=DirectVpsApi(Session(),'https://example.test','client','secret')
    c=RckCoordinator(hass,api);c.data=normalize_devices(PAYLOAD);c.last_update_success=True;c.identity_prefix='account_a_'
    switch=RckOutletSwitch(c,MAC,1);viewer=RckOutletSwitch(c,MAC,2)
    sensor=RckOutletSensor(c,MAC,1,OUTLET_SENSORS[1])
    assert switch.available and switch.is_on is True
    assert not viewer.available and viewer.is_on is False
    assert sensor.native_value==1.5 and sensor.available
    assert switch.unique_id.startswith('account_a_')
    c.last_update_success=False
    assert not switch.available and not sensor.available
    c.last_update_success=True;c.data[0]['visible_outlets']=[]
    assert not switch.available and not sensor.available
    await hass.async_stop()

@pytest.mark.asyncio
async def test_switch_failure_surfaces_and_refreshes(tmp_path):
    hass=HomeAssistant(str(tmp_path))
    api=DirectVpsApi(Session(),'https://example.test','client','secret')
    c=RckCoordinator(hass,api);c.data=normalize_devices(PAYLOAD);c.last_update_success=True
    calls=[]
    async def fail(*args): raise RckApiError('Device confirmation not received')
    async def refresh(): calls.append('refresh')
    api.set_outlet=fail;c.async_request_refresh=refresh
    with pytest.raises(HomeAssistantError): await RckOutletSwitch(c,MAC,1).async_turn_off()
    assert calls==['refresh']
    await hass.async_stop()

@pytest.mark.asyncio
async def test_real_coordinator_invalid_credentials_request_reauth(tmp_path):
    hass=HomeAssistant(str(tmp_path))
    api=DirectVpsApi(Session([(401,{})]),'https://example.test','client','secret')
    with pytest.raises(ConfigEntryAuthFailed): await RckCoordinator(hass,api)._async_update_data()
    await hass.async_stop()

@pytest.mark.asyncio
async def test_config_flow_retains_local_and_direct_choices():
    flow=ConfigFlow()
    result=await flow.async_step_user()
    assert result['menu_options']==['direct','local']

@pytest.mark.asyncio
async def test_config_flow_validates_customer_and_closes_validation_session(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock
    import fg_machines_rck.config_flow as module
    hass=HomeAssistant(str(tmp_path));session=Session()
    monkeypatch.setattr(module,'async_get_clientsession',lambda _:session)
    flow=ConfigFlow();flow.hass=hass;flow.context={'source':'user'}
    flow.async_set_unique_id=AsyncMock();flow._abort_if_unique_id_configured=lambda:None
    result=await flow.async_step_direct({'host':'https://example.test','username':'Client','password':'secret'})
    assert result['data']=={'host':'https://example.test','mode':'direct','username':'client','password':'secret'}
    assert session.calls[-1][1].endswith('/auth/logout')
    await hass.async_stop()

@pytest.mark.asyncio
async def test_config_flow_reauth_updates_existing_account(tmp_path,monkeypatch):
    from unittest.mock import AsyncMock, Mock
    import fg_machines_rck.config_flow as module
    hass=HomeAssistant(str(tmp_path));monkeypatch.setattr(module,'async_get_clientsession',lambda _:Session())
    flow=ConfigFlow();flow.hass=hass;flow.context={'source':'reauth'}
    flow.async_set_unique_id=AsyncMock()
    entry=SimpleNamespace(data={'host':'https://example.test','username':'client'})
    flow._get_reauth_entry=lambda:entry
    flow._abort_if_unique_id_configured=Mock(side_effect=AssertionError('must not abort reauth as duplicate'))
    flow.async_update_reload_and_abort=Mock(return_value={'type':'abort','reason':'reauth_successful'})
    result=await flow.async_step_direct({'host':'https://example.test','username':'client','password':'new-password'})
    assert result['reason']=='reauth_successful'
    assert flow.async_update_reload_and_abort.call_args.kwargs['data_updates']['password']=='new-password'
    await hass.async_stop()

@pytest.mark.asyncio
async def test_config_flow_invalid_password_and_https_form(tmp_path,monkeypatch):
    import fg_machines_rck.config_flow as module
    hass=HomeAssistant(str(tmp_path));monkeypatch.setattr(module,'async_get_clientsession',lambda _:Session([(401,{})]))
    flow=ConfigFlow();flow.hass=hass;flow.context={'source':'user'}
    result=await flow.async_step_direct({'host':'https://example.test','username':'client','password':'wrong'})
    assert result['errors']['base']=='invalid_auth'
    result=await flow.async_step_direct({'host':'http://example.test','username':'client','password':'wrong'})
    assert result['errors']['base']=='invalid_host'
    await hass.async_stop()

@pytest.mark.asyncio
async def test_new_and_revoked_device_entities_follow_polling(tmp_path):
    hass=HomeAssistant(str(tmp_path));api=DirectVpsApi(Session(),'https://example.test','client','secret')
    c=RckCoordinator(hass,api);c.data=[];c.last_update_success=True
    hass.data['fg_machines_rck']={'fixture':c};entities=[];unloads=[]
    entry=SimpleNamespace(entry_id='fixture',async_on_unload=unloads.append)
    await async_setup_entry(hass,entry,entities.extend)
    assert not entities
    c.async_set_updated_data(normalize_devices(PAYLOAD))
    assert len(entities)==2 and entities[0].unique_id.startswith('fixture_')
    c.async_set_updated_data(normalize_devices(PAYLOAD));assert len(entities)==2
    c.async_set_updated_data([]);assert all(not e.available for e in entities)
    for unload in unloads: unload()
    await hass.async_stop()

@pytest.mark.asyncio
async def test_unknown_state_is_not_controllable():
    p=deepcopy(PAYLOAD);p['devices'][0]['outlets'][0]['relay']='unknown'
    s=Session([(200,{'source':'direct-vps','access_token':TOKEN}),(200,p)])
    with pytest.raises(RckApiError): await DirectVpsApi(s,'https://example.test','client','secret').set_outlet(MAC,1,True)
    assert not any('/outlets/' in c[1] for c in s.calls)
