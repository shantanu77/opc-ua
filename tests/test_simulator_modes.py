from __future__ import annotations

import asyncio
import unittest

from app.schemas import SimulatorConfig
from app.simulator import OPCUASimulator


class SimulatorTrafficModeTests(unittest.IsolatedAsyncioTestCase):
    async def _start_without_network(
        self, simulator: OPCUASimulator, config: SimulatorConfig
    ) -> None:
        async def fake_setup_server() -> None:
            simulator._server_started = True

        async def idle_client(client_id: int) -> None:
            del client_id
            await simulator._stop_event.wait()

        simulator._setup_server = fake_setup_server  # type: ignore[method-assign]
        simulator._client_loop = idle_client  # type: ignore[method-assign]
        simulator.start_openopc_gateway = lambda: None  # type: ignore[method-assign]
        await simulator.update_config(config)
        await simulator.start()

    async def test_serve_only_starts_no_virtual_clients(self) -> None:
        simulator = OPCUASimulator()
        config = SimulatorConfig(traffic_mode="serve_only", virtual_clients=25)

        await self._start_without_network(simulator, config)

        self.assertEqual(simulator.get_status().traffic_mode, "serve_only")
        self.assertEqual(simulator.get_status().current_client_ops_per_sec, 0.0)
        self.assertEqual(len(simulator._client_tasks), 0)
        await simulator.stop()

    async def test_self_load_starts_configured_virtual_clients(self) -> None:
        simulator = OPCUASimulator()
        config = SimulatorConfig(traffic_mode="self_load", virtual_clients=3)

        await self._start_without_network(simulator, config)

        self.assertEqual(len(simulator._client_tasks), 3)
        self.assertGreater(simulator.get_status().current_client_ops_per_sec, 0.0)
        await simulator.stop()

    async def test_saving_config_does_not_start_openopc(self) -> None:
        simulator = OPCUASimulator()

        await simulator.update_config(SimulatorConfig(openopc_enabled=True))

        self.assertFalse(simulator.openopc_gateway.running)


if __name__ == "__main__":
    unittest.main()
