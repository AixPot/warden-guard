import base64, copy, json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from test_content import vault
from warden_guard.runtime import Profile
from warden_guard.storage import Blocked

class AdapterTests(unittest.TestCase):
    def test_source_get_only_attachment(self):
        profile=Profile('source',{},None); profile.env={}; profile.ram='/dev/shm'
        with patch('warden_guard.runtime.subprocess.run') as run:
            run.return_value.returncode=0
            profile.command('get','attachment','a','--itemid','i','--output','/run/x')
            with self.assertRaises(Blocked): profile.command('get','password','i')
            with self.assertRaises(Blocked): profile.command('create','attachment')
    def test_mapped_import_restores_fields_for_equal_bodies(self):
        data=vault(); data['items'].append(dict(copy.deepcopy(data['items'][0]),id='b'))
        profile=Profile('dest',{},None); observed={}; edited={}
        def ingest(marked):
            observed.update(copy.deepcopy(marked))
            for n,item in enumerate(observed['items']): item['id']='generated-'+str(n)
            observed['items'].reverse()  # Never rely on import or export ordering.
        def command(*args,**kwargs):
            if args[:2]==('get','item'):
                return json.dumps(next(i for i in observed['items'] if i['id']==args[2])).encode()
            if args[:2]==('edit','item'):
                edited[args[2]]=json.loads(base64.b64decode(kwargs['input'])); return b''
            raise AssertionError('unexpected command')
        with patch.object(profile,'ingest',side_effect=ingest), patch.object(profile,'export_snapshot',return_value=(observed,b'')), patch.object(profile,'command',side_effect=command):
            mapping=profile.ingest_mapped(data)
        self.assertEqual(mapping,{'a':'generated-0','b':'generated-1'})
        self.assertEqual([i['fields'] for i in edited.values()],[None,None])
