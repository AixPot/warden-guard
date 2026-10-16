import copy, tempfile, unittest
from pathlib import Path
from test_content import vault
from test_attachments import attached
from warden_guard.cycle import snapshot
from warden_guard.attachments import pack, unpack, filename
from warden_guard.content import Invalid

class BundleSafetyTests(unittest.TestCase):
    def test_hash_tamper_and_path_rejected(self):
        import json
        doc=json.loads(pack(snapshot(attached(vault()))))
        doc['payloads'][0]='dGFtcGVy'
        with self.assertRaises(Invalid): unpack(json.dumps(doc).encode())
        for name in ('../x','/absolute','a/b','a\\b','..','', 'nul\0'):
            with self.subTest(name=name), self.assertRaises(Invalid): filename(name)
    def test_bundle_limit_before_parse(self):
        from unittest.mock import patch
        with patch('warden_guard.attachments.MAX_BUNDLE',1), self.assertRaises(Invalid):
            unpack(b'{}')
    def test_missing_manifest_is_rejected(self):
        import json
        doc=json.loads(pack(snapshot(attached(vault())))); doc['manifest']=[]; doc['payloads']=[]
        with self.assertRaises(Invalid): unpack(json.dumps(doc).encode())
    def test_oversize_fails_and_records_blocked_journal(self):
        from warden_guard.cycle import execute
        from warden_guard.storage import Storage, Blocked
        from warden_guard.attachments import MAX_FILE
        src=attached(vault(),b'x'*(MAX_FILE+1)); dst=attached(vault())
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(Invalid): execute(src,dst,Storage(d),b'backup')
            self.assertFalse(dst.deleted)
            with self.assertRaises(Blocked): execute(src,dst,Storage(d),b'backup')
