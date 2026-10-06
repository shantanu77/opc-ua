# Configure and run

Choose a source in Configure & Run. The two tabs are separate ways to define the
server's tags; their settings are never combined.

## XML file

The default is config_data.xml. Upload another XML using Upload & preview, or set
a server file path and click Load path & preview. The preview shows every data tag's
name, node ID, type, initial value, range, unit, pattern, full simulation parameters,
update interval and rule source. Properties such as EURange and EngineeringUnits
are metadata, not simulated tags. Invalid uploads preserve the previous file.

The bundled file defines:

| Tag | Initial | Rule |
| --- | --- | --- |
| Temperature | 135 | 135 + 3 sin(2πt/10), range 132–138 °C |
| Pressure | -11 | -11 + sin(2πt/15), range -12–-10 bar |
| MotorRunning | true | True for 300 seconds, false for 300 seconds |
| ProductionCount | 0 | Increment by 1 each tick; wrap to 0 after 999999 |
| SpeedSetpoint | 3 | Fixed at 3 |

The default producer tick is 1000 ms. An embedded SIMULATOR CONFIG comment may set
update_interval_ms, jitter_ms, global generation defaults, and node_overrides.
The counter is independent of MotorRunning, following the JSON rule. It does not
interpret descriptive text as conditional logic. MinimumSamplingInterval does
not set the producer tick. Tags without any simulation rule retain their initial
value. Global manual-form settings do not affect XML tags.

## Manual configuration

Choose a tag count, namespace, signal pattern, minimum and maximum, timing and
noise. Click Apply settings & preview to review the generated Tag0000… entries.
Manual mode never imports the XML file. Save & Start applies the current settings
and starts the OPC-UA server. Source switches refresh the preview automatically.

## Connect and observe

OPC-UA connection settings and optional run duration apply to either source.
The server only serves values; it creates no internal stress-test clients.
External clients can browse, read, write and subscribe. Live Data displays current
values read directly from OPC-UA, including external writes. Metrics count
producer updates and errors, not external client operations.
Stop before switching source or uploading/replacing a file.

```bash
docker build -t opc-ua-simulator:latest .
docker run --rm -p 8000:8000 -p 4840:4840 opc-ua-simulator:latest
```

Open http://localhost:8000. In Prosys connect to
opc.tcp://localhost:4840/freeopcua/server/. For remote Prosys use the Docker host
address and set Advertised hostname accordingly.
