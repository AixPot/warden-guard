import copy, json, tempfile, unittest
from pathlib import Path
from test_content import vault
from test_cycle import MemoryVault
from warden_guard.cycle import execute
from warden_guard.storage import Storage, Blocked

class AttachmentVault(MemoryVault):
    def download_attachment(self, item, attachment):
        return self.payloads[attachment['id']]
    def ingest_mapped(self, data):
        clean=copy.deepcopy(data)
        for i in clean['items']: i.pop('attachments',None)
        self.ingest(clean)
        return {i['id']:'new-'+i['id'] for i in data['items']}
    def upload_attachment(self, ident, name, payload):
        if self.fail=='upload': raise Blocked('cli')
        item=next(i for i in self.data['items'] if i['id']==ident)
        aid='upload-'+str(len(self.payloads)); self.payloads[aid]=payload if self.fail!='corrupt' else b'corrupt'
        item.setdefault('attachments',[]).append({'id':aid,'fileName':name,'size':str(len(payload)+65)})

def attached(data, payload=b'content'):
    client=AttachmentVault(data); client.payloads={'file':payload}
    client.data['items'][0]['attachments']=[{'id':'file','fileName':'same.bin','size':str(len(payload)+65),'url':'sensitive'}]
    return client

class AttachmentTests(unittest.TestCase):
    def test_roundtrip_duplicate_bodies_different_attachments_and_offline_snapshot(self):
        src=attached(vault()); second=copy.deepcopy(src.data['items'][0]); second['id']='b'; second['attachments'][0]['id']='other'
        src.data['items'].append(second); src.payloads['other']=b''
        old=vault(); old['items'][0]['name']='old'; dst=attached(old,b'old-content')
        with tempfile.TemporaryDirectory() as d:
            storage=Storage(d)
            self.assertEqual(execute(src,dst,storage,b'backup'),'complete')
            self.assertEqual(execute(src,dst,storage,b'backup'),'unchanged')
            from warden_guard.attachments import unpack
            recovered=unpack(storage.decrypt(min((Path(d)/'backups').glob('target-*.enc')),b'backup'))
            self.assertEqual(recovered['payloads'][0],b'old-content')
            journal=(Path(d)/'journal.json').read_text()
            self.assertNotIn('same.bin',journal); self.assertNotIn('sensitive',journal)
    def test_source_download_failure_blocks_without_target_mutation(self):
        from unittest.mock import patch
        src=attached(vault()); dst=attached(vault())
        with tempfile.TemporaryDirectory() as d, patch.object(src,'download_attachment',side_effect=Blocked('cli')):
            with self.assertRaises(Blocked): execute(src,dst,Storage(d),b'backup')
            self.assertEqual(dst.imports,0); self.assertFalse(dst.deleted)
            with self.assertRaises(Blocked): execute(src,dst,Storage(d),b'backup')
    def test_same_name_same_length_changed_bytes_triggers_replacement(self):
        src=attached(vault(),b'one'); dst=attached(vault(),b'two')
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(execute(src,dst,Storage(d),b'backup'),'complete')
            self.assertTrue(dst.deleted)
    def test_upload_or_download_corruption_keeps_old_and_blocks(self):
        for failure in ('upload','corrupt'):
            src=attached(vault()); old=vault(); old['items'][0]['name']='old'; dst=attached(old,b'old'); dst.fail=failure
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as d:
                storage=Storage(d)
                with self.assertRaises(Exception): execute(src,dst,storage,b'backup')
                self.assertFalse(dst.deleted)
                with self.assertRaises(Blocked): execute(src,dst,storage,b'backup')
