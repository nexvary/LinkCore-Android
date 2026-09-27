import base64
import hashlib
import os
import secrets
import time
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

TEST_DB = Path("server/tests/fgrck_test.db")
if TEST_DB.exists():
    TEST_DB.unlink()

os.environ["FGRCK_ENV"] = "test"
os.environ["FGRCK_DATABASE_URL"] = "sqlite+pysqlite:///./server/tests/fgrck_test.db"
os.environ["FGRCK_JWT_SECRET"] = "test-jwt-secret-that-is-long-enough-for-tests"
os.environ["FGRCK_TOKEN_PEPPER"] = "test-token-pepper-that-is-long-enough-for-tests"
os.environ["FGRCK_COMMAND_TTL_SECONDS"] = "180"

from fastapi.testclient import TestClient

from app.main import app


def register(client, email, password="CorrectHorseBattery1!"):
    response = client.post("/api/v1/auth/register", json={"email": email, "password": password})
    assert response.status_code == 201, response.text
    return response.json()


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def bind_phone(client, account, controller_id):
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_der = private_key.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    key_id = hashlib.sha256(public_der).hexdigest()
    response = client.put(
        f"/api/v1/controllers/{controller_id}/device-binding",
        json={
            "key_id": key_id,
            "public_key_b64": base64.b64encode(public_der).decode(),
            "label": "Test Android",
            "hardware_backed": True,
        },
        headers=auth(account["access_token"]),
    )
    assert response.status_code == 200, response.text
    return private_key, key_id


def signed_headers(private_key, key_id, controller_id, mac, outlet, state,
                   issued_at=None, valid_until=None, nonce=None):
    issued_at = int(time.time()) if issued_at is None else int(issued_at)
    valid_until = issued_at + 90 if valid_until is None else int(valid_until)
    nonce = nonce or secrets.token_urlsafe(24)
    normalized_mac = "".join(ch for ch in mac.upper() if ch in "0123456789ABCDEF")
    canonical = "\n".join([
        "FGLINK-CMD-V1",
        controller_id,
        normalized_mac,
        str(outlet),
        state.lower(),
        str(issued_at),
        str(valid_until),
        nonce,
        key_id.lower(),
    ])
    signature = private_key.sign(canonical.encode(), ec.ECDSA(hashes.SHA256()))
    return {
        "X-FG-Key-Id": key_id,
        "X-FG-Nonce": nonce,
        "X-FG-Issued-At": str(issued_at),
        "X-FG-Valid-Until": str(valid_until),
        "X-FG-Signature": base64.b64encode(signature).decode(),
    }


def signed_post(client, account, private_key, key_id, controller_id, mac, outlet, state,
                nonce=None):
    headers = auth(account["access_token"])
    headers.update(signed_headers(
        private_key, key_id, controller_id, mac, outlet, state, nonce=nonce))
    return client.post(
        f"/api/v1/devices/{mac}/outlets/{outlet}?state={state}",
        headers=headers,
    )


def test_account_sharing_controller_relay_and_voice_flow():
    with TestClient(app) as client:
        owner = register(client, "owner@example.com")
        guest = register(client, "guest@example.com")
        viewer = register(client, "viewer@example.com")

        controller = client.post(
            "/api/v1/controllers",
            json={"name": "Home Android Controller"},
            headers=auth(owner["access_token"]),
        )
        assert controller.status_code == 201, controller.text
        controller_id = controller.json()["controller_id"]
        controller_key = controller.json()["controller_key"]
        controller_headers = {"X-Controller-Key": controller_key}
        owner_private, owner_key_id = bind_phone(client, owner, controller_id)

        device = client.post(
            "/api/v1/devices",
            json={
                "controller_id": controller_id,
                "mac": "AA:BB:CC:DD:EE:FF",
                "name": "Living Room Strip",
                "room": "Living Room",
                "firmware": "1.0.110",
            },
            headers=auth(owner["access_token"]),
        )
        assert device.status_code == 201, device.text
        assert device.json()["mac"] == "AABBCCDDEEFF"

        heartbeat = client.post(
            f"/api/v1/controllers/{controller_id}/heartbeat",
            json={"devices": [{"mac": "AABBCCDDEEFF", "connected": True, "firmware": "1.0.110"}]},
            headers=controller_headers,
        )
        assert heartbeat.status_code == 200, heartbeat.text

        listed = client.get("/api/v1/devices", headers=auth(owner["access_token"]))
        assert listed.status_code == 200
        assert listed.json()["devices"][0]["connected"] is True

        invite = client.post(
            "/api/v1/devices/AABBCCDDEEFF/shares/invites",
            json={"role": "control", "expires_hours": 24},
            headers=auth(owner["access_token"]),
        )
        assert invite.status_code == 201, invite.text
        share_code = invite.json()["code"]
        assert share_code.startswith("fgrck_share_")

        accepted = client.post(
            "/api/v1/shares/accept",
            json={"code": share_code},
            headers=auth(guest["access_token"]),
        )
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["role"] == "control"

        viewer_invite = client.post(
            "/api/v1/devices/AABBCCDDEEFF/shares/invites",
            json={"role": "view", "expires_hours": 24},
            headers=auth(owner["access_token"]),
        )
        viewer_accept = client.post(
            "/api/v1/shares/accept",
            json={"code": viewer_invite.json()["code"]},
            headers=auth(viewer["access_token"]),
        )
        assert viewer_accept.status_code == 200

        denied = client.post(
            "/api/v1/devices/AABBCCDDEEFF/outlets/1?state=on",
            headers=auth(viewer["access_token"]),
        )
        assert denied.status_code == 403

        unsigned_guest = client.post(
            "/api/v1/devices/AABBCCDDEEFF/outlets/2?state=on",
            headers=auth(guest["access_token"]),
        )
        assert unsigned_guest.status_code == 428

        queued = signed_post(
            client, owner, owner_private, owner_key_id,
            controller_id, "AABBCCDDEEFF", 2, "on",
        )
        assert queued.status_code == 200, queued.text
        assert queued.json()["zero_trust"] is True
        command_id = queued.json()["command_id"]

        poll = client.get(
            f"/api/v1/controllers/{controller_id}/commands/poll",
            headers=controller_headers,
        )
        assert poll.status_code == 200, poll.text
        commands = poll.json()["commands"]
        assert any(item["command_id"] == command_id and item["outlet"] == 2 and item["state"] == "on"
                   for item in commands)

        ack = client.post(
            f"/api/v1/controllers/{controller_id}/commands/{command_id}/ack",
            json={"status": "acked", "detail": "MTTL command sent locally"},
            headers=controller_headers,
        )
        assert ack.status_code == 200
        assert ack.json()["status"] == "acked"

        status_response = client.get(
            f"/api/v1/commands/{command_id}",
            headers=auth(owner["access_token"]),
        )
        assert status_response.status_code == 200
        assert status_response.json()["status"] == "acked"

        telemetry = client.post(
            f"/api/v1/controllers/{controller_id}/telemetry",
            json={"items": [{
                "mac": "AABBCCDDEEFF",
                "power_w": 123.4,
                "energy_kwh": 4.5,
                "max_temp_c": 31,
                "relay_mask": 2,
                "event_code": "00",
            }]},
            headers=controller_headers,
        )
        assert telemetry.status_code == 200
        assert telemetry.json()["accepted"] == 1

        history = client.get(
            "/api/v1/history/AABBCCDDEEFF?hours=24",
            headers=auth(viewer["access_token"]),
        )
        assert history.status_code == 200
        assert history.json()["samples"][-1]["power_w"] == 123.4

        voice = client.post(
            "/api/v1/voice/intent",
            json={"mac": "AABBCCDDEEFF", "action": "off", "all_outlets": True},
            headers=auth(owner["access_token"]),
        )
        assert voice.status_code == 428
        assert "device-bound" in voice.json()["detail"]


def test_only_owner_can_grant_admin():
    with TestClient(app) as client:
        owner = register(client, "owner2@example.com")
        admin = register(client, "admin2@example.com")
        controller = client.post(
            "/api/v1/controllers",
            json={"name": "Controller 2"},
            headers=auth(owner["access_token"]),
        ).json()
        client.post(
            "/api/v1/devices",
            json={
                "controller_id": controller["controller_id"],
                "mac": "112233445566",
                "name": "Strip 2",
            },
            headers=auth(owner["access_token"]),
        )
        invite = client.post(
            "/api/v1/devices/112233445566/shares/invites",
            json={"role": "admin", "expires_hours": 24},
            headers=auth(owner["access_token"]),
        )
        assert invite.status_code == 201
        accepted = client.post(
            "/api/v1/shares/accept",
            json={"code": invite.json()["code"]},
            headers=auth(admin["access_token"]),
        )
        assert accepted.status_code == 200

        denied = client.post(
            "/api/v1/devices/112233445566/shares/invites",
            json={"role": "admin", "expires_hours": 24},
            headers=auth(admin["access_token"]),
        )
        assert denied.status_code == 403


def test_email_alert_targets_authenticated_account(monkeypatch):
    import app.main as main_module

    captured = {}

    def fake_deliver(recipient, subject, body):
        captured["recipient"] = recipient
        captured["subject"] = subject
        captured["body"] = body

    monkeypatch.setattr(main_module, "deliver_alert_email", fake_deliver)

    with TestClient(app) as client:
        account = register(client, "alerts@example.com")
        response = client.post(
            "/api/v1/alerts/email",
            json={"subject": "FG Link alert", "body": "MTTL-W01 offline"},
            headers=auth(account["access_token"]),
        )
        assert response.status_code == 200, response.text
        assert response.json()["recipient"] == "alerts@example.com"
        assert captured == {
            "recipient": "alerts@example.com",
            "subject": "FG Link alert",
            "body": "MTTL-W01 offline",
        }


def test_per_subscriber_outlet_split_and_panel():
    with TestClient(app) as client:
        panel = client.get("/panel")
        assert panel.status_code == 200
        assert "FG Machines Link" in panel.text
        assert "Operations Console" in panel.text
        assert "إدارة أجهزة FG Link" in panel.text

        owner = register(client, "split-owner@example.com")
        guest = register(client, "split-guest@example.com")

        controller = client.post(
            "/api/v1/controllers",
            json={"name": "Split Controller"},
            headers=auth(owner["access_token"]),
        )
        assert controller.status_code == 201, controller.text
        controller_id = controller.json()["controller_id"]
        owner_private, owner_key_id = bind_phone(client, owner, controller_id)

        listed_controllers = client.get(
            "/api/v1/controllers",
            headers=auth(owner["access_token"]),
        )
        assert listed_controllers.status_code == 200
        assert listed_controllers.json()["controllers"][0]["controller_id"] == controller_id

        device = client.post(
            "/api/v1/devices",
            json={
                "controller_id": controller_id,
                "mac": "A1:B2:C3:D4:E5:F6",
                "name": "Split Strip",
                "room": "Two Subscribers",
            },
            headers=auth(owner["access_token"]),
        )
        assert device.status_code == 201, device.text
        assert device.json()["allowed_outlets"] == [1, 2, 3, 4]

        invite = client.post(
            "/api/v1/devices/A1B2C3D4E5F6/shares/invites",
            json={"role": "control", "expires_hours": 24},
            headers=auth(owner["access_token"]),
        )
        accepted = client.post(
            "/api/v1/shares/accept",
            json={"code": invite.json()["code"]},
            headers=auth(guest["access_token"]),
        )
        assert accepted.status_code == 200

        guest_id = guest["user_id"]
        policy = client.put(
            f"/api/v1/devices/A1B2C3D4E5F6/shares/{guest_id}/outlets",
            json={"outlets": [1, 2]},
            headers=auth(owner["access_token"]),
        )
        assert policy.status_code == 200, policy.text
        assert policy.json()["allowed_outlets"] == [1, 2]

        guest_devices = client.get(
            "/api/v1/devices",
            headers=auth(guest["access_token"]),
        )
        assert guest_devices.status_code == 200
        assert guest_devices.json()["devices"][0]["allowed_outlets"] == [1, 2]

        unsigned_allowed = client.post(
            "/api/v1/devices/A1B2C3D4E5F6/outlets/2?state=on",
            headers=auth(guest["access_token"]),
        )
        assert unsigned_allowed.status_code == 428

        denied = client.post(
            "/api/v1/devices/A1B2C3D4E5F6/outlets/3?state=on",
            headers=auth(guest["access_token"]),
        )
        # Zero-trust signature precondition is evaluated before a command is
        # accepted into the relay queue, so unsigned commands never reach the
        # outlet authorization stage.
        assert denied.status_code == 428

        signed_owner = signed_post(
            client, owner, owner_private, owner_key_id,
            controller_id, "A1B2C3D4E5F6", 2, "off",
        )
        assert signed_owner.status_code == 200, signed_owner.text

        shares = client.get(
            "/api/v1/devices/A1B2C3D4E5F6/shares",
            headers=auth(owner["access_token"]),
        )
        assert shares.status_code == 200
        guest_row = next(item for item in shares.json()["shares"] if item["user_id"] == guest_id)
        assert guest_row["allowed_outlets"] == [1, 2]

        owner_still_controls_3 = signed_post(
            client, owner, owner_private, owner_key_id,
            controller_id, "A1B2C3D4E5F6", 3, "off",
        )
        assert owner_still_controls_3.status_code == 200


def test_zero_trust_rejects_forged_signature_and_replay():
    with TestClient(app) as client:
        owner = register(client, "zt-owner@example.com")
        controller = client.post(
            "/api/v1/controllers",
            json={"name": "ZT Controller"},
            headers=auth(owner["access_token"]),
        ).json()
        controller_id = controller["controller_id"]
        private_key, key_id = bind_phone(client, owner, controller_id)

        device = client.post(
            "/api/v1/devices",
            json={
                "controller_id": controller_id,
                "mac": "0A0B0C0D0E0F",
                "name": "Must not persist",
                "room": "Must not persist",
            },
            headers=auth(owner["access_token"]),
        )
        assert device.status_code == 201
        assert device.json()["name"] == ""
        assert device.json()["room"] == ""

        missing = client.post(
            "/api/v1/devices/0A0B0C0D0E0F/outlets/1?state=on",
            headers=auth(owner["access_token"]),
        )
        assert missing.status_code == 428

        attacker = ec.generate_private_key(ec.SECP256R1())
        forged_headers = auth(owner["access_token"])
        forged_headers.update(signed_headers(
            attacker, key_id, controller_id, "0A0B0C0D0E0F", 1, "on"))
        forged = client.post(
            "/api/v1/devices/0A0B0C0D0E0F/outlets/1?state=on",
            headers=forged_headers,
        )
        assert forged.status_code == 401

        nonce = secrets.token_urlsafe(24)
        first = signed_post(
            client, owner, private_key, key_id,
            controller_id, "0A0B0C0D0E0F", 1, "on", nonce=nonce,
        )
        assert first.status_code == 200

        replay = signed_post(
            client, owner, private_key, key_id,
            controller_id, "0A0B0C0D0E0F", 1, "on", nonce=nonce,
        )
        assert replay.status_code == 409

        poll = client.get(
            f"/api/v1/controllers/{controller_id}/commands/poll",
            headers={"X-Controller-Key": controller["controller_key"]},
        )
        assert poll.status_code == 200
        command = next(
            item for item in poll.json()["commands"]
            if item["command_id"] == first.json()["command_id"]
        )
        assert command["proof"]["key_id"] == key_id
        assert command["proof"]["nonce"] == nonce
        assert command["proof"]["signature"]
