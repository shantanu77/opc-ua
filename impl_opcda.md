> Historical design notes. The current application serves OPC-UA only; see README.md and readmev2.md.

# OpenOPC Compatibility Layer: Configuration and Implementation

## 1. Scope

The application exposes its live simulated tags through an OpenOPC-compatible Pyro object. It does **not** implement native OPC Classic COM/DCOM interfaces. Brabo.io can call `list`, `read`, and `write` directly or use the normal OpenOPC `open_client()` gateway handshake.

Default endpoint:

```text
PYRO:opc@SIMULATOR_HOST:7766
```

The implementation is Linux/container compatible and uses open-source Pyro4.

## 2. Data flow

```text
Signal/variance engine
        |
        +--> asyncua node value
        |
        +--> thread-safe TagRegistry/current-value cache
                            |
                            v
                     OpenOPCAdapter
                            |
                  Pyro4 daemon thread :7766
                            |
                            v
                         Brabo.io
```

The existing producer updates the OPC-UA node and cache during the same producer iteration. Generated tags and discovered NodeSet variables are registered when the simulator starts.

## 3. Configuration screen

The dashboard contains an **OpenOPC** tab with two sections.

### Gateway configuration

| Field | Default | Meaning |
| --- | --- | --- |
| Enabled | `true` | Start the Pyro gateway with the web application |
| Allow Writes | `true` | Permit OpenOPC writes to update the current-value cache |
| Bind Host | `0.0.0.0` | Network interface on which Pyro listens |
| TCP Port | `7766` | OpenOPC gateway port |
| Pyro Object Name | `opc` | Object ID registered with the daemon |

Configuration can be saved only while the simulator is stopped, consistent with the existing configuration lifecycle. Changing gateway host, port, or object name restarts the background Pyro daemon.

For compatibility, keep the object name `opc` unless the consumer explicitly supports another object ID.

### Gateway status and tag registry

The screen displays:

- Listening/stopped state
- Bound host and port
- Pyro object name and URI
- Registered tag count
- Read, write, and list counters
- Startup error, if any
- Current tag path, value, type, quality, timestamp, and writable state

The tag table refreshes while the OpenOPC tab is active.

## 4. Configuration model

The fields are part of `SimulatorConfig`:

```json
{
  "openopc_enabled": true,
  "openopc_host": "0.0.0.0",
  "openopc_port": 7766,
  "openopc_object_name": "opc",
  "openopc_allow_writes": true
}
```

Configuration remains in memory, like the rest of the current application.

## 5. Tag registration

Generated tags use paths such as:

```text
SimulatedDevice.Tag0000
SimulatedDevice.Tag0001
```

They can also be resolved by their short browse name (`Tag0000`) or OPC-UA NodeId.

Imported NodeSet variables currently use their case-sensitive browse name as the OpenOPC path and their OPC-UA NodeId as an alias. If imported NodeSets contain duplicate browse names, a future revision must retain the complete browse path and reject collisions.

The registry stores:

- Canonical tag path
- Current value
- Quality string
- UTC ISO-8601 timestamp
- OPC-UA data type name
- Writable state

Access is protected by a re-entrant thread lock because the asyncio producer and Pyro worker threads use the same cache.

## 6. OpenOPCAdapter methods

The adapter also implements `create_client`, `release_client`, `connect`, `close`, and `servers` for the standard OpenOPC gateway setup. They are lightweight compatibility operations because the simulator cache is already the data source and requires no downstream COM connection.

### `read(tags)`

Accepts one tag path or an iterable of paths. It always returns a list of tuples:

```python
[
    ("SimulatedDevice.Tag0000", 42.5, "Good", "2026-09-16T09:30:00+00:00")
]
```

An unknown tag returns `None` with `Bad: Unknown tag` quality instead of terminating the complete batch.

### `write(tags, values=None)`

Accepted forms:

```python
adapter.write("Tag0000", 42.5)
adapter.write([("Tag0000", 42.5), ("Temperature", 21.0)])
adapter.write({"Tag0000": 42.5})
```

The method updates the shared cache and returns the same four-field tuples. Writes can be disabled globally. Unknown or non-writable tags return Bad quality.

The signal producer normally overwrites an OpenOPC write on its next update. Persisting writes or feeding them back into a signal pattern is a separate policy enhancement.

### `list(paths="*", recursive=False, flat=False)`

Returns sorted canonical tag-path strings. Shell-style wildcards are supported:

```python
adapter.list("SimulatedDevice.*")
```

## 7. Lifecycle

FastAPI startup configures and starts `OpenOPCGateway`. The gateway creates a Pyro daemon and registers `OpenOPCAdapter` under object ID `opc` in a daemon `threading.Thread` named `openopc-pyro-daemon`.

Application shutdown stops the simulator, asks the Pyro daemon to shut down, and joins the thread. The thread is marked daemon as a final process-exit safeguard.

## 8. REST observability

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/openopc/status` | Gateway endpoint, state, error, tag count, and method counters |
| GET | `/api/openopc/tags` | Current cache snapshot for the dashboard |

These HTTP endpoints are operational controls only. Brabo.io tag traffic uses Pyro on TCP 7766.

## 9. Docker deployment

Build:

```bash
docker build -t opc-ua-openopc-simulator:latest .
```

Run:

```bash
docker run --rm \
  --name opc-traffic-simulator \
  -p 8000:8000 \
  -p 4840:4840 \
  -p 7766:7766 \
  opc-ua-openopc-simulator:latest
```

Or use:

```bash
docker compose up --build
```

Brabo.io should use the Docker host address, not `0.0.0.0`:

```text
PYRO:opc@DOCKER_HOST:7766
```

Port 7766 uses unauthenticated Pyro in this first internal version. Restrict it to the trusted test network and do not publish it to the internet.

## 10. Validation

Automated unit coverage verifies:

- Alias reads and OpenOPC tuple shape
- Unknown-tag quality
- Single, batch, and dictionary writes
- Disabled writes
- Wildcard listing
- Concurrent registry updates and reads

Integration acceptance with Brabo.io must verify:

1. Connection to `PYRO:opc@host:7766`.
2. Listing generated and imported tags.
3. Repeated reads while signal values change.
4. Write followed by immediate read.
5. Simulator stop/start and tag-registry refresh.
6. Container restart and gateway reconnection.
7. Required sustained tag count and update rate.

## 11. Known limitations

- This is an OpenOPC/Pyro compatibility interface, not an OPC-DA COM server.
- The Pyro endpoint has no application authentication or TLS.
- OpenOPC writes update the cache but do not immediately schedule an asyncua node write.
- The producer overwrites written values on its next cycle.
- Imported NodeSet variables use browse names rather than complete hierarchical paths.
- Configuration and counters are not persistent.
- Compatibility must be confirmed with the exact Brabo.io OpenOPC client implementation.
