# Direct VPS registry capacity

The server no longer imposes a fixed total count on registered MAC addresses. Startup accepts valid persisted and environment registries beyond 256 devices, and new registrations remain additive without an aggregate cap.

Per-request bulk assignment remains limited to 256 MAC addresses for bounded validation and IPC request sizes. Submit additional batches to grow the total registry. Authentication, explicit MAC approval, per-user grants, outlet policies and command rate limits are unchanged.

This is a registration change, not a claim of unlimited concurrent throughput. RAM, CPU, file descriptors, telemetry volume and API load still determine practical capacity. The existing status IPC response has a 1 MiB guard; substantial connected fleets will require paginated or filtered status retrieval and load testing before production scale-up.

Tests exercise 1,025 persisted registrations, restart recovery, adding the next registration, invalid-MAC rejection without corrupting the registry, and 512 entries from environment configuration. These are registry correctness tests, not a simulated-device load benchmark.

Deploy using the existing `server/update-direct-users.sh` pinned to the tested commit. The script backs up the existing application/database and daemon and preserves registered devices and accounts. No Android APK update is required for this server-only change.
