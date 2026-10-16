import json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from test_content import vault
from warden_guard.runtime import Profile
from warden_guard.storage import Blocked

class ExportScopeTests(unittest.TestCase):
    def run_export(self, normal, archived, trash, exported):
        raw=json.dumps(exported,indent=2).encode()
        with tempfile.TemporaryDirectory(dir='/dev/shm') as d:
            profile=Profile('source',{},None,d); profile.path=Path(d)
            def command(*args,**kwargs):
                if args==('sync',): return b''
                if args==('list','items'): return json.dumps(normal).encode()
                if args==('list','items','--archived'): return json.dumps(archived).encode()
                if args==('list','items','--trash'): return json.dumps(trash).encode()
                if args==('list','organizations'): return b'[]'
                if args[0]=='export': Path(args[-1]).write_bytes(raw); return b''
                raise AssertionError('unexpected command')
            with patch('warden_guard.runtime.shutil.disk_usage') as disk, patch.object(profile,'command',side_effect=command):
                disk.return_value.free=1024**3
                return profile.export_snapshot(),raw

    def test_archived_card_in_scope_trash_only_in_raw(self):
        data=vault(); card={'id':'archived','type':3,'name':'card','card':{},'archivedDate':'2026-01-01'}
        trash={'id':'trash','type':3,'name':'history','card':{},'deletedDate':'2026-01-01'}
        data['items'] += [card,trash]
        (active,original),raw=self.run_export(data['items'][:1],[card],[trash],data)
        self.assertEqual(original,raw)
        self.assertEqual([i['id'] for i in active['items']],['a','archived'])

    def test_unknown_difference_and_duplicate_fail_closed(self):
        data=vault(); row=data['items'][0]
        cases=[([row,row],[],[],data),([row],[dict(row,archivedDate='date')],[],data),
               ([row],[],[],dict(data,items=[row,dict(row,id='unknown')])),
               ([dict(row,organizationId='org')],[],[],data),
               ([dict(row,collectionIds=['collection'])],[],[],data),
               ([],[dict(row,archivedDate=None)],[],data),
               ([dict(row,deletedDate='date')],[],[],data),
               ([row],[],[dict(row,id='trash')],data),
               ([row],[],[],dict(data,items=[row,row]))]
        for n,args in enumerate(cases):
            with self.subTest(case=n), self.assertRaises(Blocked): self.run_export(*args)
