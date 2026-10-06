from __future__ import annotations

import threading
import unittest

from app.openopc_adapter import OpenOPCAdapter, OpenOPCGateway
from app.tag_registry import TagRegistry


class OpenOPCAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = TagRegistry()
        self.registry.register(
            "SimulatedDevice.Tag0000",
            10.5,
            aliases=("Tag0000", "ns=2;i=100"),
        )
        self.registry.register(
            "Simulation.Line1.MotorRunning",
            True,
            data_type="Boolean",
        )
        self.adapter = OpenOPCAdapter(self.registry)

    def test_read_returns_openopc_tuple_and_resolves_alias(self) -> None:
        result = self.adapter.read("Tag0000")

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], "SimulatedDevice.Tag0000")
        self.assertEqual(result[0][1], 10.5)
        self.assertEqual(result[0][2], "Good")
        self.assertIn("+00:00", result[0][3])

    def test_read_unknown_tag_returns_bad_quality(self) -> None:
        result = self.adapter.read("missing")

        self.assertEqual(result[0][0], "missing")
        self.assertIsNone(result[0][1])
        self.assertEqual(result[0][2], "Bad: Unknown tag")

    def test_write_updates_the_shared_cache(self) -> None:
        result = self.adapter.write("Tag0000", 42.25)

        self.assertEqual(result[0][1:3], (42.25, "Good"))
        self.assertEqual(self.registry.read("SimulatedDevice.Tag0000").value, 42.25)

    def test_write_accepts_batch_and_dict_forms(self) -> None:
        batch = self.adapter.write(
            [("Tag0000", 1.0), ("Simulation.Line1.MotorRunning", False)]
        )
        mapped = self.adapter.write({"Tag0000": 2.0})

        self.assertEqual([item[2] for item in batch], ["Good", "Good"])
        self.assertEqual(mapped[0][1], 2.0)

    def test_write_can_be_disabled(self) -> None:
        adapter = OpenOPCAdapter(self.registry, allow_writes=False)

        result = adapter.write("Tag0000", 99)

        self.assertEqual(result[0][2], "Bad: Writes disabled")
        self.assertEqual(self.registry.read("Tag0000").value, 10.5)

    def test_list_supports_wildcards(self) -> None:
        self.assertEqual(
            self.adapter.list("SimulatedDevice.*"),
            ["SimulatedDevice.Tag0000"],
        )
        self.assertEqual(len(self.adapter.list("*", recursive=True)), 2)

    def test_openopc_gateway_handshake_methods(self) -> None:
        self.assertIs(self.adapter.create_client(), self.adapter)
        self.assertTrue(self.adapter.connect("OPC-UA Traffic Simulator"))
        self.assertEqual(self.adapter.servers(), ["OPC-UA Traffic Simulator"])
        self.assertTrue(self.adapter.close())
        self.assertTrue(self.adapter.release_client(self.adapter))

    def test_registry_is_safe_for_concurrent_updates_and_reads(self) -> None:
        def update_values() -> None:
            for value in range(1000):
                self.registry.update("Tag0000", value)

        threads = [threading.Thread(target=update_values) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        record = self.registry.read("Tag0000")
        self.assertIsNotNone(record)
        self.assertEqual(record.quality, "Good")

    def test_gateway_can_restart_with_the_same_adapter(self) -> None:
        gateway = OpenOPCGateway(self.adapter)
        try:
            gateway.start(host="127.0.0.1", port=0, object_name="opc")
            self.assertTrue(gateway.running)
            gateway.stop()
            self.assertFalse(gateway.running)

            gateway.start(host="127.0.0.1", port=0, object_name="opc")
            self.assertTrue(gateway.running)
        finally:
            gateway.stop()


if __name__ == "__main__":
    unittest.main()
