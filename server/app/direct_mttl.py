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
                raw = stream.readline(1048577)
            if len(raw) > 1048576 or not raw.endswith(b"\n"):
                raise ValueError("invalid IPC response")
            return json.loads(raw)

    def status(self, mac):
        return self.status_many([mac])[mac]

    def status_many(self, macs):
        try:
            result = self.request("status", timeout=2)
            sessions = {d['mac']: d for d in result.get('devices', [])}
            return {mac: {**sessions.get(mac, {}), 'connected': bool(sessions.get(mac, {}).get('online', False)),
                          'control_enabled': not result.get('observe_only', True)} for mac in macs}
        except (OSError, ValueError, KeyError, TypeError):
            return {mac: {'connected': False, 'control_enabled': False, 'outlets': []} for mac in macs}

    def control(self, mac, outlet, state):
        if not re.fullmatch(r'[0-9A-F]{12}', mac) or outlet not in (1, 2, 3, 4) or state not in ("on", "off"):
            raise ValueError("invalid direct command")
        return self.request(f"{state} {mac} {outlet}")

    def allow(self, mac):
        if not re.fullmatch(r'[0-9A-F]{12}', mac):
            raise ValueError('invalid MAC')
        result = self.request('allow ' + mac)
        if not result.get('ok'):
            raise ValueError('persistent allow-list unavailable')
        return result

    def allow_many(self, macs):
        if not macs or len(macs) > 256 or any(not re.fullmatch(r'[0-9A-F]{12}', mac) for mac in macs):
            raise ValueError('invalid MAC group')
        result = self.request('allowmany ' + ','.join(sorted(set(macs))))
        if not result.get('ok'):
            raise ValueError('persistent allow-list unavailable')
        return result


adapter = DirectMttlAdapter()
