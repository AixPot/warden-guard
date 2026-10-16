import tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from warden_guard.runtime import Profile
from warden_guard.storage import Blocked

class LimitsTests(unittest.TestCase):
    def test_default_allows_representative_large_file_with_bounded_config(self):
        from warden_guard.attachments import MAX_FILE, MAX_TOTAL, MAX_BUNDLE
        self.assertGreaterEqual(MAX_FILE,16*1024*1024)
        self.assertGreaterEqual(MAX_TOTAL,MAX_FILE)
        self.assertLessEqual(MAX_TOTAL,32*1024*1024)
        self.assertGreaterEqual(MAX_BUNDLE,2*MAX_TOTAL)

    def test_tmpfs_shortage_blocks_before_cli(self):
        p=Profile('source',{},None,ram='/dev/shm')
        with patch('warden_guard.runtime.shutil.disk_usage') as disk, patch.object(p,'command') as command:
            disk.return_value.free=1
            with self.assertRaises(Blocked): p.export_snapshot()
            command.assert_not_called()
    def test_ciphertext_length_mismatch_rejected_and_temp_file_removed(self):
        with tempfile.TemporaryDirectory(dir='/dev/shm') as d:
            p=Profile('source',{},None,ram=d); p.path=Path(d)
            def command(*args,**kwargs):
                Path(args[-1]).write_bytes(b'abc')
            with patch('warden_guard.runtime.shutil.disk_usage') as disk, patch.object(p,'command',side_effect=command):
                disk.return_value.free=1024**3
                with self.assertRaises(Blocked): p.download_attachment('item',{'id':'a','size':'321'})
            self.assertFalse(list(Path(d).iterdir()))
