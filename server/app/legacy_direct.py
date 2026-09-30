"""Direct VPS extension for the deployed FG Link Server 0.5 API.

Install against its existing engine, session factory and panel guard. No legacy
account/strip schema, controller route or deployment image is replaced.
"""
from __future__ import annotations

import base64
import functools
import inspect
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import DateTime, Integer, String, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from starlette.concurrency import run_in_threadpool
from fastapi.routing import request_response

from .direct_mttl import adapter, direct_macs
from .legacy_direct_ui import WIDGET, PANEL_LAYOUT
from .legacy_direct_users_ui import USERS_WIDGET


class DirectBase(DeclarativeBase):
    pass


class DirectRegistration(DirectBase):
    __tablename__ = 'fg_direct_registrations'
    mac: Mapped[str] = mapped_column(String(12), primary_key=True)
    outlet_mask: Mapped[int] = mapped_column(Integer, default=15)


class DirectCommand(DirectBase):
    __tablename__ = 'fg_direct_commands'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    mac: Mapped[str] = mapped_column(String(12), index=True)
    actor: Mapped[str] = mapped_column(String(120))
    outlet: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(16))
    detail: Mapped[str] = mapped_column(String(512), default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


def now():
    return datetime.now(timezone.utc)


def actor_for(request):
    # Caddy's existing Basic Auth verifies the browser username. Never retain
    # or log the password; the panel-token dependency authenticates every route.
    authorization = request.headers.get('authorization', '')
    if authorization.startswith('Basic '):
        try:
            username = base64.b64decode(authorization[6:], validate=True).decode().split(':', 1)[0]
            return username[:120] or 'owner-panel'
        except (ValueError, UnicodeDecodeError):
            pass
    return 'owner-panel'


def inject_widget(response):
    if isinstance(response, str):
        response = HTMLResponse(response)
    if not isinstance(response, HTMLResponse):
        return response
    body = response.body.decode(response.charset)
    if 'id="fg-direct-vps"' in body:
        return response
    widget = WIDGET + USERS_WIDGET + PANEL_LAYOUT
    body = body.replace('</body>', widget + '</body>') if '</body>' in body else body + widget
    response.body = body.encode(response.charset)
    response.headers['content-length'] = str(len(response.body))
    response.headers['cache-control'] = 'no-store'
    return response


def install(app, engine, session_factory, panel_guard, legacy_log):
    if getattr(app.state, 'fg_direct_installed', False):
        return
    app.state.fg_direct_installed = True

    def audit(db, command, result):
        legacy_log(db, 'direct_command_' + result, detail={
            'source': 'direct-vps', 'user': command.actor, 'mac': command.mac,
            'outlet': command.outlet, 'requested_state': command.state,
            'timestamp': now().isoformat(), 'command_id': command.id, 'result': result})

    def registered(db, mac):
        normalized = mac.upper()
        registration = db.get(DirectRegistration, normalized)
        if registration is None:
            raise HTTPException(404, 'Direct device not registered')
        return registration

    @app.on_event('startup')
    def direct_schema():
        DirectBase.metadata.create_all(bind=engine)
        with session_factory() as db:
            for mac in direct_macs():
                if db.get(DirectRegistration, mac) is None:
                    db.add(DirectRegistration(mac=mac, outlet_mask=15))
            db.commit()

    @app.get('/panel/api/direct/devices', dependencies=[Depends(panel_guard)])
    def devices():
        with session_factory() as db:
            rows = list(db.scalars(select(DirectRegistration)))
            snapshot = adapter.status_many([row.mac for row in rows])
            result = []
            for row in rows:
                live = snapshot[row.mac]
                result.append({**live, 'mac': row.mac, 'transport': 'direct-vps', 'tcp_port': 10086,
                               'allowed_outlets': [n for n in range(1, 5) if row.outlet_mask & (1 << (n - 1))]})
            return {'devices': result, 'source': 'direct-vps'}

    @app.post('/panel/api/direct/devices/{mac}/outlets/{outlet}', dependencies=[Depends(panel_guard)])
    def control(mac: str, outlet: int, request: Request, state: str):
        with session_factory() as db:
            row = registered(db, mac)
            return execute(db, row, outlet, state, actor_for(request), row.outlet_mask)

    def execute(db, row, outlet, state, actor, control_mask):
        if state not in ('on', 'off') or outlet not in (1, 2, 3, 4):
            raise HTTPException(422, 'Expected outlet 1..4 and state on/off')
        if not (row.outlet_mask & control_mask) & (1 << (outlet - 1)):
            raise HTTPException(403, 'Outlet policy denies control')
        live = adapter.status(row.mac)
        if not live.get('control_enabled'):
            raise HTTPException(409, 'Direct control disabled')
        if not live.get('connected'):
            raise HTTPException(409, 'Direct device offline')
        command = DirectCommand(id=str(uuid.uuid4()), mac=row.mac, actor=actor,
                                outlet=outlet, state=state, status='queued', created_at=now())
        db.add(command)
        audit(db, command, 'queued')
        db.commit()
        command.status = 'sent'
        db.commit()
        try:
            result = adapter.control(row.mac, outlet, state)
            command.status = result.get('status', 'failed')
            if command.status not in ('confirmed', 'timeout', 'failed'):
                command.status = 'failed'
            command.detail = result.get('error', 'fresh device confirmation')[:512]
        except (OSError, ValueError):
            command.status = 'timeout'
            command.detail = 'IPC unavailable; physical outcome unknown'
        command.completed_at = now()
        audit(db, command, command.status)
        db.commit()
        return {'ok': command.status == 'confirmed', 'command_id': command.id,
                'status': command.status, 'detail': command.detail, 'source': 'direct-vps'}

    @app.get('/panel/api/direct/commands/{command_id}', dependencies=[Depends(panel_guard)])
    def command_status(command_id: str):
        with session_factory() as db:
            command = db.get(DirectCommand, command_id)
            if command is None:
                raise HTTPException(404, 'Command not found')
            ts = command.created_at
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if command.status in ('queued', 'sent') and ts < now() - timedelta(seconds=20):
                command.status = 'timeout'
                command.detail = 'interrupted request; physical outcome unknown'
                audit(db, command, command.status)
                db.commit()
            return {'command_id': command.id, 'mac': command.mac, 'outlet': command.outlet,
                    'state': command.state, 'user': command.actor, 'status': command.status,
                    'detail': command.detail, 'source': 'direct-vps'}

    from .legacy_direct_users import install_users
    install_users(app, session_factory, panel_guard, legacy_log, registered, execute)

    for route in app.routes:
        if getattr(route, 'path', None) != '/panel' or not hasattr(route, 'dependant'):
            continue
        original = route.endpoint

        @functools.wraps(original)
        async def wrapped(*args, _original=original, **kwargs):
            if inspect.iscoroutinefunction(_original):
                response = await _original(*args, **kwargs)
            else:
                response = await run_in_threadpool(_original, *args, **kwargs)
            return inject_widget(response)

        route.endpoint = wrapped
        route.dependant.call = wrapped
        route.app = request_response(route.get_route_handler())
