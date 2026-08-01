# OPC-UA Traffic Simulator Specification

## 1. Goal
Build a Python-based OPC-UA simulator with a web frontend to stress-test OPC-UA systems by generating realistic, configurable traffic patterns.

The simulator must support:
- Hosting an OPC-UA server with configurable tags/nodes.
- Generating dynamic telemetry values over time.
- Spawning virtual OPC-UA clients that create read/write/browse/subscribe traffic.
- Providing live observability via a frontend dashboard.
- Offering multiple traffic profiles and fault-injection options.

## 2. Primary Use Cases
- Validate throughput limits of OPC-UA integrations.
- Test behavior under normal and bursty traffic.
- Validate client reconnection and error handling with injected faults.
- Demonstrate OPC-UA behavior in QA/demo environments.

## 3. Functional Requirements

### 3.1 Simulator Core
- Embedded OPC-UA server with configurable endpoint.
- Namespace and folder creation for simulated devices.
- Configurable number of variables (tags).
- Runtime start/stop controls.

### 3.2 Signal Generation
Each tag value shall update continuously using selectable patterns:
- random
- sine
- sawtooth
- random_walk
- burst

Common options:
- min/max value range
- noise
- update interval (ms)
- jitter (ms)

### 3.3 Traffic Generation
Spawn N virtual OPC-UA clients connected to the simulator endpoint.

Supported operation types:
- read
- write
- browse
- subscribe

Configurable:
- number of virtual clients
- operations per second per client
- operation mix ratios

Advanced load controls:
- fixed-duration continuous test runs (x minutes)
- automatic stop when configured duration is reached
- load profiles:
	- constant
	- linear_ramp (gradually increase ops/sec)
	- step_ramp (increment load at fixed intervals)
	- spike_wave (periodic traffic spikes)
- profile parameters (target rate, ramp time, step interval, spike multiplier)

### 3.4 Fault Injection
Optional fault modes:
- random bad-node access attempts
- transient invalid writes
- configurable fault error rate

### 3.5 Metrics and Monitoring
Expose live metrics:
- running/stopped status
- uptime
- remaining run time for timed tests
- total operations
- ops/sec
- current configured client ops/sec after profile adjustment
- total errors
- per-operation counters
- node update counter
- recent event logs

### 3.6 API
REST API endpoints:
- GET /api/simulator/config
- PUT /api/simulator/config
- POST /api/simulator/start
- POST /api/simulator/stop
- GET /api/simulator/status
- GET /api/simulator/metrics
- GET /api/simulator/events

## 4. Non-Functional Requirements
- Async-first architecture for high concurrency.
- Safe repeated start/stop operations.
- Stable operation for long-running tests.
- Clean shutdown of clients and server.
- Minimal dependencies and easy local startup.

## 5. Technical Stack
- Backend: Python 3.11+, FastAPI, Uvicorn, asyncua.
- Frontend: Vue 3 + Chart.js (served as static assets).
- Styling: custom CSS with responsive layout.

## 6. Frontend UX Requirements
Dashboard sections:
- Simulator control panel
- Traffic and signal configuration form
- Live status cards
- Real-time charts (ops/sec and errors)
- Per-operation counters
- Event log panel

UX behavior:
- One-click start/stop
- Validation for invalid config values
- Auto-refresh every second
- Mobile-friendly responsive layout

## 7. Security and Safety Notes
- Intended for controlled test environments.
- Default bind can be local or user-configurable.
- No auth included in MVP; deployment behind trusted network is recommended.

## 8. Implementation Plan
1. Create backend data models and simulator engine.
2. Implement API endpoints and lifecycle management.
3. Implement frontend dashboard for configuration and monitoring.
4. Wire frontend to API and validate end-to-end simulator flow.
5. Document run steps and defaults.

## 9. Success Criteria
- User can configure simulator from frontend.
- Simulator starts and creates measurable OPC-UA traffic.
- Metrics update live and reflect traffic patterns.
- Multiple traffic profiles and fault injection are demonstrably functional.
