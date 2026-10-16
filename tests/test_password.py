import copy, unittest
from test_content import vault
from warden_guard.content import canonical, validate, Invalid

class OptionalPasswordTests(unittest.TestCase):
    def test_missing_null_empty_password_equivalence_only(self):
        base=vault(); base['items'][0]['login'].pop('password')
        validate(base)
        for value in (None, ''):
            other=copy.deepcopy(base); other['items'][0]['login']['password']=value
            self.assertEqual(canonical(base),canonical(other))
        for value in (' ', 'secret'):
            other=copy.deepcopy(base); other['items'][0]['login']['password']=value
            self.assertNotEqual(canonical(base),canonical(other))
        other=copy.deepcopy(base); other['items'][0]['login']['password']=42
        with self.assertRaises(Invalid): validate(other)
