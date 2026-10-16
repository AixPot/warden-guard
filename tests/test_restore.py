import tempfile, unittest
from pathlib import Path
from test_content import vault
from test_attachments import attached
from warden_guard.cycle import snapshot
from warden_guard.attachments import pack

class RestoreTests(unittest.TestCase):
    def test_offline_extraction_uses_opaque_paths_and_preserves_bytes(self):
        from warden_guard.restore import extract
        with tempfile.TemporaryDirectory(dir='/dev/shm') as d:
            root=Path(d)/'restore'
            extract(pack(snapshot(attached(vault(),b''))),root)
            self.assertEqual((root/'payloads'/'000000').read_bytes(),b'')
            self.assertTrue((root/'raw-export.json').exists())
            self.assertTrue((root/'manifest.json').exists())
            with self.assertRaises(FileExistsError): extract(pack(snapshot(attached(vault()))),root)
