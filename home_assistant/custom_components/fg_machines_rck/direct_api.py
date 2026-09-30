"""HTTPS subscriber adapter. No raw socket access or owner-panel secrets."""
from __future__ import annotations
import asyncio
import re
from urllib.parse import urlsplit
from aiohttp import ClientError, ClientSession, ClientTimeout
from .api import RckApiError


class DirectAuthError(RckApiError):
    """Invalid/disabled subscriber credentials."""


def normalize_origin(value: str) -> str:
    try:
        url = urlsplit(value.strip())
        port = url.port
        if (url.scheme != 'https' or not url.hostname or url.username is not None
                or url.password is not None or url.query or url.fragment
                or url.path not in ('', '/', '/panel', '/panel/') or port == 0):
            raise ValueError('HTTPS origin required')
        return f'https://{url.netloc}'
    except (ValueError, AttributeError) as err:
        raise ValueError('HTTPS origin required') from err


def normalize_devices(payload: dict) -> list[dict]:
    if payload.get('source') != 'direct-vps' or not isinstance(payload.get('devices'), list):
        raise RckApiError('Invalid Direct VPS response')
    result = []
    for raw in payload['devices']:
        if not isinstance(raw, dict) or not re.fullmatch('[0-9A-Fa-f]{12}', str(raw.get('mac', ''))):
            raise RckApiError('Invalid device identifier')
        visible = [n for n in raw.get('visible_outlets', []) if type(n) is int and 1 <= n <= 4]
        allowed = [n for n in raw.get('allowed_outlets', []) if n in visible]
        rows = []
        for outlet in raw.get('outlets', []):
            if outlet.get('channel') not in visible:
                continue
            row = dict(outlet)
            relay = row.get('relay')
            row['on'] = True if relay == 'on' else False if relay == 'off' else None
            energy = row.get('energy_wh')
            row['energy_kwh'] = energy / 1000 if isinstance(energy, (int, float)) else None
            rows.append(row)
        result.append({**raw, 'mac': raw['mac'].upper(), 'visible_outlets': visible,
                       'allowed_outlets': allowed, 'telemetry': {'outlets': rows}})
    return result


class DirectVpsApi:
    direct = True
    def __init__(self, session: ClientSession, origin: str, username: str, password: str):
        self._session = session
        self._base_url = normalize_origin(origin)
        self._username = username.strip().lower()
        self._password = password
        self._token = None
        self._lock = asyncio.Lock()
        self._auth_lock = asyncio.Lock()

    async def _request(self, method: str, path: str, *, body=None, authenticated=True):
        headers = {'Accept': 'application/json', 'Cache-Control': 'no-store'}
        if authenticated and self._token:
            headers['Authorization'] = 'Bearer ' + self._token
        try:
            async with self._session.request(method, self._base_url + '/api/v1/direct' + path,
                    headers=headers, json=body, allow_redirects=False,
                    timeout=ClientTimeout(total=25 if method == 'POST' else 10)) as response:
                if response.status == 401:
                    raise DirectAuthError('Direct VPS authentication rejected')
                if response.status != 200:
                    raise RckApiError(f'Direct VPS HTTP {response.status}')
                if response.content_length and response.content_length > 262144:
                    raise RckApiError('Response too large')
                # Stream a bounded body; never include remote response/credentials in logs.
                data = bytearray()
                async for chunk in response.content.iter_chunked(4096):
                    data.extend(chunk)
                    if len(data) > 262144:
                        raise RckApiError('Response too large')
                import json
                parsed = json.loads(data)
                if not isinstance(parsed, dict):
                    raise RckApiError('Invalid JSON response')
                return parsed
        except (ClientError, TimeoutError, ValueError) as err:
            raise RckApiError('Direct VPS connection or response failed') from err

    async def login(self):
        response = await self._request('POST', '/auth/login', authenticated=False,
                body={'username': self._username, 'password': self._password})
        token = response.get('access_token', '')
        if response.get('source') != 'direct-vps' or not re.fullmatch(r'fgd_[A-Za-z0-9_-]{43}', token):
            raise RckApiError('Invalid login response')
        self._token = token

    async def _ensure_login(self):
        async with self._auth_lock:
            if self._token is None:
                await self.login()

    async def devices(self):
        await self._ensure_login()
        previous = self._token
        try:
            response = await self._request('GET', '/devices')
        except DirectAuthError:
            async with self._auth_lock:
                if self._token == previous:
                    await self.login()
            response = await self._request('GET', '/devices')  # One safe GET retry only.
        return normalize_devices(response)

    async def set_outlet(self, mac: str, outlet: int, on: bool):
        if not re.fullmatch('[0-9A-Fa-f]{12}', mac) or type(outlet) is not int or not 1 <= outlet <= 4:
            raise RckApiError('Invalid outlet')
        async with self._lock:
            # Fresh permission/session check before each command; server independently enforces it.
            device = next((d for d in await self.devices() if d['mac'] == mac.upper()), None)
            if (not device or not device.get('connected') or not device.get('control_enabled')
                    or outlet not in device['allowed_outlets'] or device.get('device_busy')
                    or device.get('pending_outlets')):
                raise RckApiError('Outlet unavailable or control denied')
            row = next((o for o in device['telemetry']['outlets'] if o['channel'] == outlet), None)
            if row is None or row.get('on') is None:
                raise RckApiError('Outlet state is unknown')
            response = await self._request('POST', f'/devices/{mac.upper()}/outlets/{outlet}?state={"on" if on else "off"}')
            # Never retry POST on timeout or lost connection.
            if response.get('source') != 'direct-vps' or response.get('status') != 'confirmed':
                raise RckApiError('Device confirmation not received')

    async def logout(self):
        if self._token:
            try:
                await self._request('POST', '/auth/logout')
            except RckApiError:
                pass
        self._token = None
