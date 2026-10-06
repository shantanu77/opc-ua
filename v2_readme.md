# OPC-UA Simulator V2

The simulator publishes changing values through an OPC-UA server. Connect Prosys
or another OPC-UA client to browse, read, write or subscribe to its tags. It runs
in serve-only mode and does not create internal traffic-generation clients.

## Start the application

From the `opc-ua` project directory:

```bash
docker build -t opc-ua-simulator:latest .
docker run --rm --name opc-ua-v2 -p 8000:8000 -p 4840:4840 opc-ua-simulator:latest
```

Stop any existing simulator using those ports first. Open
`http://localhost:8000`. The Docker image includes `config_data.xml`.

For an exported image, load the tar before running its matching image tag:

```bash
docker load -i opc-ua-simulator-source-tabs.tar
docker run --rm --name opc-ua-v2 -p 8000:8000 -p 4840:4840 opc-ua-simulator:source-tabs
```

## Configure & Run

Choose one of the two tabs. The sources are exclusive: their tags and generation
settings are not combined.

### XML file

1. Use the bundled `config_data.xml`, or select a file and click **Upload & preview**.
   Alternatively, enter a path accessible to the server and click **Load path & preview**.
2. Review the table: tag name, node ID, type, initial value, range, unit, pattern,
   simulation parameters, update interval and rule source.
3. Set the OPC-UA endpoint and advertised hostname if necessary.
4. Click **Save & Start**.

XML defines the nodes and their metadata. JSON inside the XML's
`SIMULATOR CONFIG` comment defines how values change. Manual-form settings do
not affect XML simulation. See [configuration.md](configuration.md) for a complete
XML example, JSON rules and their linking behavior.

The bundled configuration produces:

| Tag | Type | Initial value | Simulation |
| --- | --- | --- | --- |
| Temperature | Double | 135 | Sinusoid, 132–138 °C, 10-second period |
| Pressure | Double | -11 | Sinusoid, -12–-10 bar, 15-second period |
| MotorRunning | Boolean | true | True for 300 seconds, then false for 300 seconds |
| ProductionCount | Int64 | 0 | Adds 1 each tick; wraps to 0 after 999999 |
| SpeedSetpoint | Double | 3 | Constant 3 |

The default tick is one second. ProductionCount is independent of MotorRunning.
A description mentioning a conditional pause does not implement that behavior.

### Manual configuration

1. Choose **Manual configuration**.
2. Set tag count and namespace URI.
3. Set signal pattern, minimum/maximum, update interval and optional noise/jitter.
4. Click **Apply settings & preview** to review generated tags.
5. Click **Save & Start**.

This mode generates writable Double tags named `Tag0000`, `Tag0001`, and so on
under `SimulatedDevice`. No XML is imported. It is useful for quickly creating
sample data without authoring a NodeSet. API JSON can configure this mode too;
see [configuration.md](configuration.md#manual-configuration-through-json).

## Connect Prosys

Use this endpoint when Prosys runs on the same machine as Docker:

```text
opc.tcp://localhost:4840/freeopcua/server/
```

For a remote client, replace `localhost` with the Docker host's reachable address
and set **Advertised hostname** to that address in the dashboard. The default
server endpoint binds to `0.0.0.0`; clients should connect to a reachable host
address, not `0.0.0.0`.

For the bundled XML, browse **Objects → Simulation → Line1**. For manual tags,
browse **Objects → SimulatedDevice**. Add tags to Prosys monitoring or subscriptions.

## Observe and change a run

**Live Data** reads values directly from the OPC-UA server, including external
client writes. Metrics show producer updates and generation errors; they do not
count external client operations. **Logs** shows imports, startup and errors.

**Stop** closes the OPC-UA listener and producer. Stop before switching source,
changing settings or uploading another XML. **Save Draft** validates and previews
settings without starting a listener. An invalid upload preserves the previously
accepted file. **Use default XML** returns to the bundled configuration.

Configuration saved through the dashboard/API is held in memory. Restarting the
container restores the bundled default configuration unless you mount a different
`config_data.xml`. Uploaded files inside a container are lost when that container
is removed.

To supply your own default file:

```bash
docker run --rm -p 8000:8000 -p 4840:4840 \
  -v "$PWD/config_data.xml:/app/config_data.xml:ro" opc-ua-simulator:latest
```

## API and verification

| Method | Route | Purpose |
| --- | --- | --- |
| GET / PUT | `/api/simulator/config` | Read or replace run configuration |
| POST | `/api/simulator/start` | Start serving values |
| POST | `/api/simulator/stop` | Stop the run |
| GET | `/api/simulator/tags` | Preview rules or read live values |
| GET | `/api/simulator/status` | Run and listener status |
| GET | `/api/simulator/metrics` | Value updates, errors and timeline |
| GET | `/api/simulator/events` | Event log |
| GET | `/api/namespace/info` | Selected XML source |
| POST | `/api/namespace/upload` | Validate, select and preview an XML upload |
| DELETE | `/api/namespace/file` | Remove the upload and select default XML |

With Python dependencies installed, run:

```bash
python -m unittest discover -s tests -v
```
