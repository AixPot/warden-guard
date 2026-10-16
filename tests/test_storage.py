import tempfile, unittest, pathlib, json, os
from warden_guard.storage import Storage, Blocked

class StorageTests(unittest.TestCase):
    def test_identity_persistent_scoped_and_corrupt_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            s=Storage(d); a=s.identity('source','https://example.invalid','user@example.invalid')
            self.assertEqual(a,Storage(d).identity('source','https://example.invalid','user@example.invalid'))
            self.assertNotEqual(a,s.identity('dest','https://example.invalid','user@example.invalid'))
            f=next(pathlib.Path(d,'devices').glob('*.json'))
            self.assertEqual(f.stat().st_mode & 0o777,0o600)
            f.write_text('{"token":"bad"}')
            with self.assertRaises(Blocked): s.identity('source','https://example.invalid','user@example.invalid')
    def test_backup_roundtrip_and_journal_block(self):
        with tempfile.TemporaryDirectory() as d:
            s=Storage(d); raw=b'{"secret":"test"}'
            p=s.backup(raw,'source',b'not-an-account-password')
            self.assertNotIn(raw,p.read_bytes()); self.assertTrue(p.read_bytes().startswith(b'Salted__'))
            self.assertEqual(s.decrypt(p,b'not-an-account-password'),raw)
            s.check_ready(); s.record('importing',{'old_ids':['old']})
            with self.assertRaises(Blocked): Storage(d).check_ready()
            s.record('complete',{}); Storage(d).check_ready()
