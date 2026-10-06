# Configuring tags and simulation rules

## XML and JSON have separate roles

| XML NodeSet | Embedded JSON |
| --- | --- |
| Creates folders and tags | Chooses value-generation patterns |
| Defines NodeId, BrowseName and data type | Sets formula parameters and counter limits |
| Supplies initial values, units and engineering ranges | Sets producer timing and generation defaults |

The current XML workflow uploads **one XML file containing both parts**. It does
not upload standalone JSON or create arbitrary XML-defined tags from a JSON file.
The manual API accepts JSON for generated tags, as shown below.

## How a JSON rule links to an XML tag

An XML tag with `BrowseName="1:ProductionCount"` links to the exact, case-sensitive
JSON key `"ProductionCount"` under `node_overrides`. The namespace prefix `1:` is
removed for this lookup. The key is not the NodeId or DisplayName. Use unique
BrowseName names across data tags so rules are unambiguous. A rule referencing a
tag absent from the XML is rejected.

For example:

```json
{
  "update_interval_ms": 1000,
  "jitter_ms": 0,
  "node_overrides": {
    "ProductionCount": {
      "pattern": "counter",
      "counter_min": 0,
      "counter_max": 10,
      "counter_step": 1,
      "counter_direction": "up"
    }
  }
}
```

Place this JSON inside an XML comment marked `SIMULATOR CONFIG`. Use one such
block per file. Ordinary XML descriptions and explanatory comments are not parsed
as simulation rules. JSON uses double quotes and cannot contain JSON comments or
trailing commas.

## Complete uploadable XML example

Save this as `counter_demo.xml`, then upload it in the **XML file** tab. It creates
one Int64 tag under Objects → CounterDemo and automatically applies its rule.

```xml
<?xml version="1.0" encoding="utf-8"?>
<UANodeSet
    xmlns="http://opcfoundation.org/UA/2011/03/UANodeSet.xsd"
    xmlns:uax="http://opcfoundation.org/UA/2008/02/Types.xsd">
  <NamespaceUris>
    <Uri>urn:simulation:counter-demo</Uri>
  </NamespaceUris>
  <Aliases>
    <Alias Alias="Int64">i=8</Alias>
    <Alias Alias="HasTypeDefinition">i=40</Alias>
    <Alias Alias="Organizes">i=35</Alias>
    <Alias Alias="HasComponent">i=47</Alias>
    <Alias Alias="FolderType">i=61</Alias>
    <Alias Alias="BaseDataVariableType">i=63</Alias>
  </Aliases>
  <UAObject NodeId="ns=1;i=1000" BrowseName="1:CounterDemo">
    <DisplayName>CounterDemo</DisplayName>
    <References>
      <Reference ReferenceType="HasTypeDefinition">FolderType</Reference>
      <Reference ReferenceType="Organizes" IsForward="false">i=85</Reference>
    </References>
  </UAObject>
  <UAVariable NodeId="ns=1;i=1013" BrowseName="1:ProductionCount"
              DataType="Int64" ValueRank="-1" AccessLevel="3"
              UserAccessLevel="3" MinimumSamplingInterval="1000">
    <DisplayName>ProductionCount</DisplayName>
    <Description>Counter from 0 to 10, incrementing each simulator tick.</Description>
    <References>
      <Reference ReferenceType="HasTypeDefinition">BaseDataVariableType</Reference>
      <Reference ReferenceType="HasComponent" IsForward="false">ns=1;i=1000</Reference>
    </References>
    <Value><uax:Int64>0</uax:Int64></Value>
  </UAVariable>
</UANodeSet>
<!--
SIMULATOR CONFIG
{
  "update_interval_ms": 1000,
  "jitter_ms": 0,
  "node_overrides": {
    "ProductionCount": {
      "pattern": "counter",
      "counter_min": 0,
      "counter_max": 10,
      "counter_step": 1,
      "counter_direction": "up"
    }
  }
}
-->
```

The XML initial value is 0. The first producer tick increments to 1, followed by
2 through 10, then 0, repeating. Change `counter_max` to `999999` for the production
example. At one tick per second, it takes approximately 11.6 days to wrap.

`counter_step` must be positive. Direction can be `up` or `down`. Counter state
starts at `counter_min` on a new run; for an up-counter, align the XML initial value
with that minimum. The rule does not pause based on another tag.

The namespace index in a client may differ from the XML's index after import.
Use the live table's NodeId or browse the server to locate the imported node.

## JSON example for the bundled five-tag XML

Replace the existing SIMULATOR CONFIG block in `config_data.xml` with the following
JSON to configure all five existing tags. Keep their XML definitions.

```json
{
  "update_interval_ms": 1000,
  "jitter_ms": 0,
  "node_overrides": {
    "Temperature": {
      "pattern": "sinusoid",
      "amplitude": 3,
      "value_offset": 135,
      "period_s": 10,
      "time_offset_s": 0
    },
    "Pressure": {
      "pattern": "sinusoid",
      "amplitude": 1,
      "value_offset": -11,
      "period_s": 15
    },
    "MotorRunning": {
      "pattern": "square",
      "square_low": 0,
      "square_high": 1,
      "square_period_s": 600,
      "square_duty": 0.5
    },
    "ProductionCount": {
      "pattern": "counter",
      "counter_min": 0,
      "counter_max": 999999,
      "counter_step": 1,
      "counter_direction": "up"
    },
    "SpeedSetpoint": {
      "pattern": "constant",
      "constant_value": 3
    }
  }
}
```

Temperature follows `135 + 3 sin(2πt/10)`. Pressure follows
`-11 + sin(2πt/15)`. MotorRunning is true for the first 300 seconds of each
600-second cycle and false for the next 300. Boolean conversion uses a threshold
of 0.5. SpeedSetpoint remains 3. Counter parameters apply per producer tick, not
per client read or subscription update.

## Supported per-tag patterns

| Pattern | Main parameters |
| --- | --- |
| `constant` | `constant_value` |
| `sinusoid` | `amplitude`, `value_offset`, `period_s`, `time_offset_s` |
| `square` | `square_low`, `square_high`, `square_period_s`, `square_duty` |
| `triangle` | `triangle_min`, `triangle_max`, `triangle_period_s` |
| `counter` | `counter_min`, `counter_max`, `counter_step`, `counter_direction` |
| `random`, `sine`, `sawtooth`, `random_walk`, `burst` | Optional `min_value`, `max_value`; global generation defaults |
| `expression` | `expression`, `symbols` mapping symbol names to pattern names |

Prefer explicit per-tag rules for process signals. Expression symbols generate
pattern values; they do not reference live tags such as MotorRunning and do not
implement conditional counter gating.

## Timing, ranges and precedence

- `update_interval_ms` controls the common producer tick; supported values are
  10–10000 ms. Default: 1000 ms.
- `jitter_ms` varies timing around that interval. Default: 0. Leave at 0 for a
  regular counter tick.
- XML `MinimumSamplingInterval` describes client sampling metadata; it does not
  control the producer's update rate.
- XML `EURange`, or `InstrumentRange` as fallback, bounds numeric initial values
  and producer writes. Supported paired Min/Max properties also bound writes.
  Set formulas consistent with the XML range to avoid clipping.
- Per-tag JSON rules take precedence over the XML block's global `pattern`.
  A global pattern applies to numeric tags lacking per-tag rules. Without either,
  initial values are held. Manual-form generation settings never affect XML mode.
- The embedded block also accepts global `min_value`, `max_value`, `noise_amplitude`,
  `burst_probability`, `burst_multiplier`, and `seed`. XML mode defaults to zero
  noise. Global noise applies to the legacy random/sine/sawtooth/random-walk/burst
  patterns, not explicit constant/sinusoid/square/triangle/counter patterns.
- External client writes are not constrained by producer range checks. The next
  producer tick may overwrite them with a generated value.

Review the preview before starting: it shows parsed rules, parameters and timing.
Stop, edit/re-upload the XML, review the new preview, then start another run to
apply changes. Uploading or changing the source while running is rejected.

## Manual configuration through JSON

The REST API can configure generated tags without XML. Save this as `manual.json`:

```json
{
  "source_mode": "manual",
  "node_count": 5,
  "namespace_uri": "urn:simulation:manual-demo",
  "pattern": "random",
  "min_value": 20,
  "max_value": 30,
  "noise_amplitude": 0,
  "update_interval_ms": 1000,
  "jitter_ms": 0,
  "endpoint": "opc.tcp://0.0.0.0:4840/freeopcua/server/",
  "server_hostname": "localhost"
}
```

Apply it while stopped, review the preview, and start:

```bash
curl -X PUT http://localhost:8000/api/simulator/config \
  -H 'Content-Type: application/json' --data-binary @manual.json
curl http://localhost:8000/api/simulator/tags
curl -X POST http://localhost:8000/api/simulator/start
```

This creates five Double tags under SimulatedDevice with random values between
20 and 30. A PUT replaces the configuration; omitted fields take their defaults.

To return to the bundled XML source:

```bash
curl -X POST http://localhost:8000/api/simulator/stop
curl -X PUT http://localhost:8000/api/simulator/config \
  -H 'Content-Type: application/json' --data-binary '{"source_mode":"xml"}'
```

For XML mode, put tag rules inside the selected XML. Sending manual generation
settings or node_overrides to the run-config API does not replace its embedded
file rules. Connection settings and run duration still apply to either mode.
