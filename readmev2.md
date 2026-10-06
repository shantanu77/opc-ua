# OPC Traffic Simulator — Unified Interface

The OPC Traffic Simulator provides a shared, changing tag dataset through OPC-UA and an OpenOPC-compatible Pyro gateway. The latest version brings tag definition, value variation, protocol selection, traffic generation, and runtime monitoring into one workflow.

## What is new

### One Configure & Run interface

The dashboard now follows one four-step workflow:

1. **Tags and volume** — choose the generated tag count and optionally load a NodeSet XML file.
2. **Value variation and speed** — configure the signal pattern, range, update interval, jitter, noise, and random seed.
3. **Protocol listeners** — configure OPC-UA and optionally enable the OpenOPC/Pyro listener.
4. **Traffic behavior** — serve values to external clients or create synthetic OPC-UA client traffic.

Use **Save & Start** to save the complete configuration and start the selected listeners. Use **Save Draft** to retain the configuration without opening listeners. **Stop** shuts down the producer, virtual clients, OPC-UA server, and OpenOPC gateway together.

### Shared tag registry

Generated OPC-UA variables and imported NodeSet variables are registered in one live catalog. Both OPC-UA and OpenOPC consumers see values originating from this shared dataset.

The interface displays an approximate tag-change rate calculated as:

```text
generated tag count × 1000 / update interval in milliseconds
```

This separates two important controls:

- **Data volume and speed** are controlled by tag count and update interval.
- **Protocol request load** is controlled by virtual clients and operations per second.

### Traffic modes

Two traffic modes are available:

- **Serve only** (`serve_only`) continuously varies tag values and serves external clients without creating internal clients.
- **Generate traffic** (`self_load`) creates virtual OPC-UA clients that perform read, write, browse, and subscribe operations.

Generated traffic supports:

- Configurable virtual-client count
- Operations per second per client
- Timed or unlimited runs
- Constant, linear-ramp, step-ramp, and spike-wave load profiles
- Read, write, browse, and subscribe ratios
- Optional fault injection

### Unified protocol lifecycle

OpenOPC previously started with the web application independently of the simulator. Protocol listeners now follow the run lifecycle:

- Saving a draft does not start OpenOPC.
- Starting the simulator starts OPC-UA and OpenOPC when OpenOPC is enabled.
- Stopping the simulator stops both listeners.
- The OpenOPC adapter can be stopped and restarted safely across repeated runs.

OPC-UA remains the core server and is always available during a run. OpenOPC can be enabled or disabled from the same configuration screen.

### Live Data view

The Live Data view provides:

- Run state and uptime
- Active protocols
- Current traffic mode
- Tag update and operation metrics
- OPC-UA and OpenOPC listener status
- Traffic timeline
- Shared live tag registry
- OpenOPC read and write counters

Starting a run automatically opens this view.

## Protocol behavior

OPC-UA and OpenOPC are server-side listeners. External clients connect to the simulator to read, write, browse, or subscribe. OPC-UA subscriptions deliver changes after the client establishes a session and subscription.

The **Generate traffic** option creates OPC-UA clients that connect back to this simulator for load testing. It does not send unsolicited data to an arbitrary passive client or remote broker.

## Technology stack

- Backend: FastAPI and asyncua
- OpenOPC compatibility: Pyro4
- Frontend: Vue 3 and Chart.js
- Runtime: Python 3.11
- Packaging: Docker and Docker Compose

## Project structure

```text
app/main.py                 FastAPI routes and application lifecycle
app/schemas.py              Configuration and response models
app/simulator.py            OPC-UA server, tag producer, and traffic engine
app/openopc_adapter.py      OpenOPC-compatible Pyro adapter and gateway
app/tag_registry.py         Thread-safe shared tag catalog
app/static/index.html       Unified dashboard
app/static/app.js           Dashboard state and API integration
app/static/styles.css       Dashboard styling
tests/                      Unit and lifecycle tests
one_interface.md            Detailed unified-interface change specification
Dockerfile                  Container image and health check
docker-compose.yml          Local container deployment
```

## Run with Docker

Build the image:

```bash
docker build -t opc-ua-simulator:latest .
```

Run it directly:

```bash
docker run --rm \
  --name opc-ua-simulator \
  -p 8000:8000 \
  -p 4840:4840 \
  -p 7766:7766 \
  opc-ua-simulator:latest
```

Or use Docker Compose:

```bash
docker compose up --build
```

Open the dashboard at:

```text
http://localhost:8000
```

Default listeners:

- Dashboard/API: `http://localhost:8000`
- OPC-UA: `opc.tcp://localhost:4840/freeopcua/server/`
- OpenOPC/Pyro: `PYRO:opc@localhost:7766`

The container health check verifies that the dashboard control plane is responding. An active simulation or enabled OpenOPC gateway is not required for the container to be healthy.

## Run the tests in Docker

The production image does not copy the test directory. Mount it when running the suite:

```bash
docker run --rm \
  --mount type=bind,src="$(pwd)/tests",dst=/app/tests,readonly \
  opc-ua-simulator:latest \
  python -m unittest discover -s tests -v
```

The current suite covers:

- OpenOPC read, write, list, and handshake behavior
- Tag alias resolution and write permissions
- Concurrent registry access
- OpenOPC gateway restart behavior
- Serve-only mode
- Self-generated traffic mode
- Saving configuration without starting a listener

## Configuration API

Get the current configuration:

```http
GET /api/simulator/config
```

Save the complete configuration:

```http
PUT /api/simulator/config
Content-Type: application/json
```

The configuration includes the new traffic-mode field:

```json
{
  "traffic_mode": "serve_only"
}
```

Start and stop the configured run:

```http
POST /api/simulator/start
POST /api/simulator/stop
```

The status response now includes the selected traffic mode and listeners that are actually active:

```json
{
  "running": true,
  "server_started": true,
  "traffic_mode": "self_load",
  "active_protocols": ["OPC-UA", "OpenOPC"]
}
```

Additional endpoints:

- `GET /api/simulator/status`
- `GET /api/simulator/metrics`
- `GET /api/simulator/events`
- `GET /api/namespace/info`
- `POST /api/namespace/upload`
- `DELETE /api/namespace/file`
- `GET /api/openopc/status`
- `GET /api/openopc/tags`

## NodeSet XML

A NodeSet XML file can be selected and uploaded from the Tags section. It is loaded on the next run and its supported variables are added to the shared registry alongside generated tags.

The uploaded file is stored as `uploaded_namespace.xml`. A configured NodeSet path can also be supplied through `namespace_nodeset_file`.

## Operational notes

- Traffic operation ratios must total exactly `1.0` in generated-traffic mode.
- Set the run duration to `0` for an unlimited run.
- Set the advertised server hostname to an address reachable by external OPC-UA clients when binding the endpoint to `0.0.0.0`.
- High tag counts combined with very short update intervals can produce substantial CPU and network load.
- The simulator is intended for development, QA, integration, and load-testing environments.

For implementation-level details and compatibility notes, see [`one_interface.md`](one_interface.md).
