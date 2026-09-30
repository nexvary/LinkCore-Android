"""Account-scoped Direct alerts. SMTP stays on the server; no Android relay required."""
from __future__ import annotations
import logging
import math
import os
import smtplib
import ssl
import threading
from datetime import timedelta, timezone
from email.message import EmailMessage
from fastapi import Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, select, update
from sqlalchemy.orm import Mapped, mapped_column
from .direct_mttl import adapter
from .legacy_direct import DirectBase, now

logger = logging.getLogger(__name__)

class DirectEmailPreference(DirectBase):
    __tablename__ = 'fg_direct_email_preferences'
    user_id: Mapped[str] = mapped_column(ForeignKey('fg_direct_users.id'), primary_key=True)
    email: Mapped[str] = mapped_column(String(254), default='')
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    power_w: Mapped[int] = mapped_column(Integer, default=3000)
    temperature_c: Mapped[int] = mapped_column(Integer, default=70)

class DirectEmailState(DirectBase):
    __tablename__ = 'fg_direct_email_states'
    user_id: Mapped[str] = mapped_column(ForeignKey('fg_direct_users.id'), primary_key=True)
    mac: Mapped[str] = mapped_column(String(12), primary_key=True)
    kind: Mapped[str] = mapped_column(String(40), primary_key=True)
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    delivered: Mapped[bool] = mapped_column(Boolean, default=False)
    changed_at: Mapped[object] = mapped_column(DateTime(timezone=True))
    attempted_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)

class EmailSettings(BaseModel):
    email: EmailStr
    enabled: bool
    power_w: int = Field(default=3000, ge=100, le=10000)
    temperature_c: int = Field(default=70, ge=30, le=120)


def smtp_ready():
    return bool(os.getenv('FGRCK_SMTP_HOST', '').strip() and
                (os.getenv('FGRCK_SMTP_FROM', '').strip() or os.getenv('FGRCK_SMTP_USER', '').strip()))


def send_email(recipient, subject, body):
    if not smtp_ready():
        raise HTTPException(503, 'SMTP is not configured on the server')
    security = os.getenv('FGRCK_SMTP_SECURITY', 'starttls').lower()
    if security not in ('ssl', 'starttls', 'none'):
        raise HTTPException(503, 'SMTP configuration is invalid')
    message = EmailMessage()
    message['From'] = os.getenv('FGRCK_SMTP_FROM') or os.getenv('FGRCK_SMTP_USER')
    message['To'], message['Subject'] = recipient, subject
    message.set_content(body)
    try:
        cls = smtplib.SMTP_SSL if security == 'ssl' else smtplib.SMTP
        args = {'timeout': 10}
        if security == 'ssl': args['context'] = ssl.create_default_context()
        with cls(os.environ['FGRCK_SMTP_HOST'], int(os.getenv('FGRCK_SMTP_PORT', '587')), **args) as smtp:
            if security == 'starttls': smtp.starttls(context=ssl.create_default_context())
            user = os.getenv('FGRCK_SMTP_USER', '')
            if user: smtp.login(user, os.getenv('FGRCK_SMTP_PASSWORD', ''))
            smtp.send_message(message)
    except Exception as error:
        # Do not expose SMTP credentials, provider responses or recipient details.
        raise HTTPException(502, 'SMTP delivery failed') from error


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def flag(value):
    return str(value).lower() in ('1', 'true', 'on')


def exceeds(value, limit):
    try: return math.isfinite(float(value)) and float(value) >= limit
    except (TypeError, ValueError): return False


class DirectEmailMonitor:
    def __init__(self, factory, audit):
        self.factory, self.audit = factory, audit
        self.stop_event = threading.Event()
        self.thread = None

    def start(self):
        if os.getenv('FGRCK_DIRECT_EMAIL_WORKER_ENABLED', 'true').lower() == 'false': return
        if not smtp_ready(): return
        self.thread = threading.Thread(target=self.run, daemon=True, name='direct-email-alerts')
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread: self.thread.join(timeout=12)

    def run(self):
        while not self.stop_event.wait(30):
            try: self.scan()
            except Exception: logger.warning('Direct email scan unavailable; retrying next interval')

    def scan(self):
        from .legacy_direct_users import DirectUser, DirectGrant
        with self.factory() as db:
            prefs = list(db.scalars(select(DirectEmailPreference).where(DirectEmailPreference.enabled.is_(True))))
            for pref in prefs:
                user = db.get(DirectUser, pref.user_id)
                if not user or not user.active: continue
                grants = list(db.scalars(select(DirectGrant).where(DirectGrant.user_id == user.id)))
                # IPC errors never become fake device disconnects.
                snapshot = adapter.status_many_strict([g.mac for g in grants])
                for grant in grants:
                    live = snapshot[grant.mac]
                    connected = bool(live.get('connected'))
                    events = {'offline': not connected}
                    for outlet in live.get('outlets', []) if connected else []:
                        channel = outlet.get('channel')
                        if not isinstance(channel, int) or channel not in (1, 2, 3, 4): continue
                        if not grant.view_mask & (1 << (channel - 1)): continue
                        events[f'protection_{channel}'] = flag(outlet.get('overload')) or flag(outlet.get('overheat'))
                        events[f'power_{channel}'] = exceeds(outlet.get('power_w'), pref.power_w)
                        events[f'temperature_{channel}'] = exceeds(outlet.get('temperature_c'), pref.temperature_c)
                    for kind, active in events.items():
                        key = (user.id, grant.mac, kind)
                        state = db.get(DirectEmailState, key)
                        if state is None:
                            # Baseline offline devices are not reported as newly disconnected.
                            state = DirectEmailState(user_id=user.id, mac=grant.mac, kind=kind,
                                active=active, delivered=(kind == 'offline' and active), changed_at=now())
                            db.add(state); db.commit()
                        elif state.active != active:
                            state.active, state.delivered = active, False
                            state.changed_at, state.attempted_at = now(), None
                            db.commit()
                        if not active or state.delivered: continue
                        if kind == 'offline' and now() - aware(state.changed_at) < timedelta(seconds=120): continue
                        if state.attempted_at and now() - aware(state.attempted_at) < timedelta(minutes=5): continue
                        prior = state.attempted_at
                        claimed = db.execute(update(DirectEmailState).where(
                            DirectEmailState.user_id == user.id, DirectEmailState.mac == grant.mac,
                            DirectEmailState.kind == kind, DirectEmailState.active.is_(True),
                            DirectEmailState.delivered.is_(False), DirectEmailState.attempted_at == prior
                        ).values(attempted_at=now()))
                        db.commit()
                        if not claimed.rowcount: continue
                        # Recheck policy immediately before delivery.
                        db.expire_all()
                        current_grant = db.get(DirectGrant, (user.id, grant.mac))
                        if not pref.enabled or not user.active or current_grant is None: continue
                        if kind != 'offline' and not current_grant.view_mask & (1 << (int(kind.rsplit('_', 1)[1]) - 1)): continue
                        try:
                            send_email(pref.email, 'FG Link — تنبيه / Alert',
                                f'Device / المشترك: {grant.mac}\nEvent / التنبيه: {kind}\n'
                                'راجع حالة المشترك قبل اتخاذ أي إجراء. / Check the device state before taking action.')
                        except HTTPException:
                            self.audit(db, 'email_delivery_failed', {'user': user.id, 'mac': grant.mac, 'kind': kind})
                        else:
                            state.delivered = True
                            self.audit(db, 'email_alert_sent', {'user': user.id, 'mac': grant.mac, 'kind': kind})
                        db.commit()


def install_email(app, factory, authorized, limits, audit):
    monitor = DirectEmailMonitor(factory, audit)
    app.state.fg_direct_email_monitor = monitor
    app.add_event_handler('startup', monitor.start)
    app.add_event_handler('shutdown', monitor.stop)

    def payload(row):
        return {'source': 'direct-vps', 'smtp_ready': smtp_ready(),
                'email': row.email if row else '', 'enabled': bool(row and row.enabled),
                'power_w': row.power_w if row else 3000, 'temperature_c': row.temperature_c if row else 70}

    @app.get('/api/v1/direct/email-settings')
    def settings(user_id=Depends(authorized)):
        limits.check(('email-read', user_id), 30, 60)
        with factory() as db: return payload(db.get(DirectEmailPreference, user_id))

    @app.put('/api/v1/direct/email-settings')
    def save(body: EmailSettings, user_id=Depends(authorized)):
        limits.check(('email-save', user_id), 10, 60)
        if body.enabled and not smtp_ready(): raise HTTPException(503, 'SMTP is not configured on the server')
        with factory() as db:
            row = db.get(DirectEmailPreference, user_id)
            if row is None:
                row = DirectEmailPreference(user_id=user_id); db.add(row)
            row.email, row.enabled = str(body.email), body.enabled
            row.power_w, row.temperature_c = body.power_w, body.temperature_c
            audit(db, 'email_settings_changed', {'user': user_id, 'enabled': body.enabled})
            db.commit(); return payload(row)

    @app.post('/api/v1/direct/email-settings/test')
    def test(user_id=Depends(authorized)):
        limits.check(('email-test', user_id), 1, 60)
        with factory() as db:
            row = db.get(DirectEmailPreference, user_id)
            if row is None or not row.email: raise HTTPException(409, 'Save your email address first')
            send_email(row.email, 'FG Link — اختبار التنبيهات / Alert test',
                       'رسالة اختبار لتنبيهات حسابك. / Test message for your account notifications.')
            audit(db, 'email_test_sent', {'user': user_id}); db.commit()
            return {'source': 'direct-vps', 'status': 'sent'}
