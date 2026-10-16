import json, tempfile, pathlib, unittest
from unittest.mock import patch
from warden_guard.runtime import Profile, main
from warden_guard.storage import Storage

class RuntimeTests(unittest.TestCase):
    def test_profile_cleanup_and_stable_initial_seed(self):
        with tempfile.TemporaryDirectory() as state, tempfile.TemporaryDirectory(dir='/dev/shm') as ram:
            storage=Storage(state)
            scope={'server':'https://example.invalid','account':'user@example.invalid','password':'placeholder'}
            with patch.object(Profile,'command',return_value=b''):
                p=Profile('source',scope,storage,ram)
                with p:
                    path=p.path
                    a=json.loads((path/'data.json').read_text())['global_applicationId_appId']
                self.assertFalse(path.exists())
                with Profile('source',scope,storage,ram) as q:
                    self.assertEqual(a,json.loads((q.path/'data.json').read_text())['global_applicationId_appId'])
    def test_error_status_is_one_line_without_exception_secret(self):
        import io
        from contextlib import redirect_stdout
        out=io.StringIO()
        with patch('warden_guard.runtime.load_config',side_effect=RuntimeError('secret')),redirect_stdout(out):
            self.assertEqual(main(['once']),1)
        self.assertEqual(json.loads(out.getvalue()),{'status':'error','code':'operation_failed'})
