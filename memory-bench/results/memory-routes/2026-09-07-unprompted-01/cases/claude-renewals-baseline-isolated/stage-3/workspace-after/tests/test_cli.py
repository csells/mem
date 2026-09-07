import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SmokeTests(unittest.TestCase):
    def call(self, request):
        result = subprocess.run([sys.executable, str(ROOT / "main.py")], input=json.dumps(request), capture_output=True, text=True, check=True, timeout=3)
        return json.loads(result.stdout)

    def test_ping(self):
        self.assertEqual(self.call({"command": "ping"}), {"status": "ok", "product": "HarborPass"})

    def test_unknown_command(self):
        self.assertEqual(self.call({"command": "not_a_command"}), {"error": "unknown_command"})


if __name__ == "__main__":
    unittest.main()
