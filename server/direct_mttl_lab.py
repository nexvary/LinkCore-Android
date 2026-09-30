#!/usr/bin/env python3
"""
NEXVARY direct MTTL-W01 VPS lab.

Experimental, owner-only listener for verifying that a provisioned MTTL-W01 can
connect directly to a public VPS on TCP 10086.

Safety defaults:
- receive/telemetry mode only;
- optional allow-list by MAC;
- no public HTTP control API;
- outlet commands are disabled unless NEXVARY_MTTL_ALLOW_CONTROL=1;
- local control socket is bound to 127.0.0.1 only.

Wire format mirrors the verified Android implementation:
- CRLF-delimited UTF-8/ASCII frames
- boot: up:bootinfo:<model>;<mac>;<clientId>;<firmware>;connect
- poll: up:getinfo:all
- outlet: up:onoff:<1..4>:on|off
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import signal
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

BOOT_RE = re.compile(
    r"^up:bootinfo:([^;\r\n]{1,32});([0-9A-Fa-f]{12});"
    r"([0-9A-Fa-f]{12});([^;\r\n]{1,64});connect$"
)
ONOFF_RE = re.compile(r"^up:(?:event:)?onoff:([1-4]):(on|off)$", re.I)
GET_INFO = "up:getinfo:all"
MAX_FRAME = 64 * 1024


def normalize_mac(value: str) -> str:
    return re.sub(r"[^0-9A-Fa-f]", "", value or "").upper()


def normalize_wire_frame(value: str) -> str:
    """Discard only line/NUL delimiters at frame boundaries.

    NUL is not removed by str.strip(), and journald splits logs at NUL,
    which otherwise makes a prefixed getinfo look valid in journal output.
    Keep interior bytes intact rather than repairing malformed identities.
    """
    return value.strip("\x00 \t\r\n")


@dataclass
class Device:
    model: str
    mac: str
    firmware: str
    peer: str
    writer: asyncio.StreamWriter
    connected_at: float
    last_seen: float
    outlets: dict = field(default_factory=dict)
    pending: dict = field(default_factory=dict)
    last_command: float = 0


class DirectMttlLab:
    def __init__(
        self,
        host: str,
        port: int,
        allowed_mac: str,
        expected_model: str,
        poll_seconds: int,
        admin_host: str,
        admin_port: int,
        allow_control: bool,
    ) -> None:
        self.host = host
        self.port = port
        self.allowed_mac = normalize_mac(allowed_mac)
        self.allowed_macs = {normalize_mac(v) for v in allowed_mac.split(',') if v.strip()}
        if any(not re.fullmatch(r'[0-9A-F]{12}', v) for v in self.allowed_macs):
            raise ValueError('invalid MAC allow-list')
        self.allowlist_file = os.getenv('NEXVARY_MTTL_ALLOWED_MACS_FILE', '')
        self.managed_registry = os.getenv('NEXVARY_MTTL_MANAGED_REGISTRY', '0') == '1'
        if self.managed_registry and not self.allowlist_file:
            raise ValueError('managed registry requires persistent allow-list')
        if self.allowlist_file and Path(self.allowlist_file).exists():
            saved = json.loads(Path(self.allowlist_file).read_text())
            if not isinstance(saved, list) or any(
                    not isinstance(v, str) or not re.fullmatch(r'[0-9A-F]{12}', v) for v in saved):
                raise ValueError('invalid persisted MAC allow-list')
            self.allowed_macs.update(saved)
        self.expected_model = expected_model.strip().lower()
        self.poll_seconds = max(5, poll_seconds)
        if admin_host != "127.0.0.1":
            raise ValueError("admin interface must remain loopback-only")
        self.admin_host = admin_host
        self.admin_port = admin_port
        if allow_control and not self.allowed_macs and not self.managed_registry:
            raise ValueError("control requires an explicit MAC allow-list")
        self.allow_control = allow_control
        self.command_timeout = 8.0
        self.devices: Dict[str, Device] = {}
        self._server: Optional[asyncio.AbstractServer] = None
        self._admin_server: Optional[asyncio.AbstractServer] = None
        self._unix_server: Optional[asyncio.AbstractServer] = None
        self._poll_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        self._server = await asyncio.start_server(
            self.handle_device,
            self.host,
            self.port,
            limit=MAX_FRAME + 4096,
        )
        self._admin_server = await asyncio.start_server(
            self.handle_admin,
            self.admin_host,
            self.admin_port,
        )
        unix_path = os.getenv("NEXVARY_MTTL_ADMIN_SOCKET", "")
        if unix_path:
            self._unix_server = await asyncio.start_unix_server(self.handle_admin, path=unix_path)
            os.chmod(unix_path, 0o660)
        self._poll_task = asyncio.create_task(self.poll_loop())
        logging.info(
            "listener_ready bind=%s:%s admin=%s:%s observe_only=%s allowed_mac=%s",
            self.host,
            self.port,
            self.admin_host,
            self.admin_port,
            not self.allow_control,
            self.allowed_mac or "ANY_BOOTSTRAP",
        )

    async def stop(self) -> None:
        if self._poll_task:
            self._poll_task.cancel()
        for device in list(self.devices.values()):
            self.fail_pending(device)
            device.writer.close()
        self.devices.clear()
        for server in (self._admin_server, self._unix_server, self._server):
            if server is not None:
                server.close()
                await server.wait_closed()

    async def poll_loop(self) -> None:
        while True:
            await asyncio.sleep(self.poll_seconds)
            for device in list(self.devices.values()):
                try:
                    await self.send(device, GET_INFO)
                except Exception as exc:
                    logging.warning("poll_failed mac=%s error=%s", device.mac, exc)

    async def send(self, device: Device, command: str) -> None:
        device.writer.write((command + "\r\n").encode("utf-8"))
        await asyncio.wait_for(device.writer.drain(), timeout=5)

    async def handle_device(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        peer_raw = writer.get_extra_info("peername")
        peer = str(peer_raw)
        identified_mac: Optional[str] = None
        pending = ""
        logging.info("tcp_connected peer=%s", peer)

        try:
            while True:
                raw = await asyncio.wait_for(reader.readline(), timeout=90 if identified_mac else 15)
                if not raw:
                    break
                if len(raw) > MAX_FRAME:
                    raise ValueError("frame too large")
                decoded = raw.decode("utf-8", errors="strict")
                line = normalize_wire_frame(decoded)
                if line and line != decoded.strip():
                    logging.info("wire_envelope peer=%s raw=%r", peer, decoded[:2048])
                if not line:
                    continue

                if pending and line.startswith("up:"):
                    pending = ""
                frame = pending + line if pending else line
                if frame.startswith("up:getinfo:") and parse_getinfo(frame) is None:
                    pending = frame
                    if len(pending) > MAX_FRAME:
                        raise ValueError("getinfo frame too large")
                    continue
                pending = ""

                boot = BOOT_RE.fullmatch(frame)
                if boot:
                    model, mac, client_id, firmware = boot.groups()
                    mac = mac.upper()
                    client_id = client_id.upper()
                    if mac != client_id:
                        raise ValueError("boot MAC/clientId mismatch")
                    if self.expected_model and model.lower() != self.expected_model:
                        raise ValueError(f"unexpected model {model!r}")
                    if (self.managed_registry or self.allowed_macs) and mac not in self.allowed_macs:
                        logging.warning("rejected_mac peer=%s mac=%s", peer, mac)
                        break

                    old = self.devices.get(mac)
                    if identified_mac and identified_mac != mac:
                        raise ValueError("session identity cannot change")
                    if old and old.writer is not writer:
                        self.fail_pending(old)
                        old.writer.close()

                    identified_mac = mac
                    self.devices[mac] = Device(
                        model=model,
                        mac=mac,
                        firmware=firmware,
                        peer=peer,
                        writer=writer,
                        connected_at=time.time(),
                        last_seen=time.time(),
                    )
                    logging.info(
                        "device_online mac=%s model=%s firmware=%s peer=%s",
                        mac,
                        model,
                        firmware,
                        peer,
                    )
                    await self.send(self.devices[mac], GET_INFO)
                    continue

                if not identified_mac:
                    logging.info("pre_identity_frame peer=%s frame=%r", peer, frame[:256])
                    continue

                device = self.devices.get(identified_mac)
                if not device or device.writer is not writer:
                    break
                device.last_seen = time.time()

                telemetry = parse_getinfo(frame)
                if telemetry is not None:
                    for item in telemetry:
                        self.observe(device, item["channel"], item)
                    logging.info(
                        "telemetry mac=%s data=%s",
                        identified_mac,
                        json.dumps(telemetry, separators=(",", ":"), ensure_ascii=False),
                    )
                    continue

                state = ONOFF_RE.fullmatch(frame)
                if state:
                    self.observe(device, int(state.group(1)), {"relay": state.group(2).lower()})
                    logging.info(
                        "outlet_event mac=%s outlet=%s state=%s",
                        identified_mac,
                        state.group(1),
                        state.group(2).lower(),
                    )
                    continue

                logging.info("protocol_frame mac=%s frame=%r", identified_mac, frame[:2048])
        except (UnicodeDecodeError, ValueError, ConnectionError, asyncio.IncompleteReadError, asyncio.TimeoutError) as exc:
            logging.warning("device_connection_error peer=%s error=%s", peer, exc)
        finally:
            if identified_mac:
                current = self.devices.get(identified_mac)
                if current and current.writer is writer:
                    self.fail_pending(current)
                    self.devices.pop(identified_mac, None)
                    logging.info("device_offline mac=%s peer=%s", identified_mac, peer)
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    def observe(self, device, outlet, values):
        current = device.outlets.setdefault(outlet, {"channel": outlet})
        current.update(values)
        pending = device.pending.get(outlet)
        if pending and values.get("relay") == pending[0] and not pending[1].done():
            pending[1].set_result(True)

    def fail_pending(self, device):
        for _, future in device.pending.values():
            if not future.done():
                future.set_exception(ConnectionError("device disconnected"))

    async def handle_admin(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        # Loopback-only maintenance interface. Never bind this publicly.
        try:
            raw = await asyncio.wait_for(reader.readline(), timeout=10)
            command = raw.decode("utf-8", errors="strict").strip()
            response = await self.admin_command(command)
        except Exception as exc:
            response = {"ok": False, "error": str(exc)}
        writer.write((json.dumps(response, ensure_ascii=False) + "\n").encode("utf-8"))
        await writer.drain()
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass

    async def admin_command(self, command: str) -> dict:
        parts = command.split()
        if not parts or parts[0] == "status":
            return {
                "ok": True,
                "observe_only": not self.allow_control,
                "allowed_macs": sorted(self.allowed_macs),
                "devices": [
                    {
                        "mac": d.mac,
                        "model": d.model,
                        "firmware": d.firmware,
                        "peer": d.peer,
                        "last_seen": d.last_seen,
                        "connected_at": d.connected_at,
                        "online": time.time() - d.last_seen < 90,
                        "outlets": list(d.outlets.values()),
                        "pending_outlets": list(d.pending),
                    }
                    for d in self.devices.values()
                ],
            }

        if parts[0] in ('allow', 'allowmany') and len(parts) == 2:
            mac = parts[1].upper()
            additions = set(mac.split(',')) if parts[0] == 'allowmany' else {mac}
            if any(not re.fullmatch(r'[0-9A-F]{12}', value) for value in additions):
                return {'ok': False, 'error': 'invalid MAC'}
            if not self.allowlist_file:
                return {'ok': False, 'error': 'persistent allow-list is not configured'}
            proposed = self.allowed_macs | additions
            path = Path(self.allowlist_file)
            temporary = path.with_suffix('.tmp')
            temporary.write_text(json.dumps(sorted(proposed)))
            temporary.chmod(0o600)
            temporary.replace(path)
            self.allowed_macs = proposed
            return {'ok': True, 'mac': mac} if parts[0] == 'allow' else {'ok': True, 'macs': sorted(additions)}

        if parts[0] == "refresh" and len(parts) == 2:
            mac = normalize_mac(parts[1])
            device = self.devices.get(mac)
            if not device:
                return {"ok": False, "error": "device offline"}
            await self.send(device, GET_INFO)
            return {"ok": True}

        if parts[0] in {"on", "off"} and len(parts) == 3:
            if not self.allow_control:
                return {"ok": False, "error": "control disabled; set NEXVARY_MTTL_ALLOW_CONTROL=1"}
            mac = normalize_mac(parts[1])
            try:
                outlet = int(parts[2])
            except ValueError:
                return {"ok": False, "error": "outlet must be 1..4"}
            if outlet not in (1, 2, 3, 4):
                return {"ok": False, "error": "outlet must be 1..4"}
            device = self.devices.get(mac)
            if not device:
                return {"ok": False, "error": "device offline"}
            if mac not in self.allowed_macs:
                return {"ok": False, "status": "failed", "error": "MAC not allow-listed"}
            if device.pending or time.monotonic() - device.last_command < 1:
                return {"ok": False, "status": "failed", "error": "command rate limited or busy"}
            future = asyncio.get_running_loop().create_future()
            device.pending[outlet] = (parts[0], future)
            device.last_command = time.monotonic()
            try:
                await self.send(device, f"up:onoff:{outlet}:{parts[0]}")
                await asyncio.wait_for(future, self.command_timeout)
                return {"ok": True, "status": "confirmed"}
            except asyncio.TimeoutError:
                return {"ok": False, "status": "timeout", "error": "no fresh device confirmation"}
            except ConnectionError:
                return {"ok": False, "status": "failed", "error": "device disconnected"}
            finally:
                device.pending.pop(outlet, None)

        return {"ok": False, "error": "commands: status | refresh MAC | on MAC 1..4 | off MAC 1..4"}


def parse_getinfo(frame: str):
    """Parse live MTTL getinfo frames without assuming every firmware has
    exactly the same total field width.

    Each outlet block is introduced by :<channel>: and its payload is
    semicolon-delimited. We parse any well-formed channel block present and
    require all four channels only when the frame actually advertises them.
    """
    prefix = "up:getinfo:"
    if frame is None:
        return None
    frame = normalize_wire_frame(frame)
    if not frame.startswith(prefix):
        return None

    payload = frame[len(prefix):]
    matches = list(re.finditer(r"(?:^|:)([1-4]):(.*?)(?=:[1-4]:|$)", payload))
    if not matches:
        return None

    outlets = []
    seen = set()
    for match in matches:
        channel = int(match.group(1))
        if channel in seen:
            return None

        fields = match.group(2).rstrip(":").split(";")
        # Verified fields used by FG Link:
        # 0 test, 1 relay, 2 fixed, 3 overload, 4 overheat,
        # 5 power, 6 energy, 7 previous energy, 8 config,
        # 9 device status, 10 event code, 11 temperature.
        if len(fields) < 2:
            continue
        fields = fields[:12]

        relay = fields[1].lower()
        if relay not in {"on", "off"}:
            continue
        def numeric(index, base=10):
            try:
                return int(fields[index], base)
            except (IndexError, ValueError):
                return None
        power_raw = numeric(5)
        energy_wh = numeric(6, 16)
        temperature_c = numeric(11)
        def optional(index):
            return fields[index] if len(fields) > index else None

        outlets.append(
            {
                "channel": channel,
                "relay": relay,
                "power_w": power_raw / 1000.0 if power_raw is not None else None,
                "energy_wh": energy_wh,
                "temperature_c": temperature_c,
                "event_code": (optional(10) or "").upper(),
                "overload": optional(3),
                "overheat": optional(4),
                "device_status": optional(9),
            }
        )
        seen.add(channel)

    # A live response may be split or firmware-specific; one valid outlet block
    # is enough to classify the frame as telemetry. The next poll fills the rest.
    return sorted(outlets, key=lambda item: item["channel"]) if outlets else None


async def amain(args) -> None:
    lab = DirectMttlLab(
        host=args.host,
        port=args.port,
        allowed_mac=os.getenv("NEXVARY_MTTL_ALLOWED_MAC", ""),
        expected_model=os.getenv("NEXVARY_MTTL_EXPECTED_MODEL", "lgutap"),
        poll_seconds=int(os.getenv("NEXVARY_MTTL_POLL_SECONDS", "10")),
        admin_host="127.0.0.1",
        admin_port=int(os.getenv("NEXVARY_MTTL_ADMIN_PORT", "18087")),
        allow_control=os.getenv("NEXVARY_MTTL_ALLOW_CONTROL", "0") == "1",
    )
    await lab.start()

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    await stop_event.wait()
    await lab.stop()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=10086)
    parser.add_argument("--log-level", default=os.getenv("NEXVARY_MTTL_LOG_LEVEL", "INFO"))
    args = parser.parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    asyncio.run(amain(args))


if __name__ == "__main__":
    main()
