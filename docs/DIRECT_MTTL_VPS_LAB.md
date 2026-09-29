# NEXVARY — Direct MTTL-W01 → VPS Lab

Private experimental path for proving whether an MTTL-W01 can use a public VPS
as its TCP controller **without an Android controller phone in the data path**.

This lab belongs on the private NEXVARY branch:

`private/direct-mttl-lab`

It must not be merged into the public FG Machines distribution until the physical
test is complete.

## What is being tested

Normal verified local operation is:

```
MTTL-W01 → Android controller TCP 10086
```

The experiment changes only the controller address written during provisioning:

```
MTTL-W01 → Internet → VPS public IPv4:10086
```

The strip still joins the normal 2.4 GHz Wi-Fi/router for Internet access. During
provisioning, the controller IPv4 is changed from the phone/LAN address to the VPS
**public IPv4**.

The current provisioning dialect accepts an IPv4 address, not a DNS name, so use
the VPS public IPv4 for this test.

## Safety boundary

The first test is intentionally **observe/telemetry only**.

- Public TCP 10086 is opened only for the experimental controller listener.
- The listener accepts the verified text protocol and sends `up:getinfo:all`.
- Outlet ON/OFF commands are disabled by default.
- An optional MAC allow-list can reject every strip except the test unit.
- The maintenance port is loopback-only at `127.0.0.1:18087`.
- No public HTTP administration endpoint is created.

The MTTL protocol itself does not provide TLS or cryptographic peer
authentication. A direct public deployment therefore remains a lab path, not a
production recommendation.

## Install on Ubuntu 24.04 VPS

Run from a checkout of this branch:

```bash
sudo bash server/install-direct-mttl-lab.sh
```

If the repository is private, clone/authenticate with your normal NEXVARY GitHub
credential first, then run the script locally from the checkout.

Set the known test-strip MAC if available:

```bash
sudo nano /etc/nexvary-direct-mttl-lab.env
```

Example:

```text
NEXVARY_MTTL_ALLOWED_MAC=A1B2C3D4E5F6
NEXVARY_MTTL_ALLOW_CONTROL=0
```

Then:

```bash
sudo systemctl restart nexvary-direct-mttl-lab
sudo systemctl status nexvary-direct-mttl-lab --no-pager
sudo ss -lntp | grep 10086
sudo journalctl -u nexvary-direct-mttl-lab -f
```

## Provision the strip for the direct test

Use the existing setup AP / TCP 30300 provisioning flow.

The essential controller-setting frame is:

```text
up:ip:<VPS_PUBLIC_IPV4>
```

Then write the normal 2.4 GHz Wi-Fi credentials and reboot:

```text
up:connect:<SSID>:<PASSWORD>
up:reboot:0
```

Do not expose the Wi-Fi password in screenshots, chat logs or repository files.

## Success criteria

A successful direct test must show all of the following on the VPS:

1. incoming TCP connection on port 10086;
2. valid boot frame matching:
   `up:bootinfo:<model>;<MAC>;<same MAC>;<firmware>;connect`;
3. model equals `lgutap` for the verified family;
4. after the server sends `up:getinfo:all`, valid four-channel telemetry arrives;
5. connection remains stable for at least 10 minutes.

The log should contain lines similar to:

```text
device_online mac=... model=lgutap firmware=... peer=...
telemetry mac=... data=[...]
```

## Read local status

```bash
printf 'status\n' | nc 127.0.0.1 18087
```

Manual telemetry refresh:

```bash
printf 'refresh A1B2C3D4E5F6\n' | nc 127.0.0.1 18087
```

## Optional outlet-control test

Only after the MAC, firmware and telemetry are verified:

```bash
sudo sed -i 's/^NEXVARY_MTTL_ALLOW_CONTROL=.*/NEXVARY_MTTL_ALLOW_CONTROL=1/' /etc/nexvary-direct-mttl-lab.env
sudo systemctl restart nexvary-direct-mttl-lab
```

Then, from the VPS itself:

```bash
printf 'on A1B2C3D4E5F6 1\n'  | nc 127.0.0.1 18087
printf 'off A1B2C3D4E5F6 1\n' | nc 127.0.0.1 18087
```

Keep the load on outlet 1 non-critical during this test.

## Rollback

To return the strip to the existing Local-First design, put it back into setup
mode and provision the controller IPv4 to the Android controller/LAN address
again. ZeroTier and the normal FG Link paths remain separate from this branch.
