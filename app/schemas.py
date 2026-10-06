from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

PatternType = Literal[
    "random", "sine", "sawtooth", "random_walk", "burst",
    "constant", "sinusoid", "square", "triangle", "expression", "counter",
]


class NodePatternConfig(BaseModel):
    pattern: PatternType = "random"
    # optional range override for legacy patterns (falls back to global min/max_value)
    min_value: float | None = None
    max_value: float | None = None
    # constant
    constant_value: float = 0.0
    # sinusoid:  amplitude * sin(2π*(t - time_offset_s) / period_s) + value_offset
    amplitude: float = 1.0
    value_offset: float = 0.0
    period_s: float = Field(default=30.0, gt=0.0)
    time_offset_s: float = 0.0
    # square wave
    square_low: float = 0.0
    square_high: float = 1.0
    square_period_s: float = Field(default=30.0, gt=0.0)
    square_duty: float = Field(default=0.5, ge=0.0, le=1.0)
    # triangle wave
    triangle_min: float = 0.0
    triangle_max: float = 1.0
    triangle_period_s: float = Field(default=30.0, gt=0.0)
    # expression: formula string + symbol → PatternType mapping
    expression: str = "0"
    symbols: dict[str, PatternType] = Field(default_factory=dict)
    # counter
    counter_min: float = 0.0
    counter_max: float = 100.0
    counter_step: float = Field(default=1.0, gt=0.0)
    counter_direction: Literal["up", "down"] = "up"


class SimulatorConfig(BaseModel):
    endpoint: str = "opc.tcp://0.0.0.0:4840/freeopcua/server/"
    server_hostname: str = "localhost"
    namespace_uri: str = "http://example.org/opcua/simulator"
    source_mode: Literal["xml", "manual"] = "xml"
    namespace_nodeset_file: str | None = None
    node_count: int = Field(default=100, ge=1, le=5000)
    update_interval_ms: int = Field(default=1000, ge=10, le=10000)
    jitter_ms: int = Field(default=0, ge=0, le=2000)

    pattern: PatternType = "random"
    min_value: float = 0.0
    max_value: float = 100.0
    noise_amplitude: float = Field(default=1.0, ge=0.0, le=1000.0)
    burst_probability: float = Field(default=0.07, ge=0.0, le=1.0)
    burst_multiplier: float = Field(default=2.5, ge=1.0, le=20.0)

    test_duration_minutes: float = Field(default=0.0, ge=0.0, le=1440.0)

    # per-node pattern overrides, keyed by browse name (e.g. "Temperature", "Tag0042")
    node_overrides: dict[str, NodePatternConfig] = Field(default_factory=dict)

    verbose_events: bool = True
    include_tracebacks: bool = True

    seed: int = Field(default=42, ge=0, le=2_147_483_647)

    @model_validator(mode="after")
    def validate_ranges(self) -> "SimulatorConfig":
        if self.source_mode == "manual" and self.max_value <= self.min_value:
            raise ValueError("max_value must be greater than min_value")
        return self


class StartResponse(BaseModel):
    success: bool
    message: str


class NamespaceInfo(BaseModel):
    active_file: str | None
    active_file_name: str | None
    has_uploaded_file: bool
    configured_file: str | None
    namespace_uri: str


class SimulatorStatus(BaseModel):
    running: bool
    server_started: bool
    start_time: str | None
    uptime_seconds: float
    run_duration_target_seconds: float
    remaining_seconds: float
    active_protocols: list[str]
    endpoint: str


class SimulatorMetrics(BaseModel):
    updates_per_second: float
    errors: int
    node_updates: int
    timeline: list[dict[str, float | int | str]]


class EventRecord(BaseModel):
    ts: str
    level: str
    message: str
