# OPC Data Access (OPC-DA): Feasibility and Contingency Plan

## 1. Purpose and scope

This document evaluates how an OPC-DA traffic source could be added for Brabo.io ingestion testing.

This is a feasibility and contingency plan, not a claim that the application supports OPC-DA.

The team has selected an **OpenOPC/Pyro compatibility layer** as the first implementation. That interface is implemented and documented in `impl_opcda.md`. It exposes simulator values through Pyro but is not a native OPC Classic COM/DCOM server. This document now applies only if native COM/DCOM interoperability is later required.

### Recorded product decision

OPC-DA is deferred from the committed V2 implementation because the product must run in Ubuntu 22.04 or a similar Linux container and must avoid commercial toolkits. Conventional OPC Classic server hosting relies on Windows COM/DCOM. Formal certification is not required, but reliable interoperability with the Brabo.io DA consumer is required.

The rest of this document preserves the technical work needed if the team later approves either:

1. A Windows deployment exception using a separate open-source bridge/service.
2. A time-boxed evaluation of an open-source cross-platform DCOM/OPC Classic implementation.

The first compatibility target would be the exact DA version used by Brabo.io, preferably beginning with DA 2.05a only if that matches the connector.

## 2. Why OPC-DA cannot be added like another Python socket protocol

OPC Classic is based on Microsoft COM/DCOM and is tied to Windows technology. OPC-DA defines access to current values together with time and quality information. It is not the wire-compatible predecessor of `opc.tcp`, and `asyncua` does not implement it.

Authoritative background:

- [OPC Foundation: OPC Classic](https://opcfoundation.org/about/opc-technologies/opc-classic/)
- [Microsoft: Setting security for COM applications](https://learn.microsoft.com/en-us/windows/win32/com/setting-security-for-com-applications)
- [OPC Foundation: Developer tools](https://opcfoundation.org/developer-tools/)

Consequences for this repository:

- A production OPC-DA server needs a Windows runtime and COM registration/activation.
- Linux containers cannot directly register and expose a native Windows COM server.
- Remote access involves DCOM identity, launch/access permissions, authentication, firewall rules, and RPC port management.
- Implementing the complete COM/DCOM interfaces directly is high risk and outside the desired scope of this internal simulator.

## 3. Conventional contingency architecture

If a Windows exception is approved, keep the FastAPI/`asyncua` application on Linux and add a separate Windows OPC-DA bridge service built only from an acceptable open-source dependency.

```text
                         control and live metrics
Browser / REST clients <--------------------------> FastAPI application
                                                      |
                                    canonical tag/value engine
                                      |             |
                                      |             +--> asyncua OPC-UA server
                                      |
                                      +--> versioned bridge stream/API
                                                   |
                                                   v
                                      Windows OPC-DA service
                                      (open-source DA server stack)
                                                   |
                                                   v
                                         COM/DCOM OPC-DA clients
```

The Windows service owns all COM-specific behavior: ProgID/CLSID registration, server activation, groups, items, callbacks, OPC quality codes, and DCOM security. The Python application owns simulation configuration, signal generation, lifecycle, and shared metrics.

This split is recommended because it:

- Preserves the current Linux and Docker deployment for OPC-UA.
- Isolates COM apartment/threading and DCOM deployment concerns.
- Allows a DA scenario to have its own configurable tag set.
- Allows the DA implementation to be replaced behind a stable internal contract.
- Avoids loading Windows-only dependencies into the Python process.

For a Windows-only single-machine edition, the FastAPI application may also run on Windows, but the DA provider should still be a separate process so COM failures do not take down the simulator control plane.

The preferred but currently unproven path is a separate Linux container using an open-source managed DCOM/OPC Classic server. It would use the same versioned bridge contract without a Windows service. This path is acceptable only if Brabo.io can discover/connect to it and all required DA operations pass sustained integration tests.

## 4. Open-source feasibility gate

Do not add OPC-DA to the supported protocol list until an open-source proof of concept passes the acceptance tests below against Brabo.io.

Commercial server SDKs and gateways are excluded by product policy. Evaluate only open-source options after a maintenance, license, security, and interoperability review.

Be careful not to select a client-only package. For example, [TitaniumAS.Opc.Client](https://github.com/titanium-as/TitaniumAS.Opc.Client) provides DA client wrappers; it does not provide the DA server required by this plan.

An experimental modern implementation exists at [marcschier/opc-classic](https://github.com/marcschier/opc-classic), but its own project status identifies it as an alpha preview. It is a research candidate only. Its Linux server behavior must be demonstrated against the actual Brabo.io DA consumer before any architectural commitment.

Selection criteria:

- DA 2.05a and, if needed, DA 3.0 server support.
- 32-bit and 64-bit client interoperability requirements.
- Local and remote COM activation.
- Browse, sync/async read and write, groups, callbacks, deadband, requested update rate, quality, and timestamps.
- Clean .NET or native service hosting API.
- Supported Windows versions and patch policy.
- Licensing, redistribution, CI, and unattended installation rights.
- Active maintenance, acceptable open-source licensing, and reproducible source builds.
- Behavior with current DCOM authentication hardening.

Proof-of-concept exit criteria:

- Brabo.io discovers or is configured to connect to the simulated server.
- Brabo.io connects using its actual deployment identity and topology.
- 1000 items can be browsed and subscribed without leaks or deadlocks.
- Client writes reach the Python canonical model.
- Service restart and bridge reconnect do not require reinstalling COM registration.
- Both required client bitness combinations are verified.

## 5. Refactor the simulator around a canonical tag model

The current producer writes directly to `asyncua` node objects in `OPCUASimulator._producer_loop`. Refactor this before adding DA so values are generated once and published to protocol adapters.

Introduce protocol-neutral models, for example:

```text
TagDefinition
  key                 stable internal identifier
  browse_name         Tag0000, Temperature, ...
  browse_path         SimulatedDevice/Tag0000, ...
  canonical_type      bool, int16, uint16, int32, uint32, int64, float, double, string
  writable            boolean
  description         optional

TagSample
  key
  value
  quality             GOOD, UNCERTAIN, BAD plus optional substatus
  source_timestamp    UTC
  sequence            monotonically increasing integer
```

Add these internal interfaces:

```python
class TagCatalog:
    def snapshot(self) -> list[TagDefinition]: ...

class ValueStore:
    def read(self, keys: list[str]) -> list[TagSample]: ...
    async def write(self, writes: list[TagWrite], origin: str) -> list[WriteResult]: ...
    async def subscribe(self) -> AsyncIterator[list[TagSample]]: ...

class ProtocolAdapter:
    async def start(self, catalog: TagCatalog, values: ValueStore) -> None: ...
    async def stop(self) -> None: ...
```

Then make the signal producer update the DA scenario's `ValueStore`, and make the DA provider consume those `TagSample` values. Sharing a value with an OPC-UA scenario can remain an optional later feature rather than a requirement.

Use a stable internal key independent of any protocol-assigned runtime identifier. If a DA scenario is deliberately linked to imported OPC-UA nodes, remember that UA namespace indexes can change when NodeSets are imported.

## 6. OPC-UA to OPC-DA mapping

Define and test the mapping before implementing the bridge.

| Canonical concept | OPC-UA representation | OPC-DA representation |
| --- | --- | --- |
| Tag identity | NodeId plus browse path | ItemID string |
| Hierarchy | Objects and child nodes | Branch/leaf browse hierarchy |
| Current value | DataValue.Value | VARIANT value |
| Quality | StatusCode | OPC quality word |
| Time | SourceTimestamp | FILETIME timestamp |
| Write permission | AccessLevel/UserAccessLevel | Item access rights |
| Subscription | MonitoredItem | DA group/item callback |

Recommended ItemID rule:

```text
SimulatedDevice.Tag0000
Imported.<escaped browse path>
```

Requirements:

- ItemIDs must be stable across restart for the same configuration.
- Escape `.`, path separators, and other chosen delimiter characters in browse names.
- Detect duplicate browse paths and assign a deterministic suffix or reject startup.
- Store the canonical-key-to-UA-NodeId and canonical-key-to-DA-ItemID maps explicitly.
- Do not key per-node overrides by DA ItemID; retain the existing case-sensitive browse-name behavior until overrides migrate to stable canonical keys.

Initial type mapping:

| Canonical type | OPC-UA | OPC-DA VARIANT |
| --- | --- | --- |
| Boolean | Boolean | `VT_BOOL` |
| Signed 16-bit | Int16 | `VT_I2` |
| Unsigned 16-bit | UInt16 | `VT_UI2` |
| Signed 32-bit | Int32 | `VT_I4` |
| Unsigned 32-bit | UInt32 | `VT_UI4` |
| Signed 64-bit | Int64 | `VT_I8` when supported by target clients; otherwise documented conversion |
| Float | Float | `VT_R4` |
| Double | Double | `VT_R8` |
| String | String | `VT_BSTR` |

Start with scalar types. Reject arrays, structures, localized text, and opaque extension objects with an explicit unsupported-type event until their conversion rules and client compatibility are defined.

Quality mapping must be intentional rather than always Good. At minimum map canonical `GOOD`, `UNCERTAIN`, `BAD`, stale/communication failure, out-of-service, and write failure states to the closest UA StatusCode and DA quality/substatus. Preserve the source timestamp produced with the value.

## 7. Bridge contract

Use a versioned, bidirectional contract between Python and a separate DA provider. gRPC streaming is a suitable default for separate processes; a secured WebSocket is also acceptable if the team wants to stay within the existing FastAPI stack. Avoid per-tag HTTP polling.

Minimum messages:

- `Hello`: protocol version, instance ID, supported features.
- `CatalogSnapshot`: generation number and all tag definitions.
- `CatalogDelta`: add, update, or remove tags for a future dynamic model.
- `ValueBatch`: sequence, values, quality, source timestamps.
- `WriteRequest` / `WriteResult`: correlation ID, item keys, values, per-item result.
- `StateChange`: starting, running, stopped, degraded.
- `Heartbeat`: liveness, queue depth, last applied sequence.

Contract rules:

- Batch producer updates to reduce inter-process overhead.
- Bound queues and expose dropped/coalesced update metrics.
- Coalesce superseded samples per tag when a slow DA client cannot keep up.
- Never block the Python producer on a DA callback.
- Make writes idempotent using a correlation ID.
- Define whether an accepted DA write is visible until the next producer tick; the current UA behavior overwrites external writes on the next update.
- On reconnect, send a complete catalog and current-value snapshot before deltas.
- Authenticate and encrypt traffic when the bridge crosses hosts. Bind to loopback only when both processes are local.

## 8. OPC-DA provider responsibilities

The service should:

- Provide repeatable DCOM/OPC registration or activation through the container entrypoint and deployment tooling, not ad hoc manual changes.
- Register an explicit product ProgID and CLSID. Keep them stable across upgrades.
- Support process recovery and structured logs.
- Initialize DCOM security once at process startup according to the selected open-source stack.
- Translate toolkit callbacks to the bridge without executing network calls on COM callback threads.
- Implement browse branches/leaves from the canonical catalog.
- Implement synchronous reads from an in-memory cache.
- Route writes asynchronously to Python and return per-item HRESULTs according to the toolkit contract.
- Use DA groups to manage active items, requested update rate, callbacks, deadband, and client handles.
- Mark cached values stale/bad if the Python heartbeat expires.
- Expose health information to FastAPI and container logs.
- Drain callbacks and revoke COM activation cleanly on shutdown.

Prefer cache reads inside the DA service. A DA read must not synchronously cross the network for every item; doing so would couple COM call latency and availability to Python.

## 9. Python application changes

Suggested repository layout:

```text
app/
  domain/
    tags.py                 canonical definitions, samples, type and quality enums
    value_store.py          current values and fan-out subscriptions
  patterns.py               extracted signal generation
  protocols/
    opcua_adapter.py        asyncua server adapter
    da_bridge.py            bridge server/session manager
  simulator.py              lifecycle orchestration
  schemas.py                public API models
opc_da_provider/
  OpcDaProvider.sln         open-source managed DCOM/DA provider
contracts/
  opc_da_bridge.proto       or equivalent versioned schema
tests/
  unit/
  integration/
```

Add configuration fields only after the bridge proof of concept:

```json
{
  "protocols": {
    "opc_ua": { "enabled": true },
    "opc_da": {
      "enabled": false,
      "bridge_url": "http://opc-da-provider:7443",
      "instance_name": "OPC Traffic Simulator",
      "stale_after_ms": 5000
    }
  }
}
```

Keep DCOM credentials out of this document and the JSON API. Use a secret store or deployment-time protected configuration.

Add control/observability endpoints:

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/protocols` | UA and DA enabled/connected/degraded state |
| GET | `/api/opc-da/status` | Bridge heartbeat, service version, clients, groups, items, queue depth |
| GET | `/api/opc-da/items` | Canonical key to DA ItemID/type/quality map |
| POST | `/api/opc-da/reconnect` | Operator-requested bridge reconnect while simulator is running |

Extend metrics with DA client connections, active groups/items, reads, writes, callbacks, rejected writes, bridge reconnects, queue depth, dropped/coalesced samples, and last heartbeat age. Keep UA and DA counters separate plus an aggregate view.

## 10. Delivery phases

### Phase 0: Brabo.io and Linux feasibility spike

Deliverables:

- Record the exact Brabo.io DA connector version, DA version, bitness, topology, authentication behavior, and expected scale.
- Evaluate open-source server candidates and their transitive licenses, maintenance, and reproducible-build status.
- Build a disposable Ubuntu-container proof of concept with ten static items.
- Record the selected candidate/version, license, known limitations, and decision rationale.

Exit: Brabo.io can connect, browse, read, subscribe, and write from its real deployment topology. If this fails, OPC-DA remains deferred.

### Phase 1: protocol-neutral core

Deliverables:

- Add `TagCatalog`, `ValueStore`, canonical types/quality, and timestamps.
- Extract patterns from direct UA writes.
- Convert the existing UA server into an adapter over the scenario model.
- Preserve current REST behavior, generated tags, NodeSet imports, counters, and load profiles.

Exit: existing UA scenarios pass with no DA service installed, and every producer tick creates one canonical sample per tag.

### Phase 2: Linux DA minimum viable server

Deliverables:

- Versioned bridge contract with catalog, snapshots, batches, writes, and heartbeat if DA runs as a separate process.
- Reproducible Ubuntu container image for the open-source DA server.
- DA browse, synchronous read, writes, groups, and data-change callbacks.
- Scalar Boolean, integer, Float, Double, and String conversions.
- Bridge reconnect and stale-quality behavior.

Exit: Brabo.io passes browse/read/write/subscription tests for 100 generated items through start, stop, and restart.

### Phase 3: dashboard and traffic generation

Deliverables:

- DA state and counters in the dashboard.
- Optional built-in DA clients only for self-test and fault verification.
- A DA scenario with independently configurable tags.
- Separate DA traffic mix/rate because DA groups and callbacks do not map one-to-one to UA subscriptions.

Exit: a timed DA scenario reports Brabo.io-facing throughput and errors and stops cleanly.

### Phase 4: hardening and release

Deliverables:

- DCOM deployment guide for the supported Brabo.io topology.
- Image upgrade/rollback tests, process recovery, and least-privilege identity.
- Load, soak, reconnect, failure injection, and resource-leak tests.
- Support matrix and rollback procedure.

Exit: release criteria in sections 11 and 12 pass in the supported environment.

## 11. Test strategy

### Unit tests

- Stable ItemID generation, escaping, collision handling, and catalog generation.
- All scalar type conversions, bounds, overflow, and unsupported values.
- UA StatusCode to canonical quality to DA quality mapping.
- Timestamp UTC/FILETIME conversion.
- Write authorization and per-item result mapping.
- Queue bounding, batching, coalescing, replay prevention, and reconnect snapshots.

### Integration tests

- Python application plus an in-memory fake DA bridge on Linux CI.
- Ubuntu CI with the selected open-source stack and a reproducible container build.
- Brabo.io integration test for discovery/configuration, browse, reads, writes, and callbacks.
- Brabo.io connector bitness and topology compatibility tests where relevant.
- Python restart, DA provider restart, network partition, slow consumer, malformed write, and expired heartbeat.
- Generated DA tags with independently configured types, ItemIDs, patterns, quality, and timestamps.

### Performance tests

Measure at 100, 1000, and 5000 tags:

- Producer-to-DA callback latency percentiles.
- Reads and writes per second.
- Active clients, groups, and items.
- CPU, memory, handles, COM references, threads, queue depth, and dropped/coalesced updates.
- A soak of at least the intended production duration with repeated client reconnects.

Do not use this simulator's own virtual-client counters as proof of DA traffic delivery; instrument the DA provider and verify ingestion in Brabo.io.

## 12. Security and deployment checklist

- Support OPC-DA only on documented Ubuntu/container and Brabo.io connector versions proven by the feasibility spike.
- Use a dedicated least-privilege container/service identity.
- Configure DCOM security deliberately; do not weaken Brabo.io or host-wide security defaults to make a test pass.
- Restrict activation and access permissions to explicit principals where supported.
- Restrict firewall access to required client subnets and RPC endpoints.
- Keep Brabo.io connector hosts current because DCOM hardening changes are security-sensitive.
- Encrypt and mutually authenticate any cross-process bridge across hosts.
- Never expose the existing unauthenticated FastAPI control API to the same broad network as plant clients.
- Pin and scan container dependencies and log registration, activation, authorization, and configuration changes.
- Review open-source dependency and OPC Foundation specification/redistributable license terms before distribution. See the [OPC Foundation license portal](https://opcfoundation.org/license-agreement/).
- Validate production setup with the intended OPC client products; Classic interoperability often depends on client, bitness, identity, and DCOM topology.

## 13. Operational model

Recommended startup sequence:

1. Start the Linux DA provider; it becomes available but reports values Bad/Out-of-Service.
2. Start FastAPI and establish the authenticated bridge.
3. Send catalog and current-value snapshot.
4. Start the DA scenario; its tags change to Good values.
5. On simulator stop, retain last values but set quality to Out-of-Service, or remove the server according to the documented product policy.

Recommended failure behavior:

- Bridge disconnected: DA remains responsive from cache but changes item quality to Bad/Communication Failure after `stale_after_ms`.
- DA provider disconnected: other scenarios continue; Python reports DA degraded and bounds its outbound queue.
- Python restarted: DA rejects writes or returns an appropriate failure until catalog resynchronization completes.
- Catalog changed: increment catalog generation and rebuild DA browse state safely; if the chosen stack cannot update dynamically, document that provider restart is required.

## 14. Definition of done

OPC-DA support is complete only when:

- The selected open-source dependency and its license/maintenance decision are recorded.
- Supported DA version, Ubuntu image, Brabo.io connector, bitness, and DCOM topology are documented.
- The DA provider runs in the supported Ubuntu container without requiring commercial components.
- A DA scenario exposes its independently configured, stable tag catalog.
- Browse, read, write, group subscription, callback, quality, and timestamp behavior pass automated tests.
- Image deployment, registration, upgrade, rollback, and removal are repeatable.
- DCOM security tests pass against Brabo.io without disabling required platform hardening.
- Failure and reconnect behavior is observable and bounded.
- Load and soak targets pass with no unbounded memory, handle, thread, or COM reference growth.
- User, deployment, troubleshooting, and recovery documentation is published.

## 15. Recorded decision and conditions to resume

Recorded decisions:

1. The application generates protocol traffic for Brabo.io to consume.
2. Protocols and their tag sets are independently configurable.
3. Commercial SDKs and gateways should be avoided.
4. Ubuntu 22.04 or a similar Linux container is the supported deployment.
5. Formal OPC certification is not required.

OPC-DA work resumes only if all of the following are provided:

1. The exact Brabo.io OPC-DA connector, DA version, bitness, and connection topology.
2. A time-boxed open-source feasibility spike is approved.
3. The candidate runs on Ubuntu containers, or a Windows sidecar becomes an accepted platform exception.
4. Browse, read, write, subscription, quality, timestamp, reconnect, and sustained-load tests pass against Brabo.io.

Until then, prioritize OPC-UA, Modbus TCP, and MQTT/Sparkplug B. Do not advertise OPC-DA as supported.
