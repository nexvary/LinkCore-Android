"""Owner-provisioned Direct users; independent of legacy Android accounts."""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import threading
import time
import uuid
from collections import OrderedDict, deque
from datetime import timedelta, timezone
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

from .direct_mttl import adapter
from .legacy_direct import DirectBase, DirectCommand, DirectRegistration, now


class DirectUser(DirectBase):
    __tablename__ = 'fg_direct_users'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(256))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class DirectGrant(DirectBase):
    __tablename__ = 'fg_direct_user_grants'
    user_id: Mapped[str] = mapped_column(ForeignKey('fg_direct_users.id'), primary_key=True)
    mac: Mapped[str] = mapped_column(ForeignKey('fg_direct_registrations.mac'), primary_key=True)
    view_mask: Mapped[int] = mapped_column(Integer, default=15)
    control_mask: Mapped[int] = mapped_column(Integer, default=0)


class DirectSession(DirectBase):
    __tablename__ = 'fg_direct_user_sessions'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('fg_direct_users.id'), index=True)
    expires_at: Mapped[object] = mapped_column(DateTime(timezone=True))


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    display_name: str = Field(default='', max_length=120)
    password: str | None = Field(default=None, min_length=12, max_length=128)


class UserUpdate(BaseModel):
    active: bool


class DeviceCreate(BaseModel):
    mac: str = Field(min_length=12, max_length=12)


class GrantInput(BaseModel):
    view_mask: int = Field(default=15, ge=1, le=15)
    control_mask: int = Field(default=0, ge=0, le=15)


class PolicyInput(BaseModel):
    control_mask: int = Field(ge=0, le=15)


class Login(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=1, max_length=128)


def password_digest(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 600000).hex()
    return f'pbkdf2-sha256$600000${salt}${digest}'


def password_matches(password, stored):
    try:
        scheme, rounds, salt, digest = stored.split('$')
        if scheme != 'pbkdf2-sha256' or rounds != '600000':
            return False
        return hmac.compare_digest(password_digest(password, salt), stored)
    except (ValueError, TypeError):
        return False


def channels(mask):
    return [n for n in range(1, 5) if mask & (1 << (n - 1))]


class RateLimits:
    """Bounded process-local budgets; device command limits also live in the daemon."""
    def __init__(self):
        self.entries = OrderedDict()
        self.lock = threading.Lock()

    def check(self, key, limit, window):
        stamp = time.monotonic()
        with self.lock:
            hits = self.entries.pop(key, deque())
            while hits and hits[0] <= stamp - window:
                hits.popleft()
            self.entries[key] = hits
            while len(self.entries) > 4096:
                self.entries.popitem(last=False)
            if len(hits) >= limit:
                raise HTTPException(429, 'Too many requests', headers={'Retry-After': str(int(window))})
            hits.append(stamp)


def install_users(app, factory, guard, log, registered, execute):
    limits = RateLimits()
    # Equal-cost dummy verification for unknown names; no plaintext passwords in storage/audit.
    dummy = password_digest(secrets.token_urlsafe(24))

    @app.middleware('http')
    async def direct_response_guard(request: Request, call_next):
        owner_path = request.url.path.startswith('/panel/api/direct/')
        direct_path = owner_path or request.url.path.startswith('/api/v1/direct/')
        origin = request.headers.get('origin')
        if owner_path and request.method not in ('GET', 'HEAD', 'OPTIONS') and origin:
            try:
                parsed = urlsplit(origin)
                valid_origin = parsed.scheme == 'https' and parsed.netloc.lower() == request.headers.get('host', '').lower()
            except ValueError:
                valid_origin = False
            if not valid_origin:
                from fastapi.responses import JSONResponse
                return JSONResponse({'detail': 'Cross-origin owner request denied'}, status_code=403)
        response = await call_next(request)
        if direct_path:
            response.headers['Cache-Control'] = 'no-store'
            response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    def management_log(db, event, detail):
        log(db, 'direct_' + event, detail={'source': 'direct-vps', **detail, 'timestamp': now().isoformat()})

    def user_or_404(db, user_id):
        user = db.get(DirectUser, user_id)
        if user is None:
            raise HTTPException(404, 'User not found')
        return user

    def bearer(request):
        authorization = request.headers.get('authorization', '')
        token = authorization[7:] if authorization.startswith('Bearer ') else ''
        if not re.fullmatch(r'fgd_[A-Za-z0-9_-]{43}', token):
            raise HTTPException(401, 'Invalid Direct login', headers={'WWW-Authenticate': 'Bearer'})
        return hashlib.sha256(token.encode()).hexdigest()

    def authorized(request: Request):
        digest = bearer(request)
        with factory() as db:
            session = db.get(DirectSession, digest)
            expiry = session.expires_at if session else None
            if expiry and expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            user = db.get(DirectUser, session.user_id) if session else None
            if not session or expiry <= now() or not user or not user.active:
                raise HTTPException(401, 'Direct login expired or disabled', headers={'WWW-Authenticate': 'Bearer'})
            return user.id

    @app.post('/api/v1/direct/auth/login')
    def login(body: Login, request: Request, response: Response):
        username = body.username.strip().lower()
        peer = request.client.host if request.client else 'unknown'
        limits.check(('login-ip', peer), 60, 60)
        limits.check(('login-name', username), 10, 60)
        with factory() as db:
            user = db.scalar(select(DirectUser).where(DirectUser.username == username))
            valid = password_matches(body.password, user.password_hash if user else dummy)
            if not user or not valid or not user.active:
                raise HTTPException(401, 'Invalid username or password')
            db.execute(delete(DirectSession).where(DirectSession.expires_at < now()))
            # Limit live sessions per account. New login evicts the oldest, not other users.
            sessions = list(db.scalars(select(DirectSession).where(DirectSession.user_id == user.id)
                                       .order_by(DirectSession.expires_at)))
            for old in sessions[:-4]:
                db.delete(old)
            token = 'fgd_' + secrets.token_urlsafe(32)
            db.add(DirectSession(token_hash=hashlib.sha256(token.encode()).hexdigest(),
                                 user_id=user.id, expires_at=now() + timedelta(hours=12)))
            management_log(db, 'user_login', {'user': user.id})
            db.commit()
            response.headers['Cache-Control'] = 'no-store'
            return {'access_token': token, 'token_type': 'bearer', 'expires_in': 43200,
                    'username': user.username, 'source': 'direct-vps'}

    @app.post('/api/v1/direct/auth/logout')
    def logout(request: Request, user_id=Depends(authorized)):
        with factory() as db:
            session = db.get(DirectSession, bearer(request))
            if session:
                db.delete(session)
            management_log(db, 'user_logout', {'user': user_id})
            db.commit()
        return {'ok': True}

    @app.get('/api/v1/direct/devices')
    def devices(response: Response, user_id=Depends(authorized)):
        limits.check(('read', user_id), 60, 60)
        response.headers['Cache-Control'] = 'no-store'
        with factory() as db:
            result = []
            grants = list(db.scalars(select(DirectGrant).where(DirectGrant.user_id == user_id)))
            snapshot = adapter.status_many([grant.mac for grant in grants])
            for grant in grants:
                row = db.get(DirectRegistration, grant.mac)
                if not row:
                    continue
                live = snapshot[row.mac]
                live.pop('peer', None)  # Internal/remote networking metadata stays in owner panel.
                visible = set(channels(grant.view_mask))
                live['device_busy'] = bool(live.get('pending_outlets'))
                live['outlets'] = [o for o in live.get('outlets', []) if o.get('channel') in visible]
                live['pending_outlets'] = [n for n in live.get('pending_outlets', []) if n in visible]
                result.append({**live, 'mac': row.mac, 'transport': 'direct-vps', 'tcp_port': 10086,
                               'visible_outlets': sorted(visible),
                               'allowed_outlets': channels(row.outlet_mask & grant.control_mask & grant.view_mask)})
            return {'devices': result, 'source': 'direct-vps'}

    @app.post('/api/v1/direct/devices/{mac}/outlets/{outlet}')
    def control(mac: str, outlet: int, state: str, user_id=Depends(authorized)):
        limits.check(('command', user_id), 1, 1)
        with factory() as db:
            grant = db.get(DirectGrant, (user_id, mac.upper()))
            if not grant:
                raise HTTPException(404, 'Device not found')
            row = registered(db, mac)
            return execute(db, row, outlet, state, 'direct-user:' + user_id,
                           grant.control_mask & grant.view_mask)

    @app.get('/api/v1/direct/commands/{command_id}')
    def status(command_id: str, user_id=Depends(authorized)):
        limits.check(('read', user_id), 60, 60)
        with factory() as db:
            command = db.get(DirectCommand, command_id)
            if not command or command.actor != 'direct-user:' + user_id:
                raise HTTPException(404, 'Command not found')
            grant = db.get(DirectGrant, (user_id, command.mac))
            if not grant or not grant.view_mask & (1 << (command.outlet - 1)):
                raise HTTPException(404, 'Command not found')
            stamp = command.created_at
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            if command.status in ('queued', 'sent') and stamp < now() - timedelta(seconds=20):
                command.status = 'timeout'
                db.commit()
            return {'command_id': command.id, 'status': command.status, 'mac': command.mac,
                    'outlet': command.outlet, 'state': command.state, 'source': 'direct-vps'}

    @app.get('/panel/api/direct/users', dependencies=[Depends(guard)])
    def users():
        with factory() as db:
            result = []
            for user in db.scalars(select(DirectUser).order_by(DirectUser.username)):
                grants = db.scalars(select(DirectGrant).where(DirectGrant.user_id == user.id))
                result.append({'id': user.id, 'username': user.username, 'display_name': user.display_name,
                               'active': user.active, 'grants': [{'mac': g.mac, 'view_mask': g.view_mask,
                               'control_mask': g.control_mask} for g in grants]})
            return {'users': result}

    @app.post('/panel/api/direct/users', dependencies=[Depends(guard)])
    def create_user(body: UserCreate, response: Response):
        username = body.username.strip().lower()
        if not re.fullmatch(r'[a-z0-9][a-z0-9._-]{2,63}', username):
            raise HTTPException(422, 'Username: 3..64 Latin letters, numbers, dot, underscore or dash')
        password = body.password or secrets.token_urlsafe(18)
        with factory() as db:
            user = DirectUser(id=str(uuid.uuid4()), username=username, display_name=body.display_name or username,
                              password_hash=password_digest(password), active=True)
            db.add(user)
            management_log(db, 'user_created', {'user': user.id, 'username': username})
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                raise HTTPException(409, 'Username already exists')
            response.headers['Cache-Control'] = 'no-store'
            return {'id': user.id, 'username': username, 'password': password, 'show_once': True}

    @app.patch('/panel/api/direct/users/{user_id}', dependencies=[Depends(guard)])
    def change_user(user_id: str, body: UserUpdate):
        with factory() as db:
            user = user_or_404(db, user_id)
            user.active = body.active
            if not body.active:
                db.execute(delete(DirectSession).where(DirectSession.user_id == user_id))
            management_log(db, 'user_state_changed', {'user': user_id, 'active': body.active})
            db.commit()
            return {'ok': True}

    @app.post('/panel/api/direct/users/{user_id}/reset-password', dependencies=[Depends(guard)])
    def reset_password(user_id: str, response: Response):
        password = secrets.token_urlsafe(18)
        with factory() as db:
            user = user_or_404(db, user_id)
            user.password_hash = password_digest(password)
            db.execute(delete(DirectSession).where(DirectSession.user_id == user_id))
            management_log(db, 'user_password_reset', {'user': user_id})
            db.commit()
            response.headers['Cache-Control'] = 'no-store'
            return {'username': user.username, 'password': password, 'show_once': True}

    @app.post('/panel/api/direct/registrations', dependencies=[Depends(guard)])
    def add_device(body: DeviceCreate):
        mac = body.mac.upper()
        if not re.fullmatch(r'[0-9A-F]{12}', mac):
            raise HTTPException(422, 'Expected 12 hexadecimal MAC characters')
        try:
            adapter.allow(mac)  # Daemon writes its own private, persistent allow-list.
        except (OSError, ValueError):
            raise HTTPException(503, 'Persistent Direct allow-list unavailable; update daemon first')
        with factory() as db:
            if db.get(DirectRegistration, mac) is None:
                db.add(DirectRegistration(mac=mac, outlet_mask=15))
                management_log(db, 'device_registered', {'mac': mac})
                try:
                    db.commit()
                except IntegrityError:
                    db.rollback()
            return {'ok': True, 'mac': mac}

    @app.put('/panel/api/direct/registrations/{mac}/policy', dependencies=[Depends(guard)])
    def device_policy(mac: str, body: PolicyInput):
        with factory() as db:
            row = registered(db, mac)
            row.outlet_mask = body.control_mask
            management_log(db, 'device_policy_changed', {'mac': row.mac, 'control_mask': body.control_mask})
            db.commit()
            return {'ok': True}

    @app.put('/panel/api/direct/users/{user_id}/devices/{mac}', dependencies=[Depends(guard)])
    def grant_device(user_id: str, mac: str, body: GrantInput):
        if body.control_mask & ~body.view_mask:
            raise HTTPException(422, 'Control outlets must also be visible')
        with factory() as db:
            user_or_404(db, user_id)
            row = registered(db, mac)
            grant = db.get(DirectGrant, (user_id, row.mac))
            if not grant:
                grant = DirectGrant(user_id=user_id, mac=row.mac)
                db.add(grant)
            grant.view_mask, grant.control_mask = body.view_mask, body.control_mask
            management_log(db, 'grant_changed', {'user': user_id, 'mac': row.mac,
                           'view_mask': body.view_mask, 'control_mask': body.control_mask})
            db.commit()
            return {'ok': True}

    @app.delete('/panel/api/direct/users/{user_id}/devices/{mac}', dependencies=[Depends(guard)])
    def revoke_device(user_id: str, mac: str):
        with factory() as db:
            user_or_404(db, user_id)
            grant = db.get(DirectGrant, (user_id, mac.upper()))
            if grant:
                db.delete(grant)
            management_log(db, 'grant_revoked', {'user': user_id, 'mac': mac.upper()})
            db.commit()
            return {'ok': True}
