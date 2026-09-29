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
from dataclasses import dataclass
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


@dataclass
class Device:
    model: str
    mac: str
    firmware: str
    peer: str
    writer: asyncio.StreamWriter
    connected_at: float
    last_seen: float


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
        self.expected_model = expected_model.strip().lower()
        self.poll_seconds = max(5, poll_seconds)
        self.admin_host = admin_host
        self.admin_port = admin_port
        self.allow_control = allow_control
        self.devices: Dict[str, Device] = {}
        self._server: Optional[asyncio.AbstractServer] = None
        self._admin_server: Optional[asyncio.AbstractServer] = None
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
            device.writer.close()
        self.devices.clear()
        for server in (self._admin_server, self._server):
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
        await device.writer.drain()

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
                raw = await reader.readline()
                if not raw:
                    break
                if len(raw) > MAX_FRAME:
                    raise ValueError("frame too large")
                line = raw.decode("utf-8", errors="strict").strip()
                if not line:
                    continue

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
                    if self.allowed_mac and mac != self.allowed_mac:
                        logging.warning("rejected_mac peer=%s mac=%s", peer, mac)
                        break

                    old = self.devices.get(mac)
                    if old and old.writer is not writer:
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
                    logging.info("pre_identity_frame peer=%s frame=%s", peer, frame[:256])
                    continue

                device = self.devices.get(identified_mac)
                if device:
                    device.last_seen = time.time()

                telemetry = parse_getinfo(frame)
                if telemetry is not None:
                    logging.info(
                        "telemetry mac=%s data=%s",
                        identified_mac,
                        json.dumps(telemetry, separators=(",", ":"), ensure_ascii=False),
                    )
                    continue

                state = ONOFF_RE.fullmatch(frame)
                if state:
                    logging.info(
                        "outlet_event mac=%s outlet=%s state=%s",
                        identified_mac,
                        state.group(1),
                        state.group(2).lower(),
                    )
                    continue

                logging.info("protocol_frame mac=%s frame=%s", identified_mac, frame[:2048])
        except (UnicodeDecodeError, ValueError, ConnectionError, asyncio.IncompleteReadError) as exc:
            logging.warning("device_connection_error peer=%s error=%s", peer, exc)
        finally:
            if identified_mac:
                current = self.devices.get(identified_mac)
                if current and current.writer is writer:
                    self.devices.pop(identified_mac, None)
                    logging.info("device_offline mac=%s peer=%s", identified_mac, peer)
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

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
                "devices": [
                    {
                        "mac": d.mac,
                        "model": d.model,
                        "firmware": d.firmware,
                        "peer": d.peer,
                        "last_seen": int(d.last_seen),
                    }
                    for d in self.devices.values()
                ],
            }

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
            await self.send(device, f"up:onoff:{outlet}:{parts[0]}")
            return {"ok": True}

        return {"ok": False, "error": "commands: status | refresh MAC | on MAC 1..4 | off MAC 1..4"}


def parse_getinfo(frame: str):
    prefix = "up:getinfo:"
    if not frame.startswith(prefix):
        return None
    parts = frame[len(prefix):].split(":")
    if len(parts) != 8:
        return None

    outlets = []
    seen = set()
    for offset in range(0, 8, 2):
        try:
            channel = int(parts[offset])
        except ValueError:
            return None
        if channel not in (1, 2, 3, 4) or channel in seen:
            return None
        fields = parts[offset + 1].split(";")
        if len(fields) != 12:
            return None
        if fields[1].lower() not in {"on", "off"}:
            return None
        try:
            power_raw = int(fields[5])
            energy_wh = int(fields[6], 16)
            temperature_c = int(fields[11])
        except ValueError:
            return None
        outlets.append(
            {
                "channel": channel,
                "relay": fields[1].lower(),
                "power_w": power_raw / 1000.0,
                "energy_wh": energy_wh,
                "temperature_c": temperature_c,
                "event_code": fields[10].upper(),
            }
        )
        seen.add(channel)
    return sorted(outlets, key=lambda item: item["channel"])


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
