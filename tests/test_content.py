import copy, unittest
from warden_guard.content import canonical, validate, Invalid

def vault():
    return {"encrypted":False,"folders":[{"id":"f","name":"folder"}],"items":[{"id":"a","folderId":"f","type":1,"name":"login","login":{"username":"","password":"p","totp":None},"notes":None,"fields":None,"passwordHistory":None}]}

class ContentTests(unittest.TestCase):
    def test_equivalence_only_allowed_empty_login_fields(self):
        a=vault(); b=copy.deepcopy(a); b['items'][0]['id']='b'; b['folders'][0]['id']='g'; b['items'][0]['folderId']='g'
        del b['items'][0]['login']['username']; b['items'][0]['login']['totp']=''
        self.assertEqual(canonical(a),canonical(b))
        b['items'][0]['login']['username']=' '
        self.assertNotEqual(canonical(a),canonical(b))
        b=copy.deepcopy(a); b['items'][0]['fields']=[]
        self.assertNotEqual(canonical(a),canonical(b))
    def test_multiplicity_and_ssh_preserved(self):
        a=vault(); a['items'] += [{"id":"s","type":5,"name":"ssh","sshKey":{"privateKey":"k","publicKey":"p","keyFingerprint":"f"}}]
        validate(a,True); b=copy.deepcopy(a); b['items'][1]['sshKey']['privateKey']='changed'
        self.assertNotEqual(canonical(a),canonical(b))
        b=copy.deepcopy(a); b['items'].append(dict(a['items'][0],id='c'))
        self.assertNotEqual(canonical(a),canonical(b))
    def test_schema_and_optional_nulls(self):
        validate(vault(),True)
        for change in ('empty','duplicate','folder','type','org','attachment'):
            a=vault()
            if change=='empty': a['items']=[]
            if change=='duplicate': a['items']*=2
            if change=='folder': a['items'][0]['folderId']='missing'
            if change=='type': a['items'][0]['type']=6
            if change=='org': a['items'][0]['organizationId']='o'
            if change=='attachment': a['items'][0]['attachments']=[{'id':'x'}]
            with self.subTest(change=change), self.assertRaises(Invalid): validate(a,True)
