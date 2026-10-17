"""Test bazasi xavfsizligi: testlar hech qachon ishchi (production) bazaga tegmasligi kerak (tests/conftest.py)."""
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROD = "postgresql://prod_user:secret@db.example.com:5432/production"


def run_pytest(env_extra, *args):
    env = {k: v for k, v in os.environ.items() if k not in ("TEST_DATABASE_URL", "DATABASE_URL", "ALLOW_REMOTE_TEST_DB")}
    env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *args],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=120,
    )


class InProcessProbe(unittest.TestCase):
    def test_in_process_env(self):
        """Ichki tekshiruv: DATABASE_URL har doim test bazasi (yoki soxta manzil) — hech qachon muhitdagi haqiqiy emas."""
        expected = os.environ.get("TEST_DATABASE_URL") or "postgresql://fake/fake"
        self.assertEqual(os.environ["DATABASE_URL"], expected)
        self.assertNotIn("db.example.com", os.environ["DATABASE_URL"])


class GuardTests(unittest.TestCase):
    def test_remote_test_database_is_refused(self):
        r = run_pytest({"TEST_DATABASE_URL": PROD}, "tests/test_help.py")
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)  # pytest to'xtatiladi, testlar umuman ishlamaydi
        self.assertIn("lokal emas", r.stdout + r.stderr)
        self.assertNotIn("passed", r.stdout)

    def test_remote_allowed_only_with_explicit_flag(self):
        r = run_pytest({"TEST_DATABASE_URL": PROD, "ALLOW_REMOTE_TEST_DB": "1"}, "--collect-only", "tests/test_help.py")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_real_database_url_is_overridden_by_test_database(self):
        r = run_pytest(
            {"DATABASE_URL": PROD, "TEST_DATABASE_URL": "postgresql://postgres@localhost:5444/postgres"},
            "tests/test_db_guard.py", "-k", "in_process_env",
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_real_database_url_without_test_database_becomes_fake(self):
        r = run_pytest({"DATABASE_URL": PROD}, "tests/test_db_guard.py", "-k", "in_process_env")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_local_hosts_are_accepted(self):
        for url in ("postgresql://u@localhost/db", "postgresql://u@127.0.0.1:5432/db", "postgresql://u@[::1]/db"):
            r = run_pytest({"TEST_DATABASE_URL": url}, "--collect-only", "tests/test_help.py")
            self.assertEqual(r.returncode, 0, url + r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
