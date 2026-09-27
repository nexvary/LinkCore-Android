import os
from pathlib import Path

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

        queued = client.post(
            "/api/v1/devices/AABBCCDDEEFF/outlets/2?state=on",
            headers=auth(guest["access_token"]),
        )
        assert queued.status_code == 200, queued.text
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
            headers=auth(guest["access_token"]),
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
            headers=auth(guest["access_token"]),
        )
        assert voice.status_code == 200
        assert len(voice.json()["command_ids"]) == 4

        unsafe_all_on = client.post(
            "/api/v1/voice/intent",
            json={"mac": "AABBCCDDEEFF", "action": "on", "all_outlets": True},
            headers=auth(guest["access_token"]),
        )
        assert unsafe_all_on.status_code == 409

        safe_all_on = client.post(
            "/api/v1/voice/intent",
            json={
                "mac": "AABBCCDDEEFF",
                "action": "on",
                "all_outlets": True,
                "confirm_all_on": True,
            },
            headers=auth(guest["access_token"]),
        )
        assert safe_all_on.status_code == 200
        assert len(safe_all_on.json()["command_ids"]) == 4


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

        allowed = client.post(
            "/api/v1/devices/A1B2C3D4E5F6/outlets/2?state=on",
            headers=auth(guest["access_token"]),
        )
        assert allowed.status_code == 200, allowed.text

        denied = client.post(
            "/api/v1/devices/A1B2C3D4E5F6/outlets/3?state=on",
            headers=auth(guest["access_token"]),
        )
        assert denied.status_code == 403

        voice_off = client.post(
            "/api/v1/voice/intent",
            json={"mac": "A1B2C3D4E5F6", "action": "off", "all_outlets": True},
            headers=auth(guest["access_token"]),
        )
        assert voice_off.status_code == 200, voice_off.text
        assert len(voice_off.json()["command_ids"]) == 2

        shares = client.get(
            "/api/v1/devices/A1B2C3D4E5F6/shares",
            headers=auth(owner["access_token"]),
        )
        assert shares.status_code == 200
        guest_row = next(item for item in shares.json()["shares"] if item["user_id"] == guest_id)
        assert guest_row["allowed_outlets"] == [1, 2]

        owner_still_controls_3 = client.post(
            "/api/v1/devices/A1B2C3D4E5F6/outlets/3?state=off",
            headers=auth(owner["access_token"]),
        )
        assert owner_still_controls_3.status_code == 200
