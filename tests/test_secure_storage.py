import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))
from secure_storage import SecureStorage, protect_path


class SecureStorageTests(unittest.TestCase):
    def test_encrypted_fallback_storage(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(SecureStorage,"_keyring",return_value=None):
            storage=SecureStorage(directory);storage.set_secret("email","user@example.com");self.assertEqual(storage.get_secret("email"),"user@example.com");raw=(Path(directory)/"secure_settings.json").read_text(encoding="utf-8");self.assertNotIn("user@example.com",raw);self.assertEqual(storage.backend,"Protected local key file")
            if os.name!="nt":self.assertEqual((Path(directory)/".fairscope.key").stat().st_mode & 0o777,0o600)
            storage.delete_secret("email");self.assertEqual(storage.get_secret("email"),"")
    def test_protect_path(self):
        with tempfile.NamedTemporaryFile(delete=False) as handle:path=handle.name
        self.addCleanup(lambda:os.path.exists(path) and os.unlink(path));protect_path(path)
        if os.name!="nt":self.assertEqual(os.stat(path).st_mode & 0o777,0o600)

if __name__=="__main__":unittest.main()
