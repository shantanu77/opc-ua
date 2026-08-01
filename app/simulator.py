from __future__ import annotations

import ast
import asyncio
import math
import operator as _op
import os
import random
import tempfile
import traceback
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from asyncua import Client, Server, ua

from .schemas import EventRecord, NodePatternConfig, SimulatorConfig, SimulatorMetrics, SimulatorStatus


_EXPR_BINARY_OPS: dict = {
    ast.Add: _op.add,
    ast.Sub: _op.sub,
    ast.Mult: _op.mul,
    ast.Div: _op.truediv,
    ast.FloorDiv: _op.floordiv,
    ast.Mod: _op.mod,
    ast.Pow: _op.pow,
}
_EXPR_UNARY_OPS: dict = {ast.USub: _op.neg, ast.UAdd: _op.pos}
_EXPR_FUNCS: dict = {
    "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "sqrt": math.sqrt, "abs": abs, "floor": math.floor,
    "ceil": math.ceil, "log": math.log, "exp": math.exp,
    "min": min, "max": max,
}
_EXPR_CONSTS: dict = {"pi": math.pi, "e": math.e}


def _eval_ast_node(node: ast.expr, variables: dict[str, float]) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.Name):
        if node.id in variables:
            return variables[node.id]
        if node.id in _EXPR_CONSTS:
            return _EXPR_CONSTS[node.id]
        raise ValueError(f"Unknown symbol: {node.id!r}")
    if isinstance(node, ast.BinOp):
        fn = _EXPR_BINARY_OPS.get(type(node.op))
        if fn is None:
            raise ValueError(f"Unsupported operator: {type(node.op).__name__}")
        return fn(_eval_ast_node(node.left, variables), _eval_ast_node(node.right, variables))
    if isinstance(node, ast.UnaryOp):
        fn = _EXPR_UNARY_OPS.get(type(node.op))
        if fn is None:
            raise ValueError(f"Unsupported unary op: {type(node.op).__name__}")
        return fn(_eval_ast_node(node.operand, variables))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        fn = _EXPR_FUNCS.get(node.func.id)
        if fn is None:
            raise ValueError(f"Unknown function: {node.func.id!r}")
        return float(fn(*[_eval_ast_node(a, variables) for a in node.args]))
    raise ValueError(f"Unsupported expression construct: {type(node).__name__}")


def _safe_eval_expr(expr_str: str, variables: dict[str, float]) -> float:
    try:
        tree = ast.parse(expr_str.strip(), mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"Invalid expression syntax: {exc}") from exc
    return float(_eval_ast_node(tree.body, variables))


@dataclass
class Counters:
    total_operations: int = 0
    errors: int = 0
    node_updates: int = 0
    read_ops: int = 0
    write_ops: int = 0
    browse_ops: int = 0
    subscribe_ops: int = 0


class _SubscriptionHandler:
    def datachange_notification(self, node: Any, val: Any, data: Any) -> None:
        return

    def event_notification(self, event: Any) -> None:
        return


class OPCUASimulator:
    def __init__(self) -> None:
        self._config = SimulatorConfig()
        self._server: Server | None = None
        self._variables: list[Any] = []
        self._variable_names: list[str] = []
        self._xml_variables: list[tuple[Any, ua.VariantType, str]] = []
        self._node_ids: list[str] = []
        self._node_variant_types: dict[str, ua.VariantType] = {}
        self._namespace_index: int | None = None

        self._running = False
        self._server_started = False
        self._start_time: datetime | None = None

        self._lock = asyncio.Lock()
        self._stop_event = asyncio.Event()

        self._producer_task: asyncio.Task[None] | None = None
        self._metrics_task: asyncio.Task[None] | None = None
        self._client_tasks: list[asyncio.Task[None]] = []

        self._counters = Counters()
        self._timeline: deque[dict[str, float | int | str]] = deque(maxlen=300)
        self._events: deque[EventRecord] = deque(maxlen=2000)

        self._rng = random.Random(self._config.seed)
        self._walk_values: dict[int, float] = {}
        self._auto_stop_triggered = False

    def _utc_now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _log(self, message: str, level: str = "INFO") -> None:
        self._events.append(
            EventRecord(ts=self._utc_now().isoformat(), level=level, message=message)
        )

    def _log_exception(self, context: str, exc: Exception) -> None:
        message = f"{context}: {exc}"
        if self._config.include_tracebacks:
            message = f"{message}\n{traceback.format_exc()}"
        self._log(message, level="ERROR")

    def _resolve_nodeset_file(self) -> Path | None:
        configured = (self._config.namespace_nodeset_file or "").strip()
        candidates: list[Path] = []
        if configured:
            candidate = Path(configured)
            if not candidate.is_absolute():
                candidate = Path.cwd() / candidate
            candidates.append(candidate)

        candidates.extend(
            [
                Path.cwd() / "uploaded_namespace.xml",
                Path.cwd() / "opcua_simulation_namespace 2.xml",
                Path.cwd() / "opcua_simulation_namespace.xml",
                Path.cwd() / "namespace.xml",
            ]
        )

        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return candidate
        return None

    def _create_nodeset_compat_file(self, source_file: Path) -> Path | None:
        try:
            content = source_file.read_text(encoding="utf-8")
        except Exception:
            return None

        namespace_uri_count = content.count("<Uri>")
        needs_shift = ('ns=2;' in content) or ('BrowseName="2:' in content)
        if namespace_uri_count != 1 or not needs_shift:
            return None

        marker = "<NamespaceUris>"
        if marker not in content:
            return None

        compat_uri = "    <Uri>urn:opcua:compat:ns1</Uri>\n"
        patched = content.replace(marker, f"{marker}\n{compat_uri}", 1)
        fd, temp_path = tempfile.mkstemp(prefix="opcua_nodeset_compat_", suffix=".xml")
        os.close(fd)
        with Path(temp_path).open("w", encoding="utf-8") as handle:
            handle.write(patched)
        Path(temp_path).chmod(0o600)
        return Path(temp_path)

    def get_config(self) -> SimulatorConfig:
        return self._config

    def _uptime_seconds(self) -> float:
        if not self._start_time or not self._running:
            return 0.0
        return (self._utc_now() - self._start_time).total_seconds()

    def _run_duration_target_seconds(self) -> float:
        return max(0.0, self._config.test_duration_minutes * 60.0)

    def _current_client_ops_per_sec(self, uptime_seconds: float | None = None) -> float:
        cfg = self._config
        base = max(0.1, cfg.client_ops_per_sec)
        uptime = self._uptime_seconds() if uptime_seconds is None else max(0.0, uptime_seconds)

        if cfg.load_profile == "constant":
            return base

        if cfg.load_profile == "linear_ramp":
            ramp_s = max(1e-6, cfg.ramp_duration_minutes * 60.0)
            progress = min(1.0, uptime / ramp_s)
            return base + (cfg.ramp_target_ops_per_sec - base) * progress

        if cfg.load_profile == "step_ramp":
            direction = 1.0 if cfg.ramp_target_ops_per_sec >= base else -1.0
            steps = math.floor(uptime / cfg.step_interval_seconds)
            candidate = base + (steps * cfg.step_increment_ops_per_sec * direction)
            if direction > 0:
                return min(cfg.ramp_target_ops_per_sec, candidate)
            return max(cfg.ramp_target_ops_per_sec, candidate)

        if cfg.load_profile == "spike_wave":
            spike_window = max(1.0, min(20.0, cfg.spike_every_seconds * 0.2))
            in_spike = (uptime % cfg.spike_every_seconds) < spike_window
            return base * cfg.spike_multiplier if in_spike else base

        return base

    async def update_config(self, config: SimulatorConfig) -> None:
        async with self._lock:
            if self._running:
                raise RuntimeError("Cannot update configuration while simulator is running")
            self._config = config
            self._rng.seed(self._config.seed)
            self._walk_values.clear()
            self._log(
                "Configuration updated "
                f"(endpoint={self._config.endpoint}, namespace_uri={self._config.namespace_uri}, "
                f"nodeset_file={self._config.namespace_nodeset_file or 'auto'})"
            )

    async def start(self) -> None:
        async with self._lock:
            if self._running:
                if self._config.verbose_events:
                    self._log("Start requested but simulator is already running", level="WARN")
                return

            self._stop_event.clear()
            self._counters = Counters()
            self._timeline.clear()
            self._events.clear()
            self._walk_values.clear()
            self._rng.seed(self._config.seed)
            self._auto_stop_triggered = False

            if self._config.verbose_events:
                self._log(
                    "Starting simulator "
                    f"(endpoint={self._config.endpoint}, namespace_uri={self._config.namespace_uri}, "
                    f"node_count={self._config.node_count}, virtual_clients={self._config.virtual_clients})"
                )

            await self._setup_server()

            self._running = True
            self._start_time = self._utc_now()

            self._producer_task = asyncio.create_task(self._producer_loop(), name="producer-loop")
            self._metrics_task = asyncio.create_task(self._metrics_loop(), name="metrics-loop")
            self._client_tasks = [
                asyncio.create_task(self._client_loop(client_id), name=f"client-loop-{client_id}")
                for client_id in range(self._config.virtual_clients)
            ]
            self._log(
                f"Simulator started with {self._config.node_count} nodes and {self._config.virtual_clients} virtual clients"
            )

    async def stop(self) -> None:
        async with self._lock:
            if not self._running and not self._server_started:
                return

            if self._config.verbose_events:
                self._log("Stopping simulator")

            self._stop_event.set()

            tasks: list[asyncio.Task[None]] = []
            if self._producer_task is not None:
                tasks.append(self._producer_task)
            if self._metrics_task is not None:
                tasks.append(self._metrics_task)
            tasks.extend(self._client_tasks)

            for task in tasks:
                task.cancel()

            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
                if self._config.verbose_events:
                    self._log(f"Cancelled {len(tasks)} simulator tasks")

            self._producer_task = None
            self._metrics_task = None
            self._client_tasks.clear()

            if self._server is not None:
                try:
                    await self._server.stop()
                except Exception as exc:  # noqa: BLE001
                    self._log_exception("Error stopping OPC-UA server", exc)

            self._server = None
            self._variables = []
            self._variable_names = []
            self._xml_variables = []
            self._node_ids = []
            self._node_variant_types = {}
            self._namespace_index = None
            self._server_started = False
            self._running = False
            self._log("Simulator stopped")

    async def _setup_server(self) -> None:
        self._server = Server()
        await self._server.init()
        self._server.set_endpoint(self._config.endpoint)
        self._server.set_server_name("OPC UA Traffic Simulator")

        if self._config.verbose_events:
            self._log("OPC-UA server initialized")

        # Advertise a 1-hour MaxSessionTimeout so external clients with long
        # poll intervals are not prematurely dropped with Bad_SessionClosed.
        # OPC-UA standard node ns=0;i=2074 is Server_ServerCapabilities_MaxSessionTimeout.
        try:
            max_timeout_node = self._server.get_node("ns=0;i=2074")
            await max_timeout_node.write_value(ua.Variant(3_600_000.0, ua.VariantType.Double))
            if self._config.verbose_events:
                self._log("Set ServerCapabilities.MaxSessionTimeout to 3600000ms")
        except Exception:  # noqa: BLE001
            if self._config.verbose_events:
                self._log(
                    "Could not set MaxSessionTimeout capability node; server default timeout remains",
                    level="WARN",
                )

        nodeset_file = self._resolve_nodeset_file()
        if nodeset_file is not None:
            try:
                await self._server.import_xml(str(nodeset_file))
                self._log(f"Imported NodeSet XML: {nodeset_file}")
            except Exception as exc:  # noqa: BLE001
                if "Namespace index" in str(exc) and "is not defined in xml" in str(exc):
                    compat_file = self._create_nodeset_compat_file(nodeset_file)
                    if compat_file is not None:
                        self._log(
                            "NodeSet namespace-index mismatch detected; retrying import with compatibility patch",
                            level="WARN",
                        )
                        try:
                            await self._server.import_xml(str(compat_file))
                            self._log(
                                f"Imported NodeSet XML with compatibility patch: {nodeset_file}"
                            )
                        except Exception as retry_exc:  # noqa: BLE001
                            self._log_exception(
                                f"Failed compatibility import for NodeSet XML '{nodeset_file}'",
                                retry_exc,
                            )
                        finally:
                            try:
                                compat_file.unlink(missing_ok=True)
                            except Exception:
                                pass
                    else:
                        self._log_exception(f"Failed to import NodeSet XML '{nodeset_file}'", exc)
                else:
                    self._log_exception(f"Failed to import NodeSet XML '{nodeset_file}'", exc)
        elif self._config.verbose_events:
            self._log(
                "No NodeSet XML found. Using generated SimulatedDevice namespace only",
                level="WARN",
            )

        self._namespace_index = await self._server.register_namespace(self._config.namespace_uri)
        objects = self._server.nodes.objects
        folder = await objects.add_folder(self._namespace_index, "SimulatedDevice")

        self._variables = []
        self._variable_names = []
        self._node_ids = []
        self._node_variant_types = {}
        for i in range(self._config.node_count):
            node_name = f"Tag{i:04d}"
            node = await folder.add_variable(self._namespace_index, node_name, 0.0)
            await node.set_writable()
            self._variables.append(node)
            self._variable_names.append(node_name)
            nid_str = node.nodeid.to_string()
            self._node_ids.append(nid_str)
            self._node_variant_types[nid_str] = ua.VariantType.Double

        await self._server.start()
        self._server_started = True

        # When bound to 0.0.0.0, OPC-UA clients receive "0.0.0.0" as the
        # endpoint hostname in the GetEndpoints response and cannot use it as
        # a destination address.  Patch the in-memory endpoint list that
        # asyncua returns to clients with the configured server_hostname.
        if "0.0.0.0" in self._config.endpoint:
            self._patch_advertised_hostname(self._config.server_hostname)

        await self._collect_xml_variables()

        if self._config.verbose_events:
            self._log("OPC-UA server started and endpoint is listening")

    def _patch_advertised_hostname(self, hostname: str) -> None:
        try:
            endpoints = getattr(self._server.iserver, "endpoints", [])
            patched = 0
            for ep in endpoints:
                url = getattr(ep, "EndpointUrl", "") or ""
                if "0.0.0.0" in url:
                    ep.EndpointUrl = url.replace("0.0.0.0", hostname)
                    patched += 1
            if patched:
                self._log(f"Patched {patched} endpoint URL(s) to advertise hostname '{hostname}'")
            else:
                self._log(
                    "No endpoint URLs contained 0.0.0.0 to patch; clients may see an unreachable address",
                    level="WARN",
                )
        except Exception as exc:  # noqa: BLE001
            self._log_exception("Could not patch advertised endpoint hostname", exc)

    async def _collect_xml_variables(self) -> None:
        """Browse the server tree for UAVariable nodes from imported XML namespaces.

        These nodes are not in self._variables (which only holds the generated Tag nodes),
        so without this step they would keep their XML-defined initial value forever.
        """
        xml_vars: list[tuple[Any, ua.VariantType, str]] = []
        node_id_set = set(self._node_ids)

        async def _browse(node: Any, depth: int) -> None:
            if depth > 6:
                return
            try:
                children = await node.get_children()
            except Exception:
                return
            for child in children:
                if child.nodeid.NamespaceIndex <= 1:
                    # Skip all built-in OPC-UA server nodes (ns=0 and ns=1)
                    continue
                try:
                    nc = await child.read_node_class()
                except Exception:
                    continue
                nid_str = child.nodeid.to_string()
                if nc == ua.NodeClass.Variable:
                    if nid_str not in node_id_set:
                        try:
                            dv = await child.read_data_value()
                            vt = dv.Value.VariantType if dv.Value is not None else ua.VariantType.Double
                        except Exception:
                            vt = ua.VariantType.Double
                        try:
                            bn = await child.read_browse_name()
                            browse_name = bn.Name or nid_str
                        except Exception:
                            browse_name = nid_str
                        xml_vars.append((child, vt, browse_name))
                elif nc == ua.NodeClass.Object:
                    await _browse(child, depth + 1)

        try:
            await _browse(self._server.nodes.objects, 0)
            self._xml_variables = xml_vars
            for node, vt, _ in xml_vars:
                nid_str = node.nodeid.to_string()
                self._node_ids.append(nid_str)
                self._node_variant_types[nid_str] = vt
            if xml_vars:
                names = ", ".join(n for _, _, n in xml_vars)
                self._log(
                    f"Discovered {len(xml_vars)} UAVariable node(s) from imported XML NodeSet for simulation: {names}"
                )
        except Exception as exc:  # noqa: BLE001
            self._log_exception("Failed to collect XML namespace variables", exc)
            self._xml_variables = []

    def _cast_to_variant_type(self, value: float, vtype: ua.VariantType) -> Any:
        if vtype == ua.VariantType.Boolean:
            return value >= 0.5
        if vtype in (
            ua.VariantType.SByte,
            ua.VariantType.Byte,
            ua.VariantType.Int16,
            ua.VariantType.UInt16,
            ua.VariantType.Int32,
            ua.VariantType.UInt32,
            ua.VariantType.Int64,
            ua.VariantType.UInt64,
        ):
            return int(round(value))
        if vtype == ua.VariantType.Float:
            return float(value)
        return value

    def _pattern_value(self, index: int, elapsed_s: float, browse_name: str = "") -> float:
        override = self._config.node_overrides.get(browse_name) if browse_name else None
        pattern = override.pattern if override is not None else self._config.pattern
        return self._compute_pattern(pattern, index, elapsed_s, override)

    def _compute_pattern(
        self,
        pattern: str,
        index: int,
        elapsed_s: float,
        override: NodePatternConfig | None,
    ) -> float:
        cfg = self._config
        min_val = override.min_value if override and override.min_value is not None else cfg.min_value
        max_val = override.max_value if override and override.max_value is not None else cfg.max_value
        span = max(1e-9, max_val - min_val)

        # ── New patterns (no global noise applied) ───────────────────────────

        if pattern == "constant":
            return float(override.constant_value if override else min_val)

        if pattern == "sinusoid":
            if override:
                return (
                    override.amplitude
                    * math.sin(2.0 * math.pi * (elapsed_s - override.time_offset_s) / override.period_s)
                    + override.value_offset
                )
            return min_val + span * (0.5 + 0.5 * math.sin(elapsed_s * 2.0))

        if pattern == "square":
            if override:
                phase = (elapsed_s % override.square_period_s) / override.square_period_s
                return override.square_high if phase < override.square_duty else override.square_low
            return min_val if (elapsed_s % 2.0) < 1.0 else max_val

        if pattern == "triangle":
            if override:
                t = (elapsed_s % override.triangle_period_s) / override.triangle_period_s
                tri_span = override.triangle_max - override.triangle_min
                return override.triangle_min + tri_span * (1.0 - abs(2.0 * t - 1.0))
            t = (elapsed_s % 2.0) / 2.0
            return min_val + span * (1.0 - abs(2.0 * t - 1.0))

        if pattern == "expression":
            if override and override.expression.strip():
                sym_vals: dict[str, float] = {
                    sym: self._compute_pattern(sym_pat, index, elapsed_s, None)
                    for sym, sym_pat in override.symbols.items()
                }
                try:
                    return float(_safe_eval_expr(override.expression, sym_vals))
                except Exception:  # noqa: BLE001
                    return 0.0
            return 0.0

        if pattern == "counter":
            if override:
                current = self._walk_values.get(index, override.counter_min)
                if override.counter_direction == "up":
                    current += override.counter_step
                    if current > override.counter_max:
                        current = override.counter_min
                else:
                    current -= override.counter_step
                    if current < override.counter_min:
                        current = override.counter_max
                self._walk_values[index] = current
                return current
            return min_val

        # ── Legacy patterns (global noise added at the end) ──────────────────

        if pattern == "random":
            base = min_val + self._rng.random() * span
        elif pattern == "sine":
            phase = (index / max(1, cfg.node_count)) * math.pi
            oscillation = 0.5 + 0.5 * math.sin((elapsed_s * 2.0) + phase)
            base = min_val + (oscillation * span)
        elif pattern == "sawtooth":
            cycle = (elapsed_s * 0.5 + index * 0.01) % 1.0
            base = min_val + cycle * span
        elif pattern == "random_walk":
            current = self._walk_values.get(index, min_val + span * 0.5)
            step = self._rng.uniform(-1.0, 1.0) * max(0.001, span * 0.02)
            current = min(max_val, max(min_val, current + step))
            self._walk_values[index] = current
            base = current
        elif pattern == "burst":
            burst = self._rng.random() < cfg.burst_probability
            scalar = cfg.burst_multiplier if burst else 1.0
            base = min_val + self._rng.random() * span * scalar
            base = min(max_val, max(min_val, base))
        else:
            base = min_val

        noise = self._rng.uniform(-cfg.noise_amplitude, cfg.noise_amplitude)
        return min(max_val, max(min_val, base + noise))

    async def _producer_loop(self) -> None:
        assert self._start_time is not None
        cfg = self._config

        try:
            while not self._stop_event.is_set():
                started = asyncio.get_running_loop().time()
                elapsed_s = (self._utc_now() - self._start_time).total_seconds()

                for idx, node in enumerate(self._variables):
                    browse_name = self._variable_names[idx] if idx < len(self._variable_names) else ""
                    value = self._pattern_value(idx, elapsed_s, browse_name)
                    try:
                        await node.write_value(ua.Variant(value, ua.VariantType.Double))
                        self._counters.node_updates += 1
                    except Exception as exc:  # noqa: BLE001
                        self._counters.errors += 1
                        self._log_exception("Node update error", exc)

                base_offset = len(self._variables)
                for idx, (node, vtype, browse_name) in enumerate(self._xml_variables):
                    value = self._pattern_value(base_offset + idx, elapsed_s, browse_name)
                    typed_value = self._cast_to_variant_type(value, vtype)
                    try:
                        await node.write_value(ua.Variant(typed_value, vtype))
                        self._counters.node_updates += 1
                    except Exception as exc:  # noqa: BLE001
                        self._counters.errors += 1
                        self._log_exception("XML node update error", exc)

                interval = cfg.update_interval_ms / 1000.0
                jitter = self._rng.uniform(-cfg.jitter_ms, cfg.jitter_ms) / 1000.0
                elapsed = asyncio.get_running_loop().time() - started
                await asyncio.sleep(max(0.001, interval + jitter - elapsed))
        except asyncio.CancelledError:
            return

    async def _run_operation(self, op: str, client: Client, client_id: int) -> None:
        try:
            if self._config.fault_injection_enabled and self._rng.random() < self._config.fault_error_rate:
                bad_node = client.get_node("ns=2;s=THIS_NODE_SHOULD_FAIL")
                await bad_node.read_value()

            if op == "read":
                node_id = self._rng.choice(self._node_ids)
                node = client.get_node(node_id)
                await node.read_value()
                self._counters.read_ops += 1
            elif op == "write":
                node_id = self._rng.choice(self._node_ids)
                node = client.get_node(node_id)
                value = self._pattern_value(client_id, (self._utc_now() - self._start_time).total_seconds())
                vtype = self._node_variant_types.get(node_id, ua.VariantType.Double)
                typed_value = self._cast_to_variant_type(value, vtype)
                await node.write_value(ua.Variant(typed_value, vtype))
                self._counters.write_ops += 1
            elif op == "browse":
                await client.nodes.objects.get_children()
                self._counters.browse_ops += 1

            # NOTE: "subscribe" is handled directly in _client_loop via a
            # persistent subscription to avoid per-cycle create/delete churn
            # that can evict external client sessions (Bad_SessionClosed).

            self._counters.total_operations += 1
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            self._counters.errors += 1
            self._log_exception(f"Client op error ({op}) on client {client_id}", exc)

    async def _client_loop(self, client_id: int) -> None:
        cfg = self._config

        if cfg.client_ops_per_sec <= 0:
            return

        mix = [
            ("read", cfg.traffic_mix.read_ratio),
            ("write", cfg.traffic_mix.write_ratio),
            ("browse", cfg.traffic_mix.browse_ratio),
            ("subscribe", cfg.traffic_mix.subscribe_ratio),
        ]

        client = Client(url=cfg.endpoint, timeout=4)

        try:
            await client.connect()
            self._log(f"Client {client_id} connected")
        except Exception as exc:  # noqa: BLE001
            self._counters.errors += 1
            self._log_exception(f"Client {client_id} failed to connect", exc)
            return

        # One persistent subscription per virtual client.
        # Reusing a single subscription and rotating monitored items avoids the
        # create→subscribe→unsubscribe→delete churn that saturates the server's
        # async event loop and causes external sessions to be dropped.
        _subscription = None
        _sub_handles: list = []
        _MAX_SUB_NODES = 5

        if cfg.traffic_mix.subscribe_ratio > 0 and self._node_ids:
            try:
                _subscription = await client.create_subscription(1000, _SubscriptionHandler())
                if cfg.verbose_events:
                    self._log(f"Client {client_id} created persistent subscription")
            except Exception as exc:  # noqa: BLE001
                self._log_exception(f"Client {client_id} could not create subscription", exc)

        try:
            while not self._stop_event.is_set():
                started = asyncio.get_running_loop().time()
                current_rate = self._current_client_ops_per_sec()
                op = self._rng.choices(
                    population=[name for name, _ in mix],
                    weights=[weight for _, weight in mix],
                    k=1,
                )[0]

                if op == "subscribe":
                    # Add a monitored item to the persistent subscription;
                    # evict the oldest handle once the pool is full.
                    if _subscription is not None and self._node_ids:
                        try:
                            node = client.get_node(self._rng.choice(self._node_ids))
                            handle = await _subscription.subscribe_data_change(node)
                            _sub_handles.append(handle)
                            if len(_sub_handles) > _MAX_SUB_NODES:
                                old = _sub_handles.pop(0)
                                await _subscription.unsubscribe(old)
                                if cfg.verbose_events:
                                    self._log(
                                        f"Client {client_id} rotated subscription handle (max={_MAX_SUB_NODES})"
                                    )
                            self._counters.subscribe_ops += 1
                            self._counters.total_operations += 1
                        except asyncio.CancelledError:
                            raise
                        except Exception as exc:  # noqa: BLE001
                            self._counters.errors += 1
                            self._log_exception(
                                f"Client op error (subscribe) on client {client_id}", exc
                            )
                else:
                    await self._run_operation(op=op, client=client, client_id=client_id)

                jitter = self._rng.uniform(-cfg.jitter_ms, cfg.jitter_ms) / 1000.0
                elapsed = asyncio.get_running_loop().time() - started
                period = 1.0 / max(0.1, current_rate)
                await asyncio.sleep(max(0.001, period + jitter - elapsed))
        except asyncio.CancelledError:
            return
        finally:
            # Gracefully tear down the persistent subscription before closing
            # the session so the server does not accumulate stale subscriptions.
            if _subscription is not None:
                try:
                    if _sub_handles:
                        await _subscription.unsubscribe(_sub_handles)
                    await _subscription.delete()
                    if cfg.verbose_events:
                        self._log(f"Client {client_id} deleted persistent subscription")
                except Exception:  # noqa: BLE001
                    pass
            try:
                await client.disconnect()
                self._log(f"Client {client_id} disconnected")
            except Exception:  # noqa: BLE001
                pass

    async def _metrics_loop(self) -> None:
        last_ops = 0
        last_errors = 0
        target_run_seconds = self._run_duration_target_seconds()
        try:
            while not self._stop_event.is_set():
                await asyncio.sleep(1.0)
                current_ops = self._counters.total_operations
                current_errors = self._counters.errors
                uptime = self._uptime_seconds()
                current_client_rate = self._current_client_ops_per_sec(uptime_seconds=uptime)
                self._timeline.append(
                    {
                        "ts": self._utc_now().isoformat(),
                        "ops_last_sec": max(0, current_ops - last_ops),
                        "errors_last_sec": max(0, current_errors - last_errors),
                        "total_ops": current_ops,
                        "client_ops_per_sec": round(current_client_rate, 3),
                    }
                )
                if self._config.verbose_events:
                    self._log(
                        "Metrics heartbeat "
                        f"(ops_last_sec={max(0, current_ops - last_ops)}, "
                        f"errors_last_sec={max(0, current_errors - last_errors)}, "
                        f"total_ops={current_ops})"
                    )
                last_ops = current_ops
                last_errors = current_errors

                if (
                    target_run_seconds > 0
                    and uptime >= target_run_seconds
                    and not self._auto_stop_triggered
                ):
                    self._auto_stop_triggered = True
                    self._log(
                        f"Configured duration reached ({self._config.test_duration_minutes} minutes). Stopping simulator."
                    )
                    asyncio.create_task(self.stop())
        except asyncio.CancelledError:
            return

    def get_status(self) -> SimulatorStatus:
        uptime = self._uptime_seconds()
        run_target = self._run_duration_target_seconds()
        remaining = max(0.0, run_target - uptime) if run_target > 0 else 0.0

        return SimulatorStatus(
            running=self._running,
            server_started=self._server_started,
            start_time=self._start_time.isoformat() if self._start_time else None,
            uptime_seconds=uptime,
            run_duration_target_seconds=run_target,
            remaining_seconds=remaining,
            current_client_ops_per_sec=self._current_client_ops_per_sec(uptime_seconds=uptime),
            load_profile=self._config.load_profile,
            endpoint=self._config.endpoint,
        )

    def get_metrics(self) -> SimulatorMetrics:
        uptime = max(1e-9, self.get_status().uptime_seconds)
        ops_per_second = self._counters.total_operations / uptime if self._running else 0.0

        return SimulatorMetrics(
            total_operations=self._counters.total_operations,
            ops_per_second=ops_per_second,
            current_client_ops_per_sec=self._current_client_ops_per_sec(),
            errors=self._counters.errors,
            node_updates=self._counters.node_updates,
            per_operation={
                "read": self._counters.read_ops,
                "write": self._counters.write_ops,
                "browse": self._counters.browse_ops,
                "subscribe": self._counters.subscribe_ops,
            },
            timeline=list(self._timeline),
        )

    def get_events(self) -> list[EventRecord]:
        return list(self._events)

    def get_namespace_info(self) -> dict:
        resolved = self._resolve_nodeset_file()
        upload_path = Path.cwd() / "uploaded_namespace.xml"
        return {
            "active_file": str(resolved) if resolved else None,
            "active_file_name": resolved.name if resolved else None,
            "has_uploaded_file": upload_path.exists(),
            "configured_file": self._config.namespace_nodeset_file,
            "namespace_uri": self._config.namespace_uri,
        }
