# OPC-UA simulator

The simulator automatically reads `config_data.xml` from the project root. This
NodeSet contains folders, five tags, engineering ranges and units, initial values,
and an embedded JSON simulator configuration. The rules are applied automatically.

| Tag | Type | Initial | Behavior |
| --- | --- | --- | --- |
| Temperature | Double | 135 | 135 + 3 sin(2πt/10), range 132–138 °C |
| Pressure | Double | -11 | -11 + sin(2πt/15), range -12–-10 bar |
| MotorRunning | Boolean | true | True for 300 seconds, false for 300 seconds |
| ProductionCount | Int64 | 0 | Increments by 1 per tick, wraps after 999999 |
| SpeedSetpoint | Double | 3 | Constant 3 |

ProductionCount follows the file's explicit JSON rule. It increments regardless
of MotorRunning; conditional gating mentioned in some XML descriptions is not
part of that rule. The default update interval is 1000 ms with no timing jitter.
Internal write traffic writes current values for file-configured tags so it does
not advance the counter or replace their patterns.

## Dashboard

Configure & Run and Live Data show the loaded tag table: name, node ID, type,
initial value, current value, range, unit, pattern, and status. Before starting,
values are read from XML. During a run, the API reads current values directly from
OPC-UA, including changes made by external clients. Metadata properties are never
simulated or included as traffic targets.

Use Save & Start to run; Stop shuts down the producer, clients and OPC-UA server.
Serve only generates values for external clients. Generate traffic additionally
starts internal OPC-UA clients with the configured operation mix and load profile.
The default exposes only the five XML tags. Additional generated tags are optional.
File-defined patterns take precedence over global and dashboard pattern overrides.
Numeric XML ranges bound initial values and simulator-generated writes.
External client writes are not restricted by that generation policy.

To use another file, set the NodeSet XML path or upload a NodeSet in the dashboard.
Changing the source is allowed only while stopped. Empty paths use config_data.xml.

## Docker and Prosys

```bash
docker build -t opc-ua-simulator:latest .
docker run --rm -p 8000:8000 -p 4840:4840 opc-ua-simulator:latest
```

Open http://localhost:8000 and start the simulator. Connect Prosys to
`opc.tcp://localhost:4840/freeopcua/server/`. For a remote client use the Docker
host address and configure the advertised hostname accordingly.
Browse Objects → Simulation → Line1 for the five tags. Range and engineering-unit
properties remain attached to Temperature and Pressure.

To replace the bundled configuration without rebuilding:

```bash
docker run --rm -p 8000:8000 -p 4840:4840 \
  -v "$PWD/config_data.xml:/app/config_data.xml:ro" opc-ua-simulator:latest
```

## API and verification

- GET/PUT `/api/simulator/config`
- POST `/api/simulator/start` and `/api/simulator/stop`
- GET `/api/simulator/status`, `/api/simulator/metrics`, `/api/simulator/events`
- GET `/api/simulator/tags` (loaded metadata plus current OPC-UA values)
- GET `/api/namespace/info`
- POST `/api/namespace/upload`, DELETE `/api/namespace/file`

```bash
python -m unittest discover -s tests -v
```

Tests import the actual configuration, read it through an OPC-UA client, verify
patterns and ranges, confirm that client traffic preserves the counter, and check
that the table reflects external writes.
