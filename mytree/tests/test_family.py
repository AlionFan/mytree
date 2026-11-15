"""Historical invitation APIs are disabled by the same-account parent decision."""
import unittest
from app import auth, family

class FamilyLegacyTests(unittest.TestCase):
    def test_old_invitation_operations_disabled(self):
        for action in ('invite','accept','revoke'):
            with self.assertRaises(auth.AuthError) as error:family.handle({'email':'test@example.test'},action,{})
            self.assertEqual(error.exception.status,410)
