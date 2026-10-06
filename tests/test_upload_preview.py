import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException, UploadFile
from app import main
from app.schemas import SimulatorConfig
from app.simulator import OPCUASimulator


class UploadPreviewTests(unittest.IsolatedAsyncioTestCase):
    async def test_valid_upload_selects_xml_and_invalid_upload_preserves_it(self):
        simulator = OPCUASimulator()
        await simulator.update_config(SimulatorConfig(source_mode='manual', node_count=2))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / 'uploaded_namespace.xml'
            with patch.object(main, 'simulator', simulator), \
                 patch.object(main, 'BASE_DIR', root / 'app'), \
                 patch.object(main, 'NAMESPACE_UPLOAD_PATH', destination):
                original = Path('config_data.xml').read_bytes()
                response = await main.upload_namespace_file(
                    UploadFile(filename='process.xml', file=io.BytesIO(original)))
                self.assertEqual(response['config']['source_mode'], 'xml')
                self.assertEqual(destination.read_bytes(), original)
                self.assertEqual(len(await simulator.get_tags()), 5)
                with self.assertRaises(HTTPException) as error:
                    await main.upload_namespace_file(
                        UploadFile(filename='bad.xml', file=io.BytesIO(b'<invalid>')))
                self.assertEqual(error.exception.status_code, 422)
                self.assertEqual(destination.read_bytes(), original)
                self.assertEqual(len(await simulator.get_tags()), 5)
                simulator._running = True
                with self.assertRaises(HTTPException) as error:
                    await main.upload_namespace_file(
                        UploadFile(filename='process.xml', file=io.BytesIO(original)))
                self.assertEqual(error.exception.status_code, 409)
                simulator._running = False

    async def test_file_timing_is_used_instead_of_manual_timing(self):
        text = Path('config_data.xml').read_text().replace(
            '"pattern": "random",', '"update_interval_ms": 2000, "pattern": "random",', 1)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'timing.xml'
            path.write_text(text)
            simulator = OPCUASimulator()
            await simulator.update_config(SimulatorConfig(
                namespace_nodeset_file=str(path), update_interval_ms=10, jitter_ms=100))
            self.assertEqual(simulator._simulation_config.update_interval_ms, 2000)
            self.assertEqual(simulator._simulation_config.jitter_ms, 0)
            self.assertTrue(all(row['update_interval_ms'] == 2000
                                for row in await simulator.get_tags()))
