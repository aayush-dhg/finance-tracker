import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")

import database
import demo_data


class DemoDataTestCase(unittest.TestCase):
    def test_demo_database_is_isolated_and_contains_only_fictional_data(self):
        with tempfile.TemporaryDirectory() as directory:
            demo_path = Path(directory) / "portfolio-demo.db"
            original_database_path = database.DATABASE_PATH

            created_path = demo_data.create_demo_database(demo_path)

            self.assertEqual(created_path, demo_path.resolve())
            self.assertEqual(database.DATABASE_PATH, original_database_path)
            self.assertTrue(demo_path.exists())

            connection = sqlite3.connect(demo_path)
            try:
                user_count = connection.execute(
                    "SELECT COUNT(*) FROM users"
                ).fetchone()[0]
                paycheck_count = connection.execute(
                    "SELECT COUNT(*) FROM paychecks"
                ).fetchone()[0]
                integrity = connection.execute(
                    "PRAGMA integrity_check"
                ).fetchone()[0]
            finally:
                connection.close()

            self.assertEqual(user_count, 2)
            self.assertEqual(paycheck_count, 2)
            self.assertEqual(integrity, "ok")

            with self.assertRaises(FileExistsError):
                demo_data.create_demo_database(demo_path)

    def test_demo_generator_refuses_the_normal_database_path(self):
        with self.assertRaisesRegex(ValueError, "cannot write to finance.db"):
            demo_data.create_demo_database(
                demo_data.PRODUCTION_DATABASE_PATH
            )


if __name__ == "__main__":
    unittest.main()
