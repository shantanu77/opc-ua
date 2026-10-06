# OPC-UA Simulator

Serve changing tag values to Prosys and other OPC-UA clients. Configure & Run has
two source tabs:

- **XML file**: upload a NodeSet or use the bundled `config_data.xml`. The simulator
  reads its tags, initial values, ranges, units and embedded simulation rules.
- **Manual configuration**: create generated tags and configure their count,
  namespace, value range, signal pattern and update speed. No XML is imported.

The preview table shows exactly which values and simulation rules will be used.
Live Data reads current values directly from the running OPC-UA server.
The application runs in serve-only mode; external clients browse, read, write
and subscribe. Metrics show value updates and generation errors.

## Run with Docker

```bash
docker build -t opc-ua-simulator:latest .
docker run --rm -p 8000:8000 -p 4840:4840 opc-ua-simulator:latest
```

Open http://localhost:8000, review the preview and click Save & Start. Connect to
`opc.tcp://localhost:4840/freeopcua/server/`. For remote clients set the advertised
hostname to the Docker host's reachable address.

## Configuration behavior

XML mode ignores manual tag-generation settings. The embedded SIMULATOR CONFIG
JSON supports node_overrides and global generation settings, including
update_interval_ms (default 1000) and jitter_ms (default 0). File rules take
precedence. Without a per-tag or global simulation rule, the XML initial value is
held. MinimumSamplingInterval remains OPC-UA client sampling metadata.
Numeric XML ranges bound initial values and generated updates. External writes
are not restricted by the generation policy. Comments/descriptions do not define
simulation behavior; the embedded JSON does.

## API

- GET/PUT `/api/simulator/config`
- POST `/api/simulator/start`, `/api/simulator/stop`
- GET `/api/simulator/tags`, `/api/simulator/status`, `/api/simulator/metrics`, `/api/simulator/events`
- GET `/api/namespace/info`
- POST `/api/namespace/upload`, DELETE `/api/namespace/file`

```bash
python -m unittest discover -s tests -v
```

See [v2_readme.md](v2_readme.md) for setup and usage, and
[configuration.md](configuration.md) for XML/JSON configuration examples.
