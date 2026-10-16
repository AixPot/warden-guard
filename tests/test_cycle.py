import copy, tempfile, unittest
from warden_guard.cycle import execute
from warden_guard.storage import Storage, Blocked
from test_content import vault

class MemoryVault:
    def __init__(self, data, fail=None): self.data=copy.deepcopy(data); self.fail=fail; self.deleted=[]; self.imports=0
    def export(self): return copy.deepcopy(self.data)
    def ingest(self, data):
        self.imports+=1
        if self.fail=='import': raise RuntimeError('sensitive CLI error')
        mapping={}
        for f in data['folders']:
            nf=dict(f,id='new-'+f['id']); mapping[f['id']]=nf['id']; self.data['folders'].append(nf)
        for item in data['items']:
            n=copy.deepcopy(item); n['id']='new-'+n['id']
            if n.get('folderId'): n['folderId']=mapping[n['folderId']]
            self.data['items'].append(n)
    def delete(self, kind, ident):
        if self.fail=='delete': raise RuntimeError('secret')
        key='items' if kind=='item' else 'folders'
        self.data[key]=[x for x in self.data[key] if x['id']!=ident]; self.deleted.append(ident)

class CycleTests(unittest.TestCase):
    def test_replace_then_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            source=MemoryVault(vault()); old=vault(); old['items'][0]['name']='old'; target=MemoryVault(old)
            self.assertEqual(execute(source,target,Storage(d),b'backup'),'complete')
            self.assertEqual(target.deleted,['a','f'])
            self.assertEqual(execute(source,target,Storage(d),b'backup'),'unchanged')
            self.assertEqual(target.imports,1)
    def test_import_failure_keeps_old_and_blocks(self):
        self.failure('import')
    def test_delete_failure_blocks(self): self.failure('delete')
    def failure(self, mode):
        with tempfile.TemporaryDirectory() as d:
            old=vault(); old['items'][0]['name']='old'; target=MemoryVault(old,mode); storage=Storage(d)
            with self.assertRaises(RuntimeError): execute(MemoryVault(vault()),target,storage,b'backup')
            if mode=='import': self.assertEqual(target.data,old)
            with self.assertRaises(Blocked): execute(MemoryVault(vault()),target,storage,b'backup')
    def test_empty_source_no_target_write(self):
        with tempfile.TemporaryDirectory() as d:
            data=vault(); data['items']=[]; target=MemoryVault(vault())
            with self.assertRaises(Exception): execute(MemoryVault(data),target,Storage(d),b'backup')
            self.assertEqual(target.imports,0)
