from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import os
import re
import secrets
import smtplib
import ssl
import uuid
from email.message import EmailMessage
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Generator, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    and_,
    create_engine,
    or_,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from .panel import router as panel_router
from .direct_mttl import adapter as direct_adapter, direct_macs


APP_NAME = "FG Machines Link Cloud"
API_PREFIX = "/api/v1"
ENVIRONMENT = os.getenv("FGRCK_ENV", "development").strip().lower()
DATABASE_URL = os.getenv("FGRCK_DATABASE_URL", "sqlite+pysqlite:///./fg_rck_cloud.db")
JWT_SECRET = os.getenv("FGRCK_JWT_SECRET", "development-only-change-me")
TOKEN_PEPPER = os.getenv("FGRCK_TOKEN_PEPPER", "development-only-pepper")
JWT_TTL_MINUTES = max(15, int(os.getenv("FGRCK_JWT_TTL_MINUTES", "720")))
COMMAND_TTL_SECONDS = max(30, int(os.getenv("FGRCK_COMMAND_TTL_SECONDS", "180")))
CONTROLLER_ONLINE_SECONDS = max(30, int(os.getenv("FGRCK_CONTROLLER_ONLINE_SECONDS", "90")))
COMMAND_REDELIVER_SECONDS = max(10, int(os.getenv("FGRCK_COMMAND_REDELIVER_SECONDS", "30")))
MAX_COMMAND_ATTEMPTS = max(1, int(os.getenv("FGRCK_MAX_COMMAND_ATTEMPTS", "5")))
SIGNED_COMMAND_TTL_SECONDS = max(30, min(300, int(os.getenv("FGRCK_SIGNED_COMMAND_TTL_SECONDS", "120"))))
SIGNED_COMMAND_CLOCK_SKEW_SECONDS = max(30, min(300, int(os.getenv("FGRCK_SIGNED_COMMAND_CLOCK_SKEW_SECONDS", "90"))))
SMTP_HOST = os.getenv("FGRCK_SMTP_HOST", "").strip()
SMTP_PORT = max(1, int(os.getenv("FGRCK_SMTP_PORT", "587")))
SMTP_USER = os.getenv("FGRCK_SMTP_USER", "").strip()
SMTP_PASSWORD = os.getenv("FGRCK_SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("FGRCK_SMTP_FROM", SMTP_USER).strip()
SMTP_SECURITY = os.getenv("FGRCK_SMTP_SECURITY", "starttls").strip().lower()
SMTP_TIMEOUT_SECONDS = max(3, int(os.getenv("FGRCK_SMTP_TIMEOUT_SECONDS", "10")))

ROLE_RANK = {"view": 10, "control": 20, "admin": 30, "owner": 40}
MAC_RE = re.compile(r"^[0-9A-F]{12}$")
password_hasher = PasswordHasher(time_cost=2, memory_cost=65536, parallelism=2)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


def normalize_mac(value: str) -> str:
    raw = re.sub(r"[^0-9A-Fa-f]", "", value or "").upper()
    if not MAC_RE.fullmatch(raw):
        raise HTTPException(status_code=422, detail="MAC must contain exactly 12 hexadecimal digits")
    return raw


def hash_secret(value: str) -> str:
    return hmac.new(TOKEN_PEPPER.encode(), value.encode(), hashlib.sha256).hexdigest()


def issue_secret(prefix: str) -> str:
    return prefix + "_" + secrets.token_urlsafe(32)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Controller(Base):
    __tablename__ = "controllers"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Device(Base):
    __tablename__ = "devices"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    controller_id: Mapped[str] = mapped_column(ForeignKey("controllers.id"), index=True)
    mac: Mapped[str] = mapped_column(String(12), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), default="")
    room: Mapped[str] = mapped_column(String(120), default="")
    firmware: Mapped[str] = mapped_column(String(80), default="")
    online: Mapped[bool] = mapped_column(Boolean, default=False)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DeviceAccess(Base):
    __tablename__ = "device_access"
    __table_args__ = (UniqueConstraint("device_id", "user_id", name="uq_device_access_user"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OutletPolicy(Base):
    __tablename__ = "outlet_policies"
    __table_args__ = (UniqueConstraint("device_id", "user_id", name="uq_outlet_policy_user"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    outlet_mask: Mapped[int] = mapped_column(Integer, default=15)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DeviceBinding(Base):
    __tablename__ = "device_bindings"
    __table_args__ = (
        UniqueConstraint("controller_id", "key_id", name="uq_device_binding_controller_key"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    controller_id: Mapped[str] = mapped_column(ForeignKey("controllers.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    key_id: Mapped[str] = mapped_column(String(64), index=True)
    public_key_b64: Mapped[str] = mapped_column(String(1024))
    label: Mapped[str] = mapped_column(String(120), default="")
    hardware_backed: Mapped[bool] = mapped_column(Boolean, default=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ShareInvite(Base):
    __tablename__ = "share_invites"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), index=True)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    code_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    role: Mapped[str] = mapped_column(String(16))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Command(Base):
    __tablename__ = "commands"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    controller_id: Mapped[str] = mapped_column(ForeignKey("controllers.id"), index=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), index=True)
    requested_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    outlet: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(8))
    source: Mapped[str] = mapped_column(String(32), default="app")
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ack_detail: Mapped[str] = mapped_column(String(512), default="")


class CommandProof(Base):
    __tablename__ = "command_proofs"
    __table_args__ = (UniqueConstraint("nonce", name="uq_command_proof_nonce"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    command_id: Mapped[str] = mapped_column(ForeignKey("commands.id"), unique=True, index=True)
    key_id: Mapped[str] = mapped_column(String(64), index=True)
    nonce: Mapped[str] = mapped_column(String(128), index=True)
    issued_at: Mapped[int] = mapped_column(BigInteger)
    valid_until: Mapped[int] = mapped_column(BigInteger)
    signature_b64: Mapped[str] = mapped_column(String(1024))
    canonical_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TelemetrySnapshot(Base):
    __tablename__ = "telemetry_snapshots"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    power_w: Mapped[float] = mapped_column(Float, default=0.0)
    energy_kwh: Mapped[float] = mapped_column(Float, default=0.0)
    max_temp_c: Mapped[int] = mapped_column(Integer, default=0)
    relay_mask: Mapped[int] = mapped_column(Integer, default=0)
    event_code: Mapped[str] = mapped_column(String(64), default="")


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    device_id: Mapped[str | None] = mapped_column(ForeignKey("devices.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    detail: Mapped[str] = mapped_column(String(512), default="")
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


bearer = HTTPBearer(auto_error=False)


def create_access_token(user: User) -> str:
    now = utcnow()
    payload = {
        "sub": user.id,
        "email": user.email,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=JWT_TTL_MINUTES)).timestamp()),
        "iss": "fg-machines-rck",
        "aud": "fg-rck-cloud",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Bearer token required")
    try:
        claims = jwt.decode(
            credentials.credentials,
            JWT_SECRET,
            algorithms=["HS256"],
            audience="fg-rck-cloud",
            issuer="fg-machines-rck",
        )
        user_id = str(claims.get("sub", ""))
    except jwt.PyJWTError as error:
        raise HTTPException(status_code=401, detail="Invalid or expired access token") from error
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Account no longer exists")
    return user


def audit(db: Session, action: str, user_id: str | None = None,
          device_id: str | None = None, detail: str = "") -> None:
    db.add(AuditLog(user_id=user_id, device_id=device_id, action=action, detail=detail[:512]))


def role_for(db: Session, user: User, device: Device) -> str | None:
    if device.owner_user_id == user.id:
        return "owner"
    access = db.scalar(select(DeviceAccess).where(
        DeviceAccess.device_id == device.id,
        DeviceAccess.user_id == user.id,
    ))
    return access.role if access else None


def require_device_role(db: Session, user: User, device: Device, minimum: str) -> str:
    role = role_for(db, user, device)
    if role is None or ROLE_RANK.get(role, 0) < ROLE_RANK[minimum]:
        raise HTTPException(status_code=403, detail=f"{minimum} access required")
    return role


def allowed_outlets_for(db: Session, user: User, device: Device) -> list[int]:
    role = role_for(db, user, device)
    if role == "owner":
        return [1, 2, 3, 4]
    if role is None or ROLE_RANK.get(role, 0) < ROLE_RANK["control"]:
        return []
    policy = db.scalar(select(OutletPolicy).where(
        OutletPolicy.device_id == device.id,
        OutletPolicy.user_id == user.id,
    ))
    # Existing control/admin shares had no outlet policy. Preserve their
    # all-outlet behavior until the owner explicitly saves a split policy.
    mask = 15 if policy is None else max(0, min(15, int(policy.outlet_mask)))
    return [outlet for outlet in range(1, 5) if mask & (1 << (outlet - 1))]


def device_by_mac(db: Session, mac: str) -> Device:
    normalized = normalize_mac(mac)
    device = db.scalar(select(Device).where(Device.mac == normalized))
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    return device


def controller_auth(db: Session, controller_id: str, controller_key: str | None) -> Controller:
    if not controller_key:
        raise HTTPException(status_code=401, detail="X-Controller-Key required")
    controller = db.get(Controller, controller_id)
    if controller is None or not hmac.compare_digest(controller.key_hash, hash_secret(controller_key)):
        raise HTTPException(status_code=401, detail="Invalid controller credentials")
    return controller


def is_device_online(device: Device) -> bool:
    if not device.online or device.last_seen is None:
        return False
    seen = device.last_seen
    if seen.tzinfo is None:
        seen = seen.replace(tzinfo=timezone.utc)
    return seen >= utcnow() - timedelta(seconds=CONTROLLER_ONLINE_SECONDS)


def deliver_alert_email(recipient: str, subject: str, body: str) -> None:
    if not SMTP_HOST or not SMTP_FROM:
        raise HTTPException(status_code=503, detail="SMTP email delivery is not configured")

    message = EmailMessage()
    message["From"] = SMTP_FROM
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)

    try:
        if SMTP_SECURITY == "ssl":
            with smtplib.SMTP_SSL(
                SMTP_HOST,
                SMTP_PORT,
                timeout=SMTP_TIMEOUT_SECONDS,
                context=ssl.create_default_context(),
            ) as smtp:
                if SMTP_USER:
                    smtp.login(SMTP_USER, SMTP_PASSWORD)
                smtp.send_message(message)
            return

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT_SECONDS) as smtp:
            if SMTP_SECURITY == "starttls":
                smtp.starttls(context=ssl.create_default_context())
            elif SMTP_SECURITY not in {"none", ""}:
                raise RuntimeError("Unsupported FGRCK_SMTP_SECURITY")
            if SMTP_USER:
                smtp.login(SMTP_USER, SMTP_PASSWORD)
            smtp.send_message(message)
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=502, detail="SMTP delivery failed") from error


def device_payload(device: Device, role: str, allowed_outlets: list[int] | None = None) -> dict:
    direct = device.mac in direct_macs()
    live = direct_adapter.status(device.mac) if direct else {}
    return {
        **live,
        "transport": "direct-vps" if direct else "android-lan",
        "tcp_port": 10086 if direct else None,
        "mac": device.mac,
        "name": device.name,
        "room": device.room,
        "firmware": live.get("firmware", device.firmware),
        "connected": live.get("connected", False) if direct else is_device_online(device),
        "last_seen": int(live.get("last_seen", 0) * 1000) if direct else (int(device.last_seen.timestamp() * 1000) if device.last_seen else 0),
        "role": role,
        "allowed_outlets": allowed_outlets if allowed_outlets is not None
        else ([1, 2, 3, 4] if role == "owner" else []),
    }


def signed_command_canonical(
    controller_id: str,
    mac: str,
    outlet: int,
    state: str,
    issued_at: int,
    valid_until: int,
    nonce: str,
    key_id: str,
) -> str:
    return "\n".join([
        "FGLINK-CMD-V1",
        controller_id,
        normalize_mac(mac),
        str(int(outlet)),
        state.lower(),
        str(int(issued_at)),
        str(int(valid_until)),
        nonce,
        key_id.lower(),
    ])


def verify_device_binding_signature(
    db: Session,
    user: User,
    device: Device,
    outlet: int,
    state: str,
    key_id: str,
    nonce: str,
    issued_at: int,
    valid_until: int,
    signature_b64: str,
) -> str:
    now = int(utcnow().timestamp())
    if not re.fullmatch(r"[0-9a-fA-F]{64}", key_id or ""):
        raise HTTPException(status_code=422, detail="Invalid device binding key id")
    if not re.fullmatch(r"[A-Za-z0-9_-]{20,128}", nonce or ""):
        raise HTTPException(status_code=422, detail="Invalid command nonce")
    if issued_at > now + SIGNED_COMMAND_CLOCK_SKEW_SECONDS:
        raise HTTPException(status_code=401, detail="Signed command timestamp is in the future")
    if issued_at < now - SIGNED_COMMAND_CLOCK_SKEW_SECONDS:
        raise HTTPException(status_code=401, detail="Signed command timestamp is too old")
    if valid_until <= now:
        raise HTTPException(status_code=401, detail="Signed command expired")
    if valid_until < issued_at or valid_until - issued_at > SIGNED_COMMAND_TTL_SECONDS:
        raise HTTPException(status_code=422, detail="Signed command validity window is invalid")

    existing_nonce = db.scalar(select(CommandProof).where(CommandProof.nonce == nonce))
    if existing_nonce is not None:
        raise HTTPException(status_code=409, detail="Signed command nonce already used")

    binding = db.scalar(select(DeviceBinding).where(
        DeviceBinding.controller_id == device.controller_id,
        DeviceBinding.user_id == user.id,
        DeviceBinding.key_id == key_id.lower(),
        DeviceBinding.revoked.is_(False),
    ))
    if binding is None:
        raise HTTPException(status_code=403, detail="This phone installation is not bound to the controller")

    canonical = signed_command_canonical(
        device.controller_id,
        device.mac,
        outlet,
        state,
        issued_at,
        valid_until,
        nonce,
        key_id,
    )
    try:
        public_der = base64.b64decode(binding.public_key_b64, validate=True)
        public_key = serialization.load_der_public_key(public_der)
        if not isinstance(public_key, ec.EllipticCurvePublicKey):
            raise ValueError("not_ec")
        if not isinstance(public_key.curve, ec.SECP256R1):
            raise ValueError("wrong_curve")
        signature = base64.b64decode(signature_b64, validate=True)
        public_key.verify(signature, canonical.encode("utf-8"), ec.ECDSA(hashes.SHA256()))
    except (ValueError, TypeError, binascii.Error, InvalidSignature) as error:
        raise HTTPException(status_code=401, detail="Invalid device-bound command signature") from error
    return canonical


def queue_command(
    db: Session,
    user: User,
    device: Device,
    outlet: int,
    target_state: str,
    source: str,
    *,
    key_id: str,
    nonce: str,
    issued_at: int,
    valid_until: int,
    signature_b64: str,
    canonical: str,
) -> Command:
    if outlet < 1 or outlet > 4:
        raise HTTPException(status_code=422, detail="Outlet must be 1..4")
    if target_state not in {"on", "off"}:
        raise HTTPException(status_code=422, detail="State must be on or off")
    require_device_role(db, user, device, "control")
    if outlet not in allowed_outlets_for(db, user, device):
        raise HTTPException(status_code=403, detail=f"Outlet {outlet} is not assigned to this account")

    command = Command(
        controller_id=device.controller_id,
        device_id=device.id,
        requested_by_user_id=user.id,
        outlet=outlet,
        state=target_state,
        source=source[:32],
        expires_at=datetime.fromtimestamp(valid_until, timezone.utc),
    )
    db.add(command)
    db.flush()
    db.add(CommandProof(
        command_id=command.id,
        key_id=key_id.lower(),
        nonce=nonce,
        issued_at=issued_at,
        valid_until=valid_until,
        signature_b64=signature_b64,
        canonical_sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    ))
    audit(db, "signed_command_queued", user.id, device.id,
          f"{source}:outlet={outlet},state={target_state},key={key_id[:12]}")
    db.commit()
    db.refresh(command)
    return command


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class ControllerCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class DeviceBindingRequest(BaseModel):
    key_id: str = Field(min_length=64, max_length=64)
    public_key_b64: str = Field(min_length=80, max_length=1024)
    label: str = Field(default="", max_length=120)
    hardware_backed: bool = False


class DeviceRegisterRequest(BaseModel):
    controller_id: str
    mac: str
    name: str = Field(default="", max_length=120)
    room: str = Field(default="", max_length=120)
    firmware: str = Field(default="", max_length=80)


class ShareInviteRequest(BaseModel):
    role: Literal["view", "control", "admin"] = "view"
    expires_hours: int = Field(default=72, ge=1, le=720)


class ShareAcceptRequest(BaseModel):
    code: str = Field(min_length=20, max_length=512)


class AckRequest(BaseModel):
    status: Literal["acked", "failed"]
    detail: str = Field(default="", max_length=512)


class HeartbeatDevice(BaseModel):
    mac: str
    connected: bool = True
    firmware: str = Field(default="", max_length=80)


class HeartbeatRequest(BaseModel):
    devices: list[HeartbeatDevice] = Field(default_factory=list)


class TelemetryItem(BaseModel):
    mac: str
    power_w: float = Field(default=0.0, ge=0)
    energy_kwh: float = Field(default=0.0, ge=0)
    max_temp_c: int = 0
    relay_mask: int = Field(default=0, ge=0, le=15)
    event_code: str = Field(default="", max_length=64)


class TelemetryRequest(BaseModel):
    items: list[TelemetryItem] = Field(min_length=1, max_length=50)


class VoiceIntentRequest(BaseModel):
    mac: str
    action: Literal["on", "off"]
    outlet: int | None = Field(default=None, ge=1, le=4)
    all_outlets: bool = False
    confirm_all_on: bool = False


class EmailAlertRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=2000)


class OutletPolicyRequest(BaseModel):
    outlets: list[int] = Field(default_factory=list, max_length=4)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if ENVIRONMENT == "production":
        if JWT_SECRET == "development-only-change-me" or len(JWT_SECRET) < 32:
            raise RuntimeError("FGRCK_JWT_SECRET must be a strong production secret")
        if TOKEN_PEPPER == "development-only-pepper" or len(TOKEN_PEPPER) < 32:
            raise RuntimeError("FGRCK_TOKEN_PEPPER must be a strong production secret")
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title=APP_NAME,
    version="0.3.0",
    description="Account, sharing, outlet authorization and outbound-controller relay for FG Machines Link.",
    lifespan=lifespan,
)


app.include_router(panel_router)

@app.get("/healthz")
@app.get(f"{API_PREFIX}/health")
def health() -> dict:
    return {"ok": True, "service": "fg-link-cloud", "version": "0.3.0"}


@app.post(f"{API_PREFIX}/auth/register", status_code=201)
def register(body: RegisterRequest, db: Session = Depends(get_db)) -> dict:
    email = str(body.email).strip().lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(email=email, password_hash=password_hasher.hash(body.password))
    db.add(user)
    db.flush()
    audit(db, "account_registered", user.id, detail=email)
    db.commit()
    db.refresh(user)
    return {"access_token": create_access_token(user), "token_type": "bearer", "user_id": user.id}


@app.post(f"{API_PREFIX}/auth/login")
def login(body: LoginRequest, db: Session = Depends(get_db)) -> dict:
    email = str(body.email).strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    try:
        password_hasher.verify(user.password_hash, body.password)
    except VerifyMismatchError as error:
        raise HTTPException(status_code=401, detail="Invalid email or password") from error
    if password_hasher.check_needs_rehash(user.password_hash):
        user.password_hash = password_hasher.hash(body.password)
        db.commit()
    return {"access_token": create_access_token(user), "token_type": "bearer", "user_id": user.id}


@app.post(f"{API_PREFIX}/alerts/email")
def send_email_alert(
    body: EmailAlertRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    # The recipient is intentionally fixed to the authenticated account email
    # so this endpoint cannot be used as an arbitrary mail relay.
    deliver_alert_email(user.email, body.subject.strip(), body.body.strip())
    audit(db, "email_alert_sent", user.id, detail=body.subject.strip())
    db.commit()
    return {"ok": True, "recipient": user.email}


@app.post(f"{API_PREFIX}/controllers", status_code=201)
def create_controller(
    body: ControllerCreateRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    raw_key = issue_secret("fgrck_ctl")
    controller = Controller(
        owner_user_id=user.id,
        name=body.name.strip(),
        key_hash=hash_secret(raw_key),
    )
    db.add(controller)
    db.flush()
    audit(db, "controller_created", user.id, detail=controller.id)
    db.commit()
    db.refresh(controller)
    return {
        "controller_id": controller.id,
        "controller_key": raw_key,
        "note": "The controller key is shown once. Store it in Android private app storage.",
    }


@app.put(f"{API_PREFIX}/controllers/{{controller_id}}/device-binding")
def bind_controller_installation(
    controller_id: str,
    body: DeviceBindingRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    controller = db.get(Controller, controller_id)
    if controller is None or controller.owner_user_id != user.id:
        raise HTTPException(status_code=403, detail="Controller owner access required")

    key_id = body.key_id.lower()
    try:
        public_der = base64.b64decode(body.public_key_b64, validate=True)
        digest = hashlib.sha256(public_der).hexdigest()
        public_key = serialization.load_der_public_key(public_der)
        if not isinstance(public_key, ec.EllipticCurvePublicKey):
            raise ValueError("not_ec")
        if not isinstance(public_key.curve, ec.SECP256R1):
            raise ValueError("wrong_curve")
    except (ValueError, TypeError, binascii.Error) as error:
        raise HTTPException(status_code=422, detail="Invalid P-256 public key") from error
    if digest != key_id:
        raise HTTPException(status_code=422, detail="Key id does not match public-key fingerprint")

    existing = db.scalar(select(DeviceBinding).where(
        DeviceBinding.controller_id == controller.id,
        DeviceBinding.key_id == key_id,
    ))
    if existing is None:
        existing = DeviceBinding(
            controller_id=controller.id,
            user_id=user.id,
            key_id=key_id,
            public_key_b64=body.public_key_b64,
            label=body.label.strip(),
            hardware_backed=body.hardware_backed,
            revoked=False,
        )
        db.add(existing)
    else:
        if existing.user_id != user.id:
            raise HTTPException(status_code=409, detail="Device binding belongs to another account")
        existing.public_key_b64 = body.public_key_b64
        existing.label = body.label.strip()
        existing.hardware_backed = body.hardware_backed
        existing.revoked = False

    other_bindings = list(db.scalars(select(DeviceBinding).where(
        DeviceBinding.controller_id == controller.id,
        DeviceBinding.key_id != key_id,
        DeviceBinding.revoked.is_(False),
    )))
    for other in other_bindings:
        other.revoked = True

    audit(db, "device_binding_registered", user.id, detail=f"{controller.id}:{key_id[:16]}")
    db.commit()
    return {
        "ok": True,
        "controller_id": controller.id,
        "installation_fingerprint": key_id,
        "hardware_backed": existing.hardware_backed,
        "private_key_exported": False,
    }


@app.delete(f"{API_PREFIX}/controllers/{{controller_id}}/device-binding/{{key_id}}")
def revoke_controller_installation(
    controller_id: str,
    key_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    controller = db.get(Controller, controller_id)
    if controller is None or controller.owner_user_id != user.id:
        raise HTTPException(status_code=403, detail="Controller owner access required")
    binding = db.scalar(select(DeviceBinding).where(
        DeviceBinding.controller_id == controller.id,
        DeviceBinding.key_id == key_id.lower(),
        DeviceBinding.user_id == user.id,
    ))
    if binding is None:
        raise HTTPException(status_code=404, detail="Device binding not found")
    binding.revoked = True
    audit(db, "device_binding_revoked", user.id, detail=f"{controller.id}:{key_id[:16]}")
    db.commit()
    return {"ok": True, "installation_fingerprint": binding.key_id, "revoked": True}


@app.get(f"{API_PREFIX}/controllers")
def list_controllers(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    controllers = list(db.scalars(
        select(Controller)
        .where(Controller.owner_user_id == user.id)
        .order_by(Controller.created_at.asc())
    ))
    now = utcnow()
    rows = []
    for controller in controllers:
        seen = controller.last_seen
        if seen is not None and seen.tzinfo is None:
            seen = seen.replace(tzinfo=timezone.utc)
        binding = db.scalar(select(DeviceBinding).where(
            DeviceBinding.controller_id == controller.id,
            DeviceBinding.revoked.is_(False),
        ))
        rows.append({
            "controller_id": controller.id,
            "name": controller.name,
            "online": bool(seen and seen >= now - timedelta(seconds=CONTROLLER_ONLINE_SECONDS)),
            "last_seen": int(seen.timestamp() * 1000) if seen else 0,
            "installation_fingerprint": binding.key_id if binding else "",
            "hardware_backed": bool(binding.hardware_backed) if binding else False,
            "device_bound": binding is not None,
        })
    return {"controllers": rows}


@app.post(f"{API_PREFIX}/devices", status_code=201)
def register_device(
    body: DeviceRegisterRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    controller = db.get(Controller, body.controller_id)
    if controller is None or controller.owner_user_id != user.id:
        raise HTTPException(status_code=403, detail="Controller owner access required")
    mac = normalize_mac(body.mac)
    existing = db.scalar(select(Device).where(Device.mac == mac))
    if existing is not None:
        if existing.owner_user_id != user.id:
            raise HTTPException(status_code=409, detail="Device is already claimed")
        existing.controller_id = controller.id
        existing.name = ""
        existing.room = ""
        existing.firmware = body.firmware.strip()
        device = existing
    else:
        device = Device(
            owner_user_id=user.id,
            controller_id=controller.id,
            mac=mac,
            name="",
            room="",
            firmware=body.firmware.strip(),
        )
        db.add(device)
    db.flush()
    audit(db, "device_registered", user.id, device.id, mac)
    db.commit()
    db.refresh(device)
    return device_payload(device, "owner", [1, 2, 3, 4])


@app.get(f"{API_PREFIX}/devices")
def list_devices(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    shared_ids = list(db.scalars(select(DeviceAccess.device_id).where(DeviceAccess.user_id == user.id)))
    clause = Device.owner_user_id == user.id
    if shared_ids:
        clause = or_(clause, Device.id.in_(shared_ids))
    devices = list(db.scalars(select(Device).where(clause).order_by(Device.created_at.asc())))
    return {
        "devices": [
            device_payload(
                device,
                role_for(db, user, device) or "view",
                allowed_outlets_for(db, user, device),
            )
            for device in devices
        ]
    }


@app.post(f"{API_PREFIX}/devices/{{mac}}/direct-outlets/{{outlet}}")
def direct_set_outlet(mac: str, outlet: int, state: Literal["on", "off"],
                      user: User = Depends(current_user), db: Session = Depends(get_db)):
    device = device_by_mac(db, mac)
    require_device_role(db, user, device, "control")
    if outlet not in allowed_outlets_for(db, user, device):
        raise HTTPException(403, "Outlet policy denies control")
    if device.mac not in direct_macs():
        raise HTTPException(409, "Device is not configured for Direct VPS")
    live = direct_adapter.status(device.mac)
    if not live.get("control_enabled"):
        raise HTTPException(409, "Direct control disabled")
    if not live.get("connected"):
        raise HTTPException(409, "Direct device offline")
    command = Command(controller_id=device.controller_id, device_id=device.id,
                      requested_by_user_id=user.id, outlet=outlet, state=state,
                      source="direct-vps", status="queued",
                      expires_at=utcnow() + timedelta(seconds=15))
    db.add(command)
    audit(db, "direct_command_queued", user.id, device.id,
          f"source=direct-vps mac={device.mac} outlet={outlet} state={state} result=queued")
    db.commit()
    command.status = "sent"
    command.delivered_at = utcnow()
    command.attempts = 1
    db.commit()
    try:
        result = direct_adapter.control(device.mac, outlet, state)
        command.status = result.get("status", "failed")
        if command.status not in {"confirmed", "failed", "timeout"}:
            command.status = "failed"
        command.ack_detail = result.get("error", "fresh device confirmation")[:512]
    except (OSError, ValueError):
        command.status = "timeout"
        command.ack_detail = "IPC unavailable; physical outcome unknown"
    command.acked_at = utcnow()
    audit(db, "direct_command_" + command.status, user.id, device.id,
          f"source=direct-vps mac={device.mac} outlet={outlet} state={state} result={command.status}")
    db.commit()
    return {"ok": command.status == "confirmed", "command_id": command.id,
            "status": command.status, "source": "direct-vps", "detail": command.ack_detail}


@app.post(f"{API_PREFIX}/devices/{{mac}}/outlets/{{outlet}}")
def compatible_set_outlet(
    mac: str,
    outlet: int,
    state_value: str = Query(alias="state"),
    x_fg_key_id: str | None = Header(default=None, alias="X-FG-Key-Id"),
    x_fg_nonce: str | None = Header(default=None, alias="X-FG-Nonce"),
    x_fg_issued_at: int | None = Header(default=None, alias="X-FG-Issued-At"),
    x_fg_valid_until: int | None = Header(default=None, alias="X-FG-Valid-Until"),
    x_fg_signature: str | None = Header(default=None, alias="X-FG-Signature"),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    device = device_by_mac(db, mac)
    require_device_role(db, user, device, "control")
    state = state_value.lower()
    if None in (x_fg_key_id, x_fg_nonce, x_fg_issued_at, x_fg_valid_until, x_fg_signature):
        raise HTTPException(
            status_code=428,
            detail="A device-bound Android Keystore signature is required",
        )
    canonical = verify_device_binding_signature(
        db,
        user,
        device,
        outlet,
        state,
        str(x_fg_key_id),
        str(x_fg_nonce),
        int(x_fg_issued_at),
        int(x_fg_valid_until),
        str(x_fg_signature),
    )
    command = queue_command(
        db, user, device, outlet, state, "signed-app",
        key_id=str(x_fg_key_id),
        nonce=str(x_fg_nonce),
        issued_at=int(x_fg_issued_at),
        valid_until=int(x_fg_valid_until),
        signature_b64=str(x_fg_signature),
        canonical=canonical,
    )
    return {
        "ok": True,
        "command_id": command.id,
        "status": command.status,
        "zero_trust": True,
        "installation_fingerprint": str(x_fg_key_id).lower(),
    }


@app.get(f"{API_PREFIX}/history/{{mac}}")
def history(
    mac: str,
    hours: int = Query(default=24, ge=1, le=2160),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    device = device_by_mac(db, mac)
    require_device_role(db, user, device, "view")
    since = utcnow() - timedelta(hours=hours)
    samples = list(db.scalars(
        select(TelemetrySnapshot)
        .where(TelemetrySnapshot.device_id == device.id, TelemetrySnapshot.ts >= since)
        .order_by(TelemetrySnapshot.ts.desc())
        .limit(1000)
    ))
    return {
        "mac": device.mac,
        "hours": hours,
        "samples": [
            {
                "ts": int(item.ts.replace(tzinfo=item.ts.tzinfo or timezone.utc).timestamp() * 1000),
                "power_w": item.power_w,
                "energy_kwh": item.energy_kwh,
                "max_temp_c": item.max_temp_c,
                "relay_mask": item.relay_mask,
                "event_code": item.event_code,
            }
            for item in reversed(samples)
        ],
    }


@app.post(f"{API_PREFIX}/devices/{{mac}}/shares/invites", status_code=201)
def create_share_invite(
    mac: str,
    body: ShareInviteRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    device = device_by_mac(db, mac)
    actor_role = require_device_role(db, user, device, "admin")
    if body.role == "admin" and actor_role != "owner":
        raise HTTPException(status_code=403, detail="Only the owner can grant Admin")
    raw_code = issue_secret("fgrck_share")
    invite = ShareInvite(
        device_id=device.id,
        created_by_user_id=user.id,
        code_hash=hash_secret(raw_code),
        role=body.role,
        expires_at=utcnow() + timedelta(hours=body.expires_hours),
    )
    db.add(invite)
    audit(db, "share_invite_created", user.id, device.id, body.role)
    db.commit()
    return {
        "code": raw_code,
        "role": body.role,
        "expires_at": invite.expires_at.isoformat(),
        "note": "Treat this code like a password. It is shown only in this response.",
    }


@app.post(f"{API_PREFIX}/shares/accept")
def accept_share(
    body: ShareAcceptRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    invite = db.scalar(select(ShareInvite).where(ShareInvite.code_hash == hash_secret(body.code.strip())))
    if invite is None or invite.revoked:
        raise HTTPException(status_code=404, detail="Share code not found")
    if invite.accepted_at is not None:
        raise HTTPException(status_code=409, detail="Share code already used")
    expires = invite.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires <= utcnow():
        raise HTTPException(status_code=410, detail="Share code expired")
    device = db.get(Device, invite.device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    if device.owner_user_id != user.id:
        access = db.scalar(select(DeviceAccess).where(
            DeviceAccess.device_id == device.id,
            DeviceAccess.user_id == user.id,
        ))
        if access:
            access.role = invite.role
        else:
            db.add(DeviceAccess(device_id=device.id, user_id=user.id, role=invite.role))
    if device.owner_user_id != user.id:
        creator = db.get(User, invite.created_by_user_id)
        inherited = allowed_outlets_for(db, creator, device) if creator else []
        initial_outlets = [] if invite.role == "view" else inherited
        mask = sum(1 << (outlet - 1) for outlet in initial_outlets)
        policy = db.scalar(select(OutletPolicy).where(
            OutletPolicy.device_id == device.id,
            OutletPolicy.user_id == user.id,
        ))
        if policy is None:
            db.add(OutletPolicy(device_id=device.id, user_id=user.id, outlet_mask=mask))
        else:
            policy.outlet_mask = mask

    invite.accepted_by_user_id = user.id
    invite.accepted_at = utcnow()
    audit(db, "share_accepted", user.id, device.id, invite.role)
    db.commit()
    effective_role = "owner" if device.owner_user_id == user.id else invite.role
    return device_payload(device, effective_role, allowed_outlets_for(db, user, device))


@app.get(f"{API_PREFIX}/devices/{{mac}}/shares")
def list_shares(
    mac: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    device = device_by_mac(db, mac)
    require_device_role(db, user, device, "admin")
    owner = db.get(User, device.owner_user_id)
    rows = [{
        "user_id": owner.id,
        "email": owner.email,
        "role": "owner",
        "allowed_outlets": [1, 2, 3, 4],
    }] if owner else []
    accesses = list(db.scalars(select(DeviceAccess).where(DeviceAccess.device_id == device.id)))
    for access in accesses:
        account = db.get(User, access.user_id)
        if account:
            rows.append({
                "user_id": account.id,
                "email": account.email,
                "role": access.role,
                "allowed_outlets": allowed_outlets_for(db, account, device),
            })
    return {"shares": rows}


@app.put(f"{API_PREFIX}/devices/{{mac}}/shares/{{target_user_id}}/outlets")
def set_share_outlets(
    mac: str,
    target_user_id: str,
    body: OutletPolicyRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    device = device_by_mac(db, mac)
    actor_role = require_device_role(db, user, device, "admin")
    if target_user_id == device.owner_user_id:
        raise HTTPException(status_code=422, detail="Owner always controls outlets 1..4")

    access = db.scalar(select(DeviceAccess).where(
        DeviceAccess.device_id == device.id,
        DeviceAccess.user_id == target_user_id,
    ))
    if access is None:
        raise HTTPException(status_code=404, detail="Share not found")
    if access.role == "admin" and actor_role != "owner":
        raise HTTPException(status_code=403, detail="Only the owner can change Admin outlet access")

    outlets = sorted(set(int(item) for item in body.outlets))
    if actor_role != "owner":
        actor_allowed = set(allowed_outlets_for(db, user, device))
        if any(item not in actor_allowed for item in outlets):
            raise HTTPException(status_code=403, detail="Admin cannot grant outlets outside their own scope")
    if any(item < 1 or item > 4 for item in outlets):
        raise HTTPException(status_code=422, detail="Outlets must be between 1 and 4")
    if access.role == "view" and outlets:
        raise HTTPException(status_code=422, detail="View role cannot control outlets")

    mask = sum(1 << (outlet - 1) for outlet in outlets)
    policy = db.scalar(select(OutletPolicy).where(
        OutletPolicy.device_id == device.id,
        OutletPolicy.user_id == target_user_id,
    ))
    if policy is None:
        policy = OutletPolicy(device_id=device.id, user_id=target_user_id, outlet_mask=mask)
        db.add(policy)
    else:
        policy.outlet_mask = mask

    audit(
        db,
        "outlet_policy_updated",
        user.id,
        device.id,
        f"target={target_user_id},outlets={','.join(str(item) for item in outlets) or 'none'}",
    )
    db.commit()
    return {"ok": True, "user_id": target_user_id, "allowed_outlets": outlets}


@app.delete(f"{API_PREFIX}/devices/{{mac}}/shares/{{target_user_id}}")
def revoke_share(
    mac: str,
    target_user_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    device = device_by_mac(db, mac)
    actor_role = require_device_role(db, user, device, "admin")
    if target_user_id == device.owner_user_id:
        raise HTTPException(status_code=422, detail="Owner access cannot be revoked")
    access = db.scalar(select(DeviceAccess).where(
        DeviceAccess.device_id == device.id,
        DeviceAccess.user_id == target_user_id,
    ))
    if access is None:
        raise HTTPException(status_code=404, detail="Share not found")
    if access.role == "admin" and actor_role != "owner":
        raise HTTPException(status_code=403, detail="Only the owner can revoke Admin")
    policy = db.scalar(select(OutletPolicy).where(
        OutletPolicy.device_id == device.id,
        OutletPolicy.user_id == target_user_id,
    ))
    if policy is not None:
        db.delete(policy)
    db.delete(access)
    audit(db, "share_revoked", user.id, device.id, target_user_id)
    db.commit()
    return {"ok": True}


@app.post(f"{API_PREFIX}/voice/intent")
def voice_intent(
    body: VoiceIntentRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    # Cloud-side voice command generation is intentionally disabled in
    # zero-trust mode. Voice actions must be converted to individually signed
    # outlet commands on the bound Android installation so a compromised VPS
    # cannot fabricate an executable relay command.
    device = device_by_mac(db, body.mac)
    require_device_role(db, user, device, "control")
    raise HTTPException(
        status_code=428,
        detail="Zero-trust mode requires device-bound signed outlet commands",
    )


@app.post(f"{API_PREFIX}/controllers/{{controller_id}}/heartbeat")
def controller_heartbeat(
    controller_id: str,
    body: HeartbeatRequest,
    x_controller_key: str | None = Header(default=None, alias="X-Controller-Key"),
    db: Session = Depends(get_db),
) -> dict:
    controller = controller_auth(db, controller_id, x_controller_key)
    now = utcnow()
    controller.last_seen = now
    seen_macs: set[str] = set()
    for item in body.devices:
        mac = normalize_mac(item.mac)
        device = db.scalar(select(Device).where(
            Device.controller_id == controller.id,
            Device.mac == mac,
        ))
        if device is None:
            continue
        device.online = bool(item.connected)
        device.last_seen = now
        if item.firmware:
            device.firmware = item.firmware.strip()
        seen_macs.add(mac)
    db.commit()
    return {"ok": True, "accepted_devices": len(seen_macs), "server_time": now.isoformat()}


@app.post(f"{API_PREFIX}/controllers/{{controller_id}}/telemetry")
def controller_telemetry(
    controller_id: str,
    body: TelemetryRequest,
    x_controller_key: str | None = Header(default=None, alias="X-Controller-Key"),
    db: Session = Depends(get_db),
) -> dict:
    controller = controller_auth(db, controller_id, x_controller_key)
    now = utcnow()
    accepted = 0
    for item in body.items:
        mac = normalize_mac(item.mac)
        device = db.scalar(select(Device).where(
            Device.controller_id == controller.id,
            Device.mac == mac,
        ))
        if device is None:
            continue
        device.online = True
        device.last_seen = now
        db.add(TelemetrySnapshot(
            device_id=device.id,
            ts=now,
            power_w=item.power_w,
            energy_kwh=item.energy_kwh,
            max_temp_c=item.max_temp_c,
            relay_mask=item.relay_mask,
            event_code=item.event_code.strip(),
        ))
        accepted += 1
    controller.last_seen = now
    db.commit()
    return {"ok": True, "accepted": accepted}


@app.get(f"{API_PREFIX}/controllers/{{controller_id}}/commands/poll")
def poll_commands(
    controller_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    x_controller_key: str | None = Header(default=None, alias="X-Controller-Key"),
    db: Session = Depends(get_db),
) -> dict:
    controller = controller_auth(db, controller_id, x_controller_key)
    now = utcnow()
    stale_before = now - timedelta(seconds=COMMAND_REDELIVER_SECONDS)

    expired = list(db.scalars(select(Command).where(
        Command.controller_id == controller.id,
        Command.expires_at <= now,
        Command.status.in_(["queued", "delivered"]),
    )))
    for item in expired:
        item.status = "expired"

    commands = list(db.scalars(
        select(Command)
        .where(
            Command.controller_id == controller.id,
            Command.source != "direct-vps",
            Command.expires_at > now,
            Command.attempts < MAX_COMMAND_ATTEMPTS,
            or_(
                Command.status == "queued",
                and_(Command.status == "delivered", Command.delivered_at <= stale_before),
            ),
        )
        .order_by(Command.created_at.asc())
        .limit(limit)
    ))

    payload = []
    for command in commands:
        device = db.get(Device, command.device_id)
        if device is None:
            command.status = "failed"
            command.ack_detail = "device_missing"
            continue
        command.status = "delivered"
        command.delivered_at = now
        command.attempts += 1
        proof = db.scalar(select(CommandProof).where(CommandProof.command_id == command.id))
        if proof is None:
            command.status = "failed"
            command.ack_detail = "missing_device_bound_signature"
            continue
        payload.append({
            "command_id": command.id,
            "mac": device.mac,
            "outlet": command.outlet,
            "state": command.state,
            "source": command.source,
            "attempt": command.attempts,
            "expires_at": command.expires_at.isoformat(),
            "proof": {
                "version": 1,
                "key_id": proof.key_id,
                "nonce": proof.nonce,
                "issued_at": proof.issued_at,
                "valid_until": proof.valid_until,
                "signature": proof.signature_b64,
                "canonical_sha256": proof.canonical_sha256,
            },
        })
    controller.last_seen = now
    db.commit()
    return {"commands": payload, "server_time": now.isoformat()}


@app.post(f"{API_PREFIX}/controllers/{{controller_id}}/commands/{{command_id}}/ack")
def ack_command(
    controller_id: str,
    command_id: str,
    body: AckRequest,
    x_controller_key: str | None = Header(default=None, alias="X-Controller-Key"),
    db: Session = Depends(get_db),
) -> dict:
    controller = controller_auth(db, controller_id, x_controller_key)
    command = db.get(Command, command_id)
    if command is None or command.controller_id != controller.id:
        raise HTTPException(status_code=404, detail="Command not found")
    if command.source == "direct-vps":
        raise HTTPException(status_code=409, detail="Direct commands require device session confirmation")
    if command.status in {"acked", "failed", "expired"}:
        return {"ok": True, "status": command.status}
    command.status = body.status
    command.acked_at = utcnow()
    command.ack_detail = body.detail.strip()
    device = db.get(Device, command.device_id)
    audit(db, "command_" + body.status, command.requested_by_user_id,
          device.id if device else None, body.detail)
    db.commit()
    return {"ok": True, "status": command.status}


@app.get(f"{API_PREFIX}/commands/{{command_id}}")
def command_status(
    command_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    command = db.get(Command, command_id)
    if command is None:
        raise HTTPException(status_code=404, detail="Command not found")
    device = db.get(Device, command.device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    require_device_role(db, user, device, "view")
    expiry = command.expires_at
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    if command.source == "direct-vps" and command.status in {"queued", "sent"} and expiry < utcnow():
        command.status = "timeout"
        command.ack_detail = "request interrupted; physical outcome unknown"
        audit(db, "direct_command_timeout", command.requested_by_user_id, device.id,
              f"source=direct-vps mac={device.mac} outlet={command.outlet} state={command.state} result=timeout")
        db.commit()
    return {
        "command_id": command.id,
        "mac": device.mac,
        "outlet": command.outlet,
        "state": command.state,
        "source": command.source,
        "status": command.status,
        "attempts": command.attempts,
        "detail": command.ack_detail,
    }
