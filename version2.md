# Version 2 — Change Summary & Usage Guide

## What Changed

### Bug Fix: XML-Imported UAVariable Nodes Not Updating

**Problem:** UAVariable nodes loaded from an XML NodeSet file received their initial value at import time and then froze. The producer loop only iterated over the dynamically generated `Tag0000..TagNNNN` nodes; XML-imported nodes were never written to again.

**Fix:** After the OPC-UA server starts, the simulator now browses the server tree and discovers all UAVariable nodes from imported namespaces (namespace index > 1). These nodes are added to the update loop alongside the Tag nodes. Their OPC-UA data type (Boolean, Int32, Double, etc.) is read at discovery time so values are cast correctly on every write.

---

### Feature: Per-Variable Pattern Overrides

Previously, a single global `pattern` setting applied identically to every node. Nodes can now each have their own pattern and parameters via the `node_overrides` config field.

---

### Feature: Six New Signal Patterns

In addition to the five existing patterns (`random`, `sine`, `sawtooth`, `random_walk`, `burst`), six new patterns are available:

| Pattern      | Description |
|--------------|-------------|
| `constant`   | Emits a fixed value on every tick. |
| `sinusoid`   | Full sine wave with configurable amplitude, period, value offset, and time offset. |
| `square`     | Alternates between a low and high value at a configurable period and duty cycle. |
| `triangle`   | Linear ramp up then ramp down, repeating at a configurable period. |
| `expression` | Evaluates a user-supplied math formula. Variables in the formula are each assigned their own pattern. |
| `counter`    | Increments (or decrements) by a fixed step, wrapping at min/max bounds. |

---

## API Changes

### `GET /api/simulator/config` and `PUT /api/simulator/config`

The config schema now includes two additions:

**Extended `pattern` field** — accepts all 11 pattern names as the global default.

**New `node_overrides` field** — a dictionary keyed by node browse name. Each entry is a `NodePatternConfig` object that overrides the global pattern for that specific node. Nodes not listed here continue to use the global `pattern`.

---

## NodePatternConfig Fields

All fields are optional and have sensible defaults. Only the fields relevant to the chosen `pattern` need to be set.

| Field               | Type              | Default  | Used by |
|---------------------|-------------------|----------|---------|
| `pattern`           | PatternType       | `random` | all |
| `min_value`         | float \| null     | null     | legacy patterns (overrides global) |
| `max_value`         | float \| null     | null     | legacy patterns (overrides global) |
| `constant_value`    | float             | `0.0`    | `constant` |
| `amplitude`         | float             | `1.0`    | `sinusoid` |
| `value_offset`      | float             | `0.0`    | `sinusoid` |
| `period_s`          | float > 0         | `30.0`   | `sinusoid` |
| `time_offset_s`     | float             | `0.0`    | `sinusoid` |
| `square_low`        | float             | `0.0`    | `square` |
| `square_high`       | float             | `1.0`    | `square` |
| `square_period_s`   | float > 0         | `30.0`   | `square` |
| `square_duty`       | float [0.0–1.0]   | `0.5`    | `square` |
| `triangle_min`      | float             | `0.0`    | `triangle` |
| `triangle_max`      | float             | `1.0`    | `triangle` |
| `triangle_period_s` | float > 0         | `30.0`   | `triangle` |
| `expression`        | string            | `"0"`    | `expression` |
| `symbols`           | dict[str, PatternType] | `{}` | `expression` |
| `counter_min`       | float             | `0.0`    | `counter` |
| `counter_max`       | float             | `100.0`  | `counter` |
| `counter_step`      | float > 0         | `1.0`    | `counter` |
| `counter_direction` | `"up"` \| `"down"` | `"up"` | `counter` |

---

## Pattern Details

### `constant`
Returns `constant_value` on every tick. Useful for simulating a sensor stuck at a known reading.

```json
{ "pattern": "constant", "constant_value": 42.0 }
```

### `sinusoid`
`amplitude × sin(2π × (t − time_offset_s) / period_s) + value_offset`

The output is not clamped, so it can go negative or exceed typical ranges — size amplitude and offset to suit your target range.

```json
{
  "pattern": "sinusoid",
  "amplitude": 10.0,
  "value_offset": 25.0,
  "period_s": 60.0,
  "time_offset_s": 0.0
}
```

### `square`
Switches between `square_low` and `square_high`. Spends `square_duty × 100%` of each period at the high value.

```json
{
  "pattern": "square",
  "square_low": 0.0,
  "square_high": 1.0,
  "square_period_s": 10.0,
  "square_duty": 0.5
}
```

### `triangle`
Linearly rises from `triangle_min` to `triangle_max` then falls back, repeating each `triangle_period_s` seconds.

```json
{
  "pattern": "triangle",
  "triangle_min": 0.0,
  "triangle_max": 100.0,
  "triangle_period_s": 30.0
}
```

### `expression`
Evaluates a math formula each tick. Symbols are defined in the `symbols` dict; each is resolved using its assigned sub-pattern (any pattern except `expression`).

Supported operators: `+ − * / // % **`
Supported functions: `sin cos tan sqrt abs floor ceil log exp min max`
Supported constants: `pi e`

```json
{
  "pattern": "expression",
  "expression": "a * sin(2 * pi * t) + b",
  "symbols": {
    "a": "random",
    "b": "random_walk",
    "t": "sawtooth"
  }
}
```

Symbol values are generated using global min/max and the global pattern parameters (noise, burst probability, etc.).

### `counter`
Increments (or decrements) by `counter_step` each tick. Wraps back to `counter_min` when it exceeds `counter_max` (or to `counter_max` when going below `counter_min`).

```json
{
  "pattern": "counter",
  "counter_min": 0,
  "counter_max": 500,
  "counter_step": 1,
  "counter_direction": "up"
}
```

---

## Usage Examples

### Example 1 — XML namespace variables with individual patterns

Given an uploaded XML NodeSet that defines `Temperature`, `Pressure`, `MotorRunning`, `ProductionCount`, and `SpeedSetpoint`:

```json
PUT /api/simulator/config
{
  "pattern": "random",
  "node_overrides": {
    "Temperature": {
      "pattern": "sinusoid",
      "amplitude": 8.0,
      "value_offset": 23.0,
      "period_s": 120.0
    },
    "Pressure": {
      "pattern": "random_walk",
      "min_value": 3.0,
      "max_value": 7.0
    },
    "MotorRunning": {
      "pattern": "square",
      "square_low": 0.0,
      "square_high": 1.0,
      "square_period_s": 60.0,
      "square_duty": 0.8
    },
    "ProductionCount": {
      "pattern": "counter",
      "counter_min": 0,
      "counter_max": 9999,
      "counter_step": 1,
      "counter_direction": "up"
    },
    "SpeedSetpoint": {
      "pattern": "constant",
      "constant_value": 75.0
    }
  }
}
```

### Example 2 — Generated Tag nodes with per-node overrides

```json
PUT /api/simulator/config
{
  "node_count": 10,
  "pattern": "random",
  "node_overrides": {
    "Tag0000": {
      "pattern": "triangle",
      "triangle_min": 0.0,
      "triangle_max": 100.0,
      "triangle_period_s": 20.0
    },
    "Tag0001": {
      "pattern": "counter",
      "counter_min": 0,
      "counter_max": 100,
      "counter_step": 5,
      "counter_direction": "up"
    },
    "Tag0002": {
      "pattern": "expression",
      "expression": "a + b + 2",
      "symbols": { "a": "random", "b": "random" }
    }
  }
}
```

Tags not listed in `node_overrides` (`Tag0003` through `Tag0009`) continue to use the global `"random"` pattern.

### Example 3 — Mixed: global sinusoid with one constant override

```json
PUT /api/simulator/config
{
  "pattern": "sinusoid",
  "node_overrides": {
    "Tag0000": {
      "pattern": "constant",
      "constant_value": 0.0
    }
  }
}
```

All nodes use sinusoid except `Tag0000`, which is pinned to `0.0`.

---

## Notes

- Node browse names are **case-sensitive** (`"Temperature"` not `"temperature"`).
- XML node browse names are logged at startup when the NodeSet is imported, e.g.:
  `Discovered 5 UAVariable node(s) from imported XML NodeSet for simulation: Temperature, Pressure, MotorRunning, ProductionCount, SpeedSetpoint`
- Generated Tag nodes are named `Tag0000`, `Tag0001`, …, `Tag{N-1:04d}`.
- The `expression` evaluator does not support nested `expression` symbols — each symbol must use a non-expression pattern.
- `sinusoid`, `square`, `triangle`, and `constant` do **not** apply global `noise_amplitude` jitter. Legacy patterns (`random`, `sine`, `sawtooth`, `random_walk`, `burst`) still do.
- The `counter` pattern uses the same internal state store as `random_walk`; each node tracks its own counter independently.
