# Unified Configure & Run Interface

## Purpose

The simulator now uses one workflow for defining tag data, selecting protocol listeners, choosing traffic behavior, and starting a run. The same live tag registry is presented to OPC-UA and OpenOPC consumers, so tag values only need to be configured once.

## User workflow

The **Configure & Run** screen is organized into four sections:

1. **Tags and volume**
   - Set the number of generated tags.
   - Set the namespace URI.
   - Optionally provide or upload an OPC-UA NodeSet XML file.
   - Generated and imported variables are placed in the shared live tag registry.

2. **Value variation and speed**
   - Select the signal pattern.
   - Set minimum and maximum values.
   - Set the update interval and timing jitter.
   - Configure noise, burst settings, and the repeatable random seed.
   - The interface displays an approximate data-change volume using:

     `generated tag count × 1000 / update interval in milliseconds`

3. **Protocol listeners**
   - Configure the core OPC-UA endpoint and advertised hostname.
   - Enable or disable the OpenOPC/Pyro compatibility listener.
   - Configure the OpenOPC bind address, port, object name, and write permission.
   - Both listeners expose values from the same registry.

4. **Traffic behavior**
   - **Serve only** updates tag values and exposes them to external clients, but creates no internal virtual clients.
   - **Generate traffic** creates internal OPC-UA clients and exposes client count, rate, duration, load profile, operation mix, and fault-injection controls.

The primary action is **Save & Start**. It validates and saves the entire configuration before starting the run. **Stop** shuts down the run and its selected protocol listeners. **Save Draft** stores configuration without opening protocol listeners.

## Runtime behavior

### Unified lifecycle

Previously, the OpenOPC gateway started during FastAPI application startup and could remain independent of the simulator run. It now follows the simulator lifecycle:

- Saving configuration does not start a listener.
- Starting a run starts the OPC-UA server and, when enabled, the OpenOPC gateway.
- Stopping a run stops the producer, internal clients, OPC-UA server, and OpenOPC gateway.
- Application shutdown still performs a defensive gateway shutdown.

The Docker health check now checks the web application's simulator-status endpoint. Container health therefore means that the control plane is available; it does not require an active simulation or an enabled OpenOPC gateway.

### Traffic modes

`SimulatorConfig` has a new field:

```json
{
  "traffic_mode": "serve_only"
}
```

Allowed values are:

- `serve_only`: no virtual client tasks are created and the reported client operation target is `0`.
- `self_load`: the configured number of internal OPC-UA clients are created and use the selected load profile and operation mix.

The default remains `self_load` to preserve the previous behavior for API consumers that do not explicitly set the field.

### Status API additions

`GET /api/simulator/status` now includes:

```json
{
  "traffic_mode": "self_load",
  "active_protocols": ["OPC-UA", "OpenOPC"]
}
```

`active_protocols` reports listeners that are actually running, rather than protocols merely selected in the draft configuration.

## Interface views

- **Configure & Run** contains all settings required for a run.
- **Live Data** shows runtime metrics, listener status, the traffic chart, and the shared tag registry.
- **Logs** provides level and text filtering for simulator events.

Starting from the interface automatically opens **Live Data** so listener and tag activity can be verified immediately.

## Protocol semantics

OPC-UA and OpenOPC operate as server-side listeners in this application. External clients connect to those listeners. OPC-UA subscriptions deliver changes after a client creates a session and subscription; the simulator does not send unsolicited data to an arbitrary passive client.

The **Generate traffic** option specifically creates OPC-UA clients that connect back to this simulator for load testing. Sending to a different remote server or message broker would require a separate outbound-target mode and is not part of this change.

## Files changed

- `app/static/index.html`: replaces separated configuration tabs with the unified workflow and live-data view.
- `app/static/app.js`: adds traffic-mode state, summaries, estimates, unified save/start behavior, and continuous shared-tag refresh.
- `app/static/styles.css`: adds responsive layout and controls for the new workflow.
- `app/schemas.py`: adds `traffic_mode` and runtime protocol status fields.
- `app/simulator.py`: implements serve-only behavior and synchronized OpenOPC lifecycle.
- `app/openopc_adapter.py`: allows the same Pyro adapter to stop and restart cleanly across runs.
- `app/main.py`: removes automatic OpenOPC startup from application boot.
- `Dockerfile`: changes the health check to verify control-plane availability.
- `tests/test_simulator_modes.py`: covers traffic modes and confirms that saving does not start OpenOPC.

## Compatibility

- Existing configuration fields and API endpoints remain available.
- Existing clients that omit `traffic_mode` retain self-generated traffic behavior.
- OpenOPC remains enabled by default, but now begins listening only after the simulator is started.
- OPC-UA remains the core server and the transport used by internal virtual clients.
