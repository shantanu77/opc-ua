from __future__ import annotations

import threading
from dataclasses import asdict
from typing import Any, Iterable

from .tag_registry import TagRegistry, TagValue, utc_timestamp

try:
    import Pyro4
except ImportError:  # pragma: no cover - exercised through gateway status
    Pyro4 = None  # type: ignore[assignment]


class OpenOPCAdapter:
    """OpenOPC-shaped read/write/list API backed by the live tag cache."""

    def __init__(self, registry: TagRegistry, *, allow_writes: bool = True) -> None:
        self.registry = registry
        self.allow_writes = allow_writes
        self._lock = threading.Lock()
        self._read_count = 0
        self._write_count = 0
        self._list_count = 0

    def read(self, tags: str | Iterable[str], *args: Any, **kwargs: Any) -> list[tuple[str, Any, str, str]]:
        del args, kwargs
        requested = [tags] if isinstance(tags, str) else list(tags)
        results: list[tuple[str, Any, str, str]] = []
        for requested_path in requested:
            record = self.registry.read(str(requested_path))
            if record is None:
                results.append((str(requested_path), None, "Bad: Unknown tag", utc_timestamp()))
            else:
                results.append(self._as_openopc_tuple(record))
        with self._lock:
            self._read_count += len(requested)
        return results

    def write(
        self,
        tags: str | dict[str, Any] | Iterable[tuple[str, Any]],
        values: Any | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> list[tuple[str, Any, str, str]]:
        del args, kwargs
        writes = self._normalize_writes(tags, values)
        results: list[tuple[str, Any, str, str]] = []
        for path, value in writes:
            if not self.allow_writes:
                current = self.registry.read(path)
                results.append(
                    (
                        path,
                        current.value if current else value,
                        "Bad: Writes disabled",
                        utc_timestamp(),
                    )
                )
                continue
            updated = self.registry.update(path, value, require_writable=True)
            if updated is None:
                results.append((path, value, "Bad: Unknown tag", utc_timestamp()))
            else:
                results.append(self._as_openopc_tuple(updated))
        with self._lock:
            self._write_count += len(writes)
        return results

    def list(
        self,
        paths: str | Iterable[str] = "*",
        recursive: bool = False,
        flat: bool = False,
        *args: Any,
        **kwargs: Any,
    ) -> list[str]:
        del args, kwargs, flat
        patterns = [paths] if isinstance(paths, str) else list(paths)
        found: set[str] = set()
        for pattern in patterns or ["*"]:
            found.update(self.registry.list_paths(str(pattern), recursive=recursive))
        with self._lock:
            self._list_count += 1
        return sorted(found)

    def ping(self) -> bool:
        return True

    def create_client(self) -> "OpenOPCAdapter":
        """Return this registered object; Pyro4 auto-proxies it to OpenOPC clients."""
        return self

    def release_client(self, obj: Any = None) -> bool:
        del obj
        return True

    def connect(self, opc_server: str | None = None, opc_host: str = "localhost") -> bool:
        del opc_server, opc_host
        return True

    def close(self, *args: Any, **kwargs: Any) -> bool:
        del args, kwargs
        return True

    def servers(self, opc_host: str = "localhost") -> list[str]:
        del opc_host
        return ["OPC-UA Traffic Simulator"]

    def stats(self) -> dict[str, int | bool]:
        with self._lock:
            return {
                "reads": self._read_count,
                "writes": self._write_count,
                "lists": self._list_count,
                "allow_writes": self.allow_writes,
            }

    @staticmethod
    def _as_openopc_tuple(record: TagValue) -> tuple[str, Any, str, str]:
        return (record.path, record.value, record.quality, record.timestamp)

    @staticmethod
    def _normalize_writes(
        tags: str | dict[str, Any] | Iterable[tuple[str, Any]], values: Any | None
    ) -> list[tuple[str, Any]]:
        if isinstance(tags, str):
            if values is None:
                raise ValueError("a value is required when writing one tag")
            return [(tags, values)]
        if isinstance(tags, dict):
            return [(str(path), value) for path, value in tags.items()]
        return [(str(path), value) for path, value in tags]


if Pyro4 is not None:
    OpenOPCAdapter = Pyro4.expose(OpenOPCAdapter)  # type: ignore[misc,assignment]


class OpenOPCGateway:
    """Own a Pyro daemon in a background thread and expose the adapter as `opc`."""

    def __init__(self, adapter: OpenOPCAdapter) -> None:
        self.adapter = adapter
        self._daemon: Any | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._ready_event = threading.Event()
        self._lock = threading.RLock()
        self._host = "0.0.0.0"
        self._port = 7766
        self._object_name = "opc"
        self._uri: str | None = None
        self._error: str | None = None

    def configure(
        self,
        *,
        enabled: bool,
        host: str,
        port: int,
        object_name: str = "opc",
        allow_writes: bool = True,
    ) -> None:
        self.adapter.allow_writes = allow_writes
        desired = (host, port, object_name)
        current = (self._host, self._port, self._object_name)
        if not enabled:
            self.stop()
            self._host, self._port, self._object_name = desired
            return
        if self.running and desired == current:
            return
        self.stop()
        self.start(host=host, port=port, object_name=object_name)

    def start(self, *, host: str, port: int, object_name: str = "opc") -> None:
        if Pyro4 is None:
            raise RuntimeError("Pyro4 is required for the OpenOPC compatibility gateway")
        with self._lock:
            if self.running:
                return
            self._host = host
            self._port = port
            self._object_name = object_name
            self._uri = None
            self._error = None
            self._stop_event.clear()
            self._ready_event.clear()
            self._thread = threading.Thread(
                target=self._serve,
                name="openopc-pyro-daemon",
                daemon=True,
            )
            self._thread.start()
        if not self._ready_event.wait(timeout=5.0):
            self.stop()
            raise RuntimeError("OpenOPC Pyro daemon did not start within 5 seconds")
        if self._error:
            error = self._error
            self.stop()
            raise RuntimeError(f"OpenOPC Pyro daemon failed to start: {error}")

    def stop(self) -> None:
        with self._lock:
            daemon = self._daemon
            thread = self._thread
            self._stop_event.set()
        if daemon is not None:
            try:
                daemon.shutdown()
            except Exception:
                pass
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=5.0)
        with self._lock:
            self._daemon = None
            self._thread = None
            self._uri = None

    @property
    def running(self) -> bool:
        thread = self._thread
        return bool(thread and thread.is_alive() and self._error is None)

    def status(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "host": self._host,
            "port": self._port,
            "object_name": self._object_name,
            "uri": self._uri,
            "error": self._error,
            "tag_count": len(self.adapter.registry),
            **self.adapter.stats(),
        }

    def tags(self) -> list[dict[str, Any]]:
        return [asdict(record) for record in self.adapter.registry.snapshot()]

    def _serve(self) -> None:
        daemon: Any | None = None
        try:
            assert Pyro4 is not None
            Pyro4.config.SERVERTYPE = "thread"
            daemon = Pyro4.Daemon(host=self._host, port=self._port)
            uri = daemon.register(self.adapter, objectId=self._object_name)
            with self._lock:
                self._daemon = daemon
                self._uri = str(uri)
            self._ready_event.set()
            daemon.requestLoop(loopCondition=lambda: not self._stop_event.is_set())
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                self._error = str(exc)
            self._ready_event.set()
        finally:
            if daemon is not None:
                try:
                    # Pyro stores the registration id on the exposed object.
                    # Unregister it so this same adapter can be started again
                    # in a fresh daemon after a simulator stop/start cycle.
                    daemon.unregister(self.adapter)
                except Exception:
                    pass
                try:
                    daemon.close()
                except Exception:
                    pass
            with self._lock:
                if self._daemon is daemon:
                    self._daemon = None
