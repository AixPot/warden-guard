import unittest
from warden_guard.runtime import reject_unexportable
from warden_guard.storage import Blocked

class PreflightTests(unittest.TestCase):
    def test_attachment_and_organization_fail_closed(self):
        reject_unexportable([{'id':'x','type':5,'attachments':None,'organizationId':None}],[])
        reject_unexportable([{'id':'x','type':1,'attachments':[{'id':'a','fileName':'file'}]}],[])
        for items,orgs in (([], [{'id':'org'}]),([{'type':6}],[])):
            with self.assertRaises(Blocked): reject_unexportable(items,orgs)
