import asyncio
import unittest

from asyncua import Client
from app.schemas import SimulatorConfig
from app.simulator import OPCUASimulator


class SimulatorSourceTests(unittest.IsolatedAsyncioTestCase):
    async def test_manual_source_does_not_load_xml(self):
        simulator = OPCUASimulator()
        await simulator.update_config(SimulatorConfig(
            source_mode='manual', node_count=3, pattern='constant', min_value=7,
            max_value=8, endpoint='opc.tcp://127.0.0.1:14842/test/'))
        self.assertIsNone(simulator._resolve_nodeset_file())
        self.assertFalse(simulator.get_status().server_started)
        preview = await simulator.get_tags()
        self.assertEqual(len(preview), 3)
        try:
            await simulator.start()
            await asyncio.sleep(0.05)
            self.assertEqual(len(simulator._xml_variables), 0)
            self.assertEqual(len(simulator._variables), 3)
            self.assertFalse(hasattr(simulator, '_client_tasks'))
            async with Client(simulator._config.endpoint) as client:
                rows = await simulator.get_tags()
                for row in rows:
                    self.assertEqual(await client.get_node(row['node_id']).read_value(), 7)
        finally:
            await simulator.stop()

    async def test_xml_ignores_manual_generation_settings(self):
        simulator = OPCUASimulator()
        await simulator.update_config(SimulatorConfig(
            node_count=200, pattern='burst', min_value=2000, max_value=3000,
            noise_amplitude=500, update_interval_ms=10, jitter_ms=100))
        preview = await simulator.get_tags()
        self.assertEqual(len(preview), 5)
        self.assertEqual(simulator._simulation_config.update_interval_ms, 1000)
        self.assertEqual(simulator._simulation_config.jitter_ms, 0)
        self.assertEqual(simulator._pattern_value(0, 0, 'Temperature'), 135)
        counter = next(row for row in preview if row['name'] == 'ProductionCount')
        self.assertIn('step 1', counter['simulation_parameters'])
        self.assertEqual(counter['parameters']['counter_max'], 999999)
