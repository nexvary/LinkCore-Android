"""Bounded loopback IPC; the Cloud API never writes raw device frames."""
import json
import os
import re
import socket


def direct_macs():
    return {v.upper() for v in os.getenv("FGRCK_DIRECT_MTTL_MACS", "").split(",")
            if re.fullmatch(r"[0-9a-fA-F]{12}", v)}


class DirectMttlAdapter:
    def request(self, command, timeout=12):
        port = int(os.getenv("FGRCK_DIRECT_MTTL_ADMIN_PORT", "18087"))
        unix_path = os.getenv("FGRCK_DIRECT_MTTL_SOCKET", "")
        if unix_path:
            connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            connection.settimeout(timeout)
            try:
                connection.connect(unix_path)
            except OSError:
                connection.close()
                raise
        else:
            connection = socket.create_connection(("127.0.0.1", port), timeout=timeout)
        with connection as sock:
            sock.settimeout(timeout)
            sock.sendall((command + "\n").encode("ascii"))
            with sock.makefile("rb") as stream:
                raw = stream.readline(65537)
            if len(raw) > 65536 or not raw.endswith(b"\n"):
                raise ValueError("invalid IPC response")
            return json.loads(raw)

    def status(self, mac):
        try:
            result = self.request("status", timeout=2)
            session = next((d for d in result.get("devices", []) if d["mac"] == mac), {})
            return {**session, "connected": bool(session.get("online", False)),
                    "control_enabled": not result.get("observe_only", True)}
        except (OSError, ValueError, KeyError):
            return {"connected": False, "control_enabled": False, "outlets": []}

    def control(self, mac, outlet, state):
        if mac not in direct_macs() or outlet not in (1, 2, 3, 4) or state not in ("on", "off"):
            raise ValueError("invalid direct command")
        return self.request(f"{state} {mac} {outlet}")


adapter = DirectMttlAdapter()
