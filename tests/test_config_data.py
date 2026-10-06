import asyncio
import math
import unittest
from pathlib import Path

from asyncua import Client, ua

from app.nodeset_config import read_nodeset
from app.schemas import SimulatorConfig
from app.simulator import OPCUASimulator


class ConfigDataTests(unittest.IsolatedAsyncioTestCase):
    def test_reads_five_tags_metadata_and_embedded_rules(self):
        rows, rules = read_nodeset(Path('config_data.xml'))
        self.assertEqual(len(rows), 5)
        by_name = {row['name']: row for row in rows}
        self.assertEqual(by_name['Temperature']['initial_value'], 135)
        self.assertEqual(by_name['Temperature']['min_value'], 132)
        self.assertEqual(by_name['Temperature']['unit'], '°C')
        self.assertEqual(by_name['Pressure']['max_value'], -10)
        self.assertEqual(by_name['MotorRunning']['initial_value'], True)
        self.assertEqual(by_name['ProductionCount']['data_type'], 'Int64')
        self.assertEqual(rules['SpeedSetpoint'].constant_value, 3)

    async def test_default_file_patterns_and_preview(self):
        simulator = OPCUASimulator()
        await simulator.update_config(SimulatorConfig())
        rows = await simulator.get_tags()
        self.assertEqual(len(rows), 5)
        self.assertTrue(all(row['quality'] == 'Loaded' for row in rows))
        for t in (0, 2.5, 5, 7.5, 10, 300, 600):
            self.assertAlmostEqual(simulator._pattern_value(0, t, 'Temperature'),
                                   135 + 3 * math.sin(2 * math.pi * t / 10))
            self.assertAlmostEqual(simulator._pattern_value(1, t, 'Pressure'),
                                   -11 + math.sin(2 * math.pi * t / 15))
            self.assertEqual(simulator._pattern_value(4, t, 'SpeedSetpoint'), 3)
        self.assertEqual(simulator._pattern_value(2, 299, 'MotorRunning'), 1)
        self.assertEqual(simulator._pattern_value(2, 300, 'MotorRunning'), 0)
        self.assertEqual(simulator._pattern_value(2, 600, 'MotorRunning'), 1)
        self.assertEqual(simulator._pattern_value(3, 0, 'ProductionCount'), 1)
        self.assertEqual(simulator._pattern_value(3, 1, 'ProductionCount'), 2)

    async def test_actual_file_import_live_table_and_external_write(self):
        simulator = OPCUASimulator()
        await simulator.update_config(SimulatorConfig(
            endpoint='opc.tcp://127.0.0.1:14841/test/',
            traffic_mode='self_load', virtual_clients=1, client_ops_per_sec=50,
            traffic_mix={'read_ratio': 0, 'write_ratio': 1,
                         'browse_ratio': 0, 'subscribe_ratio': 0},
        ))
        try:
            await simulator.start()
            await asyncio.sleep(0.2)
            self.assertEqual(len(simulator._xml_variables), 5)
            self.assertEqual(len(simulator._node_ids), 5)
            self.assertEqual(simulator.get_status().active_protocols, ['OPC-UA'])
            rows = {row['name']: row for row in await simulator.get_tags()}
            self.assertTrue(all(row['quality'] == 'Good' for row in rows.values()))
            self.assertGreaterEqual(rows['Temperature']['value'], 132)
            self.assertLessEqual(rows['Temperature']['value'], 138)
            self.assertGreaterEqual(rows['Pressure']['value'], -12)
            self.assertLessEqual(rows['Pressure']['value'], -10)
            self.assertIs(rows['MotorRunning']['value'], True)
            self.assertEqual(rows['SpeedSetpoint']['value'], 3)
            self.assertEqual(rows['ProductionCount']['value'], 1)
            self.assertGreater(simulator.get_metrics().per_operation['write'], 0)
            self.assertEqual(simulator.get_metrics().errors, 0)
            # With background tasks paused, the table must still read live UA values.
            simulator._producer_task.cancel()
            for task in simulator._client_tasks:
                task.cancel()
            await asyncio.gather(simulator._producer_task, *simulator._client_tasks)
            async with Client(simulator._config.endpoint) as client:
                node = client.get_node(rows['SpeedSetpoint']['node_id'])
                await node.write_value(ua.Variant(4.0, ua.VariantType.Double))
                fresh = {row['name']: row for row in await simulator.get_tags()}
                self.assertEqual(fresh['SpeedSetpoint']['value'], 4)
                self.assertEqual(fresh['SpeedSetpoint']['initial_value'], 3)
        finally:
            await simulator.stop()

    async def test_missing_file_is_reported_without_replacing_configuration(self):
        simulator = OPCUASimulator()
        with self.assertRaisesRegex(ValueError, 'not found'):
            await simulator.update_config(SimulatorConfig(namespace_nodeset_file='missing.xml'))
        self.assertIsNone(simulator.get_config().namespace_nodeset_file)
