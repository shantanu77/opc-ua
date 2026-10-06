import asyncio
import tempfile
import unittest
from pathlib import Path

from asyncua import Client, Server, ua

from app.schemas import SimulatorConfig
from app.simulator import OPCUASimulator


class XMLRangeTests(unittest.IsolatedAsyncioTestCase):
    async def test_imported_limits_survive_producer_updates(self):
        # Export a real NodeSet, then import it through the simulator workflow.
        server = Server()
        await server.init()
        ns = await server.register_namespace('urn:range-test')
        folder = await server.nodes.objects.add_folder(ns, 'Plant')
        variable = await folder.add_variable(ns, 'Temperature', 999.0)
        await variable.set_writable()
        limits = await variable.add_property(ns, 'EURange', ua.Range(Low=20.0, High=30.0))
        with tempfile.TemporaryDirectory() as directory:
            xml = Path(directory) / 'ranges.xml'
            await server.export_xml([folder, variable, limits], str(xml), export_values=True)
            simulator = OPCUASimulator()
            await simulator.update_config(SimulatorConfig(
                namespace_nodeset_file=str(xml), endpoint='opc.tcp://127.0.0.1:14840/test/',
                min_value=1000, max_value=2000,
            ))
            try:
                await simulator.start()
                imported = simulator._xml_variables[0][0]
                self.assertEqual(len(simulator._xml_variables), 1)
                async with Client(simulator._config.endpoint) as client:
                    node = client.get_node(imported.nodeid)
                    for _ in range(30):
                        value = await node.read_value()
                        self.assertGreaterEqual(value, 20)
                        self.assertLessEqual(value, 30)
                        await asyncio.sleep(0.02)
                self.assertGreater(simulator.get_metrics().node_updates, 0)
                self.assertEqual(simulator.get_metrics().errors, 0)
                self.assertEqual((await limits.read_value()).High, 30)
            finally:
                await simulator.stop()

    async def test_min_max_properties_and_integer_rounding(self):
        server = Server()
        await server.init()
        ns = await server.register_namespace('urn:min-max-test')
        node = await server.nodes.objects.add_variable(ns, 'Count', 2)
        await node.add_property(ns, 'Min', 1.2)
        await node.add_property(ns, 'Max', 3.8)
        simulator = OPCUASimulator()
        bounds = await simulator._read_node_range(node)
        simulator._node_ranges[node.nodeid.to_string()] = bounds
        self.assertEqual(simulator._bounded_node_value(node.nodeid.to_string(), -99, ua.VariantType.Int32), 2)
        self.assertEqual(simulator._bounded_node_value(node.nodeid.to_string(), 99, ua.VariantType.Int32), 3)

    async def test_instrument_range_fallback_and_eu_range_precedence(self):
        server = Server()
        await server.init()
        ns = await server.register_namespace('urn:range-precedence')
        node = await server.nodes.objects.add_variable(ns, 'Pressure', 2.0)
        await node.add_property(ns, 'InstrumentRange', ua.Range(Low=-10, High=10))
        simulator = OPCUASimulator()
        self.assertEqual(await simulator._read_node_range(node), (-10, 10))
        await node.add_property(ns, 'EURange', ua.Range(Low=1, High=3))
        self.assertEqual(await simulator._read_node_range(node), (1, 3))

    async def test_all_patterns_are_bounded_and_missing_limits_preserve_behavior(self):
        simulator = OPCUASimulator()
        simulator._node_ranges['test'] = (20, 30)
        for pattern in ('random', 'sine', 'sawtooth', 'random_walk', 'burst',
                        'constant', 'sinusoid', 'square', 'triangle', 'expression', 'counter'):
            simulator._config.pattern = pattern
            for index in range(20):
                value = simulator._pattern_value(index, index / 10, node_id='test')
                bounded = simulator._bounded_node_value('test', value, ua.VariantType.Double)
                self.assertGreaterEqual(bounded, 20)
                self.assertLessEqual(bounded, 30)
        self.assertEqual(simulator._bounded_node_value('unbounded', 999, ua.VariantType.Double), 999)
