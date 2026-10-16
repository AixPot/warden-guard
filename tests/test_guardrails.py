import copy, tempfile, unittest, os
from unittest.mock import patch
from test_content import vault
from warden_guard.content import validate, Invalid
from warden_guard.storage import Storage, Blocked
from warden_guard.runtime import once

class GuardrailTests(unittest.TestCase):
    def test_incomplete_typed_content_rejected(self):
        data=vault(); data['items'][0]['login']={'password':42}
        with self.assertRaises(Invalid): validate(data)
        data['items'][0].update(type=5,sshKey={})
        with self.assertRaises(Invalid): validate(data)
    def test_busy_global_lock_prevents_login(self):
        with tempfile.TemporaryDirectory() as state:
            with Storage(state).lock(),patch.dict(os.environ,{'WG_STATE_DIR':state}),patch('warden_guard.runtime.load_config',return_value={}),patch('warden_guard.runtime.Profile') as profile:
                with self.assertRaises(Blocked): once()
                profile.assert_not_called()
