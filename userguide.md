# OPC-UA Traffic Simulator User Guide

## 1. What this application does

The OPC-UA Traffic Simulator runs three components together:

1. An OPC-UA server that exposes writable, changing variables.
2. Virtual OPC-UA clients that generate read, write, browse, and subscription traffic against that server.
3. A browser dashboard and REST API for configuration, lifecycle control, metrics, and logs.

It is intended for development, demos, QA, soak testing, and load testing on a trusted network. It has no user authentication and the OPC-UA endpoint does not currently configure certificates, credentials, or secure policies. Do not expose it directly to an untrusted network.

## 2. Quick start

### Run from source

Requirements:

- Python 3.11 or newer
- Network access from the browser to the Vue and Chart.js CDNs used by the dashboard

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000`.

For development with automatic reload:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Run with Docker Compose

```bash
docker compose up --build
```

Open `http://localhost:8000`. The compose file publishes:

- TCP 8000: dashboard and REST API
- TCP 4840: OPC-UA endpoint

Stop and remove the container with:

```bash
docker compose down
```

### Run a prebuilt image

If a published image is available:

```bash
docker run --rm \
  --name opc-ua-simulator \
  -p 8000:8000 \
  -p 4840:4840 \
  shantanu77/opc-ua-simulator:latest
```

The image and compose deployment have no persistent volume by default. An XML file uploaded through the dashboard and all runtime configuration are lost when the container is replaced.

## 3. First test

1. Open the dashboard.
2. Keep the default endpoint and set **Virtual Clients** to `1` for a small test.
3. Confirm that the four traffic ratios add up to `1.00`.
4. Select **Save Config**.
5. Select **Start Simulator**.
6. Confirm that **State** changes to `Running`, **Node Updates** increases, and operation counters begin increasing.
7. Connect an external OPC-UA client to `opc.tcp://localhost:4840/freeopcua/server/`.
8. Browse `Objects/SimulatedDevice/Tag0000` and read its changing value.
9. Select **Stop Simulator** when finished.

Configuration cannot be changed while the simulator is running. Stop it before saving new settings.

## 4. OPC-UA endpoint and remote clients

For clients on the same machine, use:

```text
opc.tcp://localhost:4840/freeopcua/server/
```

For remote clients, the server must listen on all interfaces while advertising a hostname the client can reach:

```text
Endpoint:        opc.tcp://0.0.0.0:4840/freeopcua/server/
Server Hostname: 192.168.1.50
```

Remote clients then connect to:

```text
opc.tcp://192.168.1.50:4840/freeopcua/server/
```

Replace the address with the server's DNS name or IP address. Allow inbound TCP 4840 through the host firewall. In Docker, publish that port as shown above. `0.0.0.0` is a bind address, not a client destination.

If changing the OPC-UA port in the endpoint, also change the Docker port mapping. For example, endpoint port 4841 requires `-p 4841:4841`.

## 5. Dashboard

### Status cards

- **State**: lifecycle state.
- **Uptime**: time since the current run started.
- **Total Ops**: operations completed by the built-in virtual clients.
- **Ops/Sec**: average virtual-client operations per second over the current run, not an instantaneous rate.
- **Client Rate**: current configured rate per virtual client after applying the selected load profile.
- **Errors**: producer, client, connection, subscription, and injected errors.
- **Node Updates**: successful server-side writes performed by the signal producer.
- **Remaining Run Time**: countdown for a timed run, or `Unlimited` when duration is zero.

The traffic chart shows per-second virtual-client operation and error deltas for the most recent 40 samples. The server retains up to 300 samples internally.

### Dashboard tab: signal generation

| Setting | Meaning | Valid range |
| --- | --- | --- |
| Endpoint | Address on which the embedded OPC-UA server listens | OPC TCP URL |
| Server Hostname | Host substituted into endpoint discovery results when binding to `0.0.0.0` | Reachable hostname or IP |
| Namespace URI | URI registered for generated nodes | Non-empty URI recommended |
| Node Count | Number of generated `Double` variables | 1–5000 |
| Update Interval | Target producer cycle | 10–10000 ms |
| Jitter | Random positive or negative timing variation | 0–2000 ms |
| Min/Max Value | Global output bounds for legacy patterns | Max must exceed min |
| Noise Amplitude | Noise added to legacy patterns | 0–1000 |
| Random Seed | Makes random behavior repeatable for the same configuration | 0–2147483647 |

Generated nodes are named `Tag0000`, `Tag0001`, and so on, under `Objects/SimulatedDevice`. They are writable `Double` variables.

The dashboard exposes these global patterns:

- `random`: uniform random values within the configured range.
- `sine`: phase-shifted sine values across tags.
- `sawtooth`: repeating linear rise.
- `random_walk`: bounded random movement from the preceding value.
- `burst`: random values with occasional configured bursts.

The backend also supports `constant`, `sinusoid`, `square`, `triangle`, `expression`, and `counter`. These advanced patterns and per-node overrides currently must be configured through the API; see [Advanced per-node patterns](#10-advanced-per-node-patterns).

### Dashboard tab: traffic generation

**Virtual Clients** controls how many internal clients connect to the embedded server. Setting it to zero runs the signal producer and server without generating client traffic.

**Client Ops/Sec** is a per-client target. For a constant profile, a rough aggregate target is:

```text
virtual_clients × client_ops_per_sec
```

Actual throughput depends on operation latency, subscriptions, jitter, machine resources, and event-loop load.

The traffic mix selects an operation probabilistically on each client cycle:

- **Read** reads a random simulated node.
- **Write** writes a generated value to a random simulated node.
- **Browse** browses the Objects folder.
- **Subscribe** adds or rotates a monitored item on a persistent subscription. Each virtual client retains at most five monitored items.

All four ratios must add up to exactly `1.00` within floating-point tolerance.

### Load profiles

| Profile | Behavior |
| --- | --- |
| `constant` | Holds the base Client Ops/Sec value. |
| `linear_ramp` | Moves linearly from the base rate to Ramp Target over Ramp Duration. |
| `step_ramp` | Moves toward Ramp Target by Step Increment at every Step Interval. It can ramp up or down. |
| `spike_wave` | Multiplies the base rate at each Spike Every interval. A spike lasts 20% of that interval, capped at 20 seconds and floored at 1 second. |

The displayed **Client Rate** is per client. A duration greater than zero automatically stops the run when the duration is reached.

### Fault injection

When enabled, each selected operation has the configured probability of first reading a deliberately invalid NodeId. That failed read increments the error count and the intended normal operation for that cycle is not completed. This tests error handling; it does not simulate network loss, delayed responses, or server shutdown.

### Namespace tab

Use this tab to upload a UA NodeSet2 XML document or configure a server-local file path. The file is imported on the next start, not immediately into a running server.

NodeSet selection uses the first existing file in this order:

1. `namespace_nodeset_file` from configuration.
2. `uploaded_namespace.xml` in the process working directory.
3. `opcua_simulation_namespace 2.xml` in the process working directory.
4. `opcua_simulation_namespace.xml` in the process working directory.
5. `namespace.xml` in the process working directory.

The committed `opc.xml` file is an example but is not auto-detected by that filename. Set its path explicitly or upload it. The Dockerfile does not currently copy either example XML file into the image.

After import, the simulator recursively discovers variables in non-built-in namespaces to a maximum object depth of six. Imported scalar Boolean and numeric variables are updated with type conversion. Unsupported or structured types may reject writes and appear in the error log.

The simulator always adds its generated `SimulatedDevice` tags as well as imported nodes. **Node Count** does not control the number of imported variables.

An upload always replaces the single server-side `uploaded_namespace.xml` file. **Clear Uploaded** deletes it. Uploads are not size-limited by application code, so deployments should enforce request limits at a reverse proxy.

### Logs tab

The backend retains the latest 2000 events in memory. The browser displays the latest 80 in reverse chronological order and supports level and text filtering. Starting a new run clears previous events. With verbose events enabled, one metrics heartbeat per second and subscription details are recorded.

## 6. Connect with an external OPC-UA client

Use any standards-compatible OPC-UA client and the configured endpoint. With the default generated namespace:

1. Connect anonymously to the endpoint.
2. Browse **Objects**.
3. Open **SimulatedDevice**.
4. Read or subscribe to `Tag0000` through `TagNNNN`.
5. Optionally write a numeric value. The next producer cycle will normally overwrite it.

The namespace index is assigned at runtime. Browse for nodes or resolve the namespace URI instead of assuming a fixed `ns=N` index, particularly when importing a NodeSet.

## 7. Common scenarios

### Server-only signal source

- Virtual Clients: `0`
- Update Interval: as required
- Pattern: desired signal pattern
- Run Duration: `0`

This exposes changing tags for external clients without internal traffic.

### Ten-minute linear ramp

- Virtual Clients: `10`
- Client Ops/Sec: `5`
- Load Profile: `linear_ramp`
- Ramp Target Ops/Sec: `50`
- Ramp Duration: `10`
- Run Duration: `10`

The rate moves from 5 to 50 operations per second **for each virtual client**.

### Periodic spikes

- Virtual Clients: `4`
- Client Ops/Sec: `10`
- Load Profile: `spike_wave`
- Spike Every: `30`
- Spike Multiplier: `3`

Each client targets 30 ops/sec during the spike window and 10 ops/sec otherwise.

### Reproducible run

Use the same complete configuration and Random Seed. Timing and task scheduling can still change the exact interleaving under concurrency, so reproducibility is approximate rather than a deterministic traffic transcript.

## 8. REST API

Interactive OpenAPI documentation is available at `http://localhost:8000/docs`.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/simulator/config` | Read active in-memory configuration |
| PUT | `/api/simulator/config` | Replace configuration while stopped |
| POST | `/api/simulator/start` | Start server, producer, metrics, and clients |
| POST | `/api/simulator/stop` | Stop the current run |
| GET | `/api/simulator/status` | Read lifecycle and timing status |
| GET | `/api/simulator/metrics` | Read counters and timeline |
| GET | `/api/simulator/events` | Read retained events oldest-first |
| GET | `/api/namespace/info` | Show resolved NodeSet information |
| POST | `/api/namespace/upload` | Upload multipart field `file` containing XML |
| DELETE | `/api/namespace/file` | Delete the uploaded XML file |

Basic commands:

```bash
curl http://localhost:8000/api/simulator/config
curl -X POST http://localhost:8000/api/simulator/start
curl http://localhost:8000/api/simulator/status
curl http://localhost:8000/api/simulator/metrics
curl -X POST http://localhost:8000/api/simulator/stop
```

Upload a NodeSet:

```bash
curl -X POST http://localhost:8000/api/namespace/upload \
  -F 'file=@opc.xml'
```

`PUT /api/simulator/config` accepts a `SimulatorConfig` document. Omitted fields receive model defaults rather than retaining their prior values, so automation should GET the current document, modify it, and PUT the complete result.

Example using `jq`:

```bash
curl -s http://localhost:8000/api/simulator/config \
  | jq '.virtual_clients = 8 | .client_ops_per_sec = 10' \
  | curl -sS -X PUT http://localhost:8000/api/simulator/config \
      -H 'Content-Type: application/json' \
      --data-binary @-
```

Saving while running returns HTTP `409`. Schema validation failures return HTTP `422`.

## 9. Configuration lifecycle

Configuration exists only in process memory. Restarting the Python process or replacing a container restores code defaults. There is no configuration file or database persistence in the current version.

Starting a run resets counters, timeline, event history, random-walk/counter state, and the random generator. Stopping retains the final counters and events until the next start.

## 10. Advanced per-node patterns

Per-node overrides are keyed by the case-sensitive browse name, such as `Tag0000` or `Temperature`. Retrieve the current configuration, add `node_overrides`, and PUT the complete document.

Example:

```json
{
  "node_overrides": {
    "Tag0000": {
      "pattern": "sinusoid",
      "amplitude": 10,
      "value_offset": 25,
      "period_s": 60
    },
    "Tag0001": {
      "pattern": "counter",
      "counter_min": 0,
      "counter_max": 500,
      "counter_step": 1,
      "counter_direction": "up"
    },
    "Tag0002": {
      "pattern": "square",
      "square_low": 0,
      "square_high": 1,
      "square_period_s": 10,
      "square_duty": 0.5
    }
  }
}
```

Additional patterns:

- `constant`: `constant_value`
- `sinusoid`: `amplitude`, `value_offset`, `period_s`, `time_offset_s`
- `square`: `square_low`, `square_high`, `square_period_s`, `square_duty`
- `triangle`: `triangle_min`, `triangle_max`, `triangle_period_s`
- `counter`: `counter_min`, `counter_max`, `counter_step`, `counter_direction`
- `expression`: `expression` plus a map of symbol names to non-expression patterns in `symbols`

Allowed expression operations are `+`, `-`, `*`, `/`, `//`, `%`, and `**`. Allowed functions are `sin`, `cos`, `tan`, `sqrt`, `abs`, `floor`, `ceil`, `log`, `exp`, `min`, and `max`; constants are `pi` and `e`. Invalid expressions currently evaluate to `0` rather than producing a log error.

See `version2.md` for every override field and more examples.

## 11. Troubleshooting

### Dashboard is blank or charts do not load

The page loads Vue 3, Chart.js, and fonts from public CDNs. Confirm the browser can reach those CDNs. For an offline deployment, vendor those assets into `app/static` and update `index.html`.

### Port already in use

Stop the process using TCP 4840, or change the endpoint to a free port and update the container port mapping. The start API returns `409` for a detected address conflict.

### External client receives an unreachable `0.0.0.0` endpoint

Set **Server Hostname** to the server's reachable DNS name or IP, save, and restart the simulator.

### NodeSet does not load

- Stop the simulator before changing configuration.
- Check **Namespace > Active file**.
- Use a path visible inside the container, not a host-only path.
- Inspect Logs for an import error.
- Confirm the document is UA NodeSet2 XML and its namespace declarations match its NodeIds.

The simulator attempts a narrow compatibility repair for a common single-URI `ns=2` mismatch, but it cannot repair arbitrary invalid NodeSets.

### Imported variables do not change

Confirm that they are scalar `UAVariable` nodes below Objects, use namespace index greater than 1, and are no deeper than six objects from the root browse. Check the startup log for the discovered browse names and look for type/write errors.

### Error counter rises rapidly

- Disable fault injection to distinguish deliberate failures.
- Reduce virtual clients or per-client rate.
- Reduce verbose logging at high traffic rates through the API (`verbose_events: false`).
- Inspect the Logs tab for connection, session, type conversion, or write errors.

### Remote client cannot connect

Verify the endpoint host, TCP port publication, firewall, routing, and server state. This application does not enable OPC-UA username authentication or certificate-secured endpoints.

## 12. Current limitations

- Configuration, metrics, and logs are in memory only.
- No dashboard/API authentication or authorization.
- CORS permits every origin.
- No configured OPC-UA security policy, certificate trust workflow, or user credentials.
- One simulator instance per application process.
- Uploaded XML uses one fixed filename and has no application-level size limit.
- Advanced per-node patterns are API-only.
- Metrics describe built-in virtual clients; external client operations are not counted.
- The dashboard requires third-party CDN assets at runtime.

Use bounded load tests, monitor host CPU and memory, and deploy behind network controls appropriate for a test tool.
