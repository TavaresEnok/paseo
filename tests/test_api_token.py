import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from orchestrator import service

class ApiTokenTests(unittest.TestCase):
    def test_first_boot_initializes_private_token_and_restart_preserves_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'runtime/flow-token'
            with patch.object(service,'TOKEN_FILE',path):
                service.ensure_api_token();first=path.read_bytes();service.ensure_api_token()
            self.assertGreater(len(first),32);self.assertEqual(path.read_bytes(),first)
            self.assertEqual(path.stat().st_mode&0o777,0o600)

    def test_invalid_existing_file_is_not_silently_replaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'flow-token';path.write_text('')
            with patch.object(service,'TOKEN_FILE',path):
                with self.assertRaises(RuntimeError):service.ensure_api_token()
            self.assertEqual(path.read_text(),'')
