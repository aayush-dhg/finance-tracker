import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("FINANCE_SKIP_DATABASE_INIT", "1")

import app as app_module
import database


class DashboardTestCase(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.original_database_path = database.DATABASE_PATH
        database.DATABASE_PATH = (
            Path(self.temporary_directory.name) / "test-finance.db"
        )
        database.initialize_database()
        self.user_id = database.create_user(
            "dashboard_user", "a-secure-password"
        )
        self.other_user_id = database.create_user(
            "other_user", "another-secure-password"
        )

        app_module.app.config.update(
            TESTING=True,
            WTF_CSRF_ENABLED=False,
        )
        self.client = app_module.app.test_client()
        self.login_as(self.user_id)

    def tearDown(self):
        database.DATABASE_PATH = self.original_database_path
        self.temporary_directory.cleanup()

    def login_as(self, user_id):
        with self.client.session_transaction() as session:
            session.clear()
            session["_user_id"] = str(user_id)
            session["_fresh"] = True

    def test_dashboard_calculations_and_recorded_history(self):
        database.update_income(self.user_id, 500000, 100000)
        database.add_expense(
            self.user_id,
            "Rent",
            100000,
            "Housing",
        )
        database.add_asset(
            self.user_id,
            "Savings",
            "Cash",
            1000000,
            "2026-02-01",
        )
        database.add_asset(
            self.user_id,
            "Brokerage",
            "Investments",
            500000,
            "2026-02-01",
        )
        database.add_credit_card(
            self.user_id, "Visa", 300000, 2000, 10000, 10
        )
        database.add_loan(
            self.user_id,
            "Auto",
            "auto",
            500000,
            650,
            30000,
            14,
        )

        planned_page = self.client.get("/?month=2026-02&year=2026")
        self.assertIn(b"$15,000.00", planned_page.data)
        self.assertIn(b"$8,000.00", planned_page.data)
        self.assertIn(b"$7,000.00", planned_page.data)
        self.assertIn(b"$4,600.00", planned_page.data)
        self.assertIn(b"Planned monthly estimate", planned_page.data)
        self.assertIn(b"No recorded history for 2026", planned_page.data)

        database.add_income_record(
            self.user_id, "February pay", 600000, "2026-02-15"
        )
        database.add_expense(
            self.user_id,
            "February spending",
            150000,
            "Living costs",
            "2026-02-20",
        )
        database.add_debt_payment(
            self.user_id,
            "Visa payment",
            "credit_card",
            40000,
            "2026-02-25",
        )

        recorded_page = self.client.get("/?month=2026-02&year=2026")
        self.assertIn(
            b"Recorded entries + planned debt payments",
            recorded_page.data,
        )
        self.assertIn(b"$4,100.00", recorded_page.data)
        self.assertIn(b"2026 recorded net cash flow", recorded_page.data)
        self.assertIn(b"recorded debt\n                        payments $400.00", recorded_page.data)

        # A recorded payment affects cash-flow history, not outstanding debt.
        self.assertIn(b"$8,000.00", recorded_page.data)

    def test_custom_expense_categories_are_validated_and_reused(self):
        response = self.client.post(
            "/expenses/add",
            data={
                "name": "Monthly help",
                "category": "Family support",
                "amount": "250.00",
                "recorded_on": "",
            },
        )
        self.assertEqual(response.status_code, 302)

        expense = database.get_expenses(self.user_id)[0]
        self.assertEqual(expense["category"], "Family support")
        self.assertIsNone(expense["recorded_on"])

        manage_page = self.client.get("/add")
        self.assertIn(b'value="Family support"', manage_page.data)

        response = self.client.post(
            f"/expenses/{expense['id']}/edit",
            data={
                "name": "Vet plan",
                "category": "Pet care",
                "amount": "90.25",
                "recorded_on": "2026-03-03",
            },
        )
        self.assertEqual(response.status_code, 302)
        edited = database.get_expenses(self.user_id)[0]
        self.assertEqual(edited["category"], "Pet care")
        self.assertEqual(edited["amount_cents"], 9025)
        self.assertEqual(edited["recorded_on"], "2026-03-03")

        unsafe_category = "<script>alert(1)</script>"
        database.add_expense(
            self.user_id,
            "Escaped category",
            100,
            unsafe_category,
        )
        manage_page = self.client.get("/add")
        self.assertNotIn(unsafe_category.encode(), manage_page.data)
        self.assertIn(b"&lt;script&gt;alert(1)&lt;/script&gt;", manage_page.data)

        invalid_response = self.client.post(
            "/expenses/add",
            data={
                "name": "Bad category",
                "category": "x" * 51,
                "amount": "1.00",
                "recorded_on": "",
            },
        )
        self.assertEqual(invalid_response.status_code, 302)
        self.assertEqual(len(database.get_expenses(self.user_id)), 2)

        response = self.client.post(f"/expenses/{expense['id']}/delete")
        self.assertEqual(response.status_code, 302)
        self.assertNotIn(
            expense["id"],
            [item["id"] for item in database.get_expenses(self.user_id)],
        )

    def test_asset_income_and_payment_crud(self):
        asset_response = self.client.post(
            "/assets/add",
            data={
                "name": "Emergency fund",
                "category": "Cash",
                "balance": "2500.00",
                "as_of_date": "2026-04-01",
            },
        )
        income_response = self.client.post(
            "/income-records/add",
            data={
                "name": "Paycheck",
                "amount": "3000.00",
                "recorded_on": "2026-04-15",
            },
        )
        payment_response = self.client.post(
            "/debt-payments/add",
            data={
                "name": "Loan payment",
                "debt_type": "loan",
                "amount": "425.00",
                "paid_on": "2026-04-16",
            },
        )
        self.assertEqual(asset_response.status_code, 302)
        self.assertEqual(income_response.status_code, 302)
        self.assertEqual(payment_response.status_code, 302)

        asset = database.get_assets(self.user_id)[0]
        income = database.get_income_records(self.user_id)[0]
        payment = database.get_debt_payments(self.user_id)[0]

        self.client.post(
            f"/assets/{asset['id']}/edit",
            data={
                "name": "Emergency savings",
                "category": "Cash",
                "balance": "3000.00",
                "as_of_date": "2026-04-02",
            },
        )
        self.client.post(
            f"/income-records/{income['id']}/edit",
            data={
                "name": "Updated paycheck",
                "amount": "3100.00",
                "recorded_on": "2026-04-15",
            },
        )
        self.client.post(
            f"/debt-payments/{payment['id']}/edit",
            data={
                "name": "Updated loan payment",
                "debt_type": "loan",
                "amount": "450.00",
                "paid_on": "2026-04-16",
            },
        )

        self.assertEqual(database.get_assets(self.user_id)[0]["balance_cents"], 300000)
        self.assertEqual(database.get_income_records(self.user_id)[0]["amount_cents"], 310000)
        self.assertEqual(database.get_debt_payments(self.user_id)[0]["amount_cents"], 45000)

        self.client.post(f"/assets/{asset['id']}/delete")
        self.client.post(f"/income-records/{income['id']}/delete")
        self.client.post(f"/debt-payments/{payment['id']}/delete")
        self.assertEqual(database.get_assets(self.user_id), [])
        self.assertEqual(database.get_income_records(self.user_id), [])
        self.assertEqual(database.get_debt_payments(self.user_id), [])

    def test_new_records_are_private_to_owner(self):
        asset_id = database.add_asset(
            self.user_id, "Private asset", "Cash", 100000, "2026-05-01"
        )
        income_id = database.add_income_record(
            self.user_id, "Private income", 200000, "2026-05-02"
        )
        expense_id = database.add_expense(
            self.user_id,
            "Private expense",
            30000,
            "Private category",
            "2026-05-03",
        )
        payment_id = database.add_debt_payment(
            self.user_id,
            "Private payment",
            "other",
            10000,
            "2026-05-04",
        )
        self.login_as(self.other_user_id)

        manage_page = self.client.get("/add")
        for private_label in (
            b"Private asset",
            b"Private income",
            b"Private expense",
            b"Private payment",
        ):
            self.assertNotIn(private_label, manage_page.data)

        attempts = (
            self.client.post(
                f"/assets/{asset_id}/edit",
                data={
                    "name": "Taken",
                    "category": "Cash",
                    "balance": "1.00",
                    "as_of_date": "2026-05-01",
                },
            ),
            self.client.post(f"/assets/{asset_id}/delete"),
            self.client.post(
                f"/income-records/{income_id}/edit",
                data={
                    "name": "Taken",
                    "amount": "1.00",
                    "recorded_on": "2026-05-02",
                },
            ),
            self.client.post(f"/income-records/{income_id}/delete"),
            self.client.post(
                f"/expenses/{expense_id}/edit",
                data={
                    "name": "Taken",
                    "category": "Other",
                    "amount": "1.00",
                    "recorded_on": "2026-05-03",
                },
            ),
            self.client.post(f"/expenses/{expense_id}/delete"),
            self.client.post(
                f"/debt-payments/{payment_id}/edit",
                data={
                    "name": "Taken",
                    "debt_type": "other",
                    "amount": "1.00",
                    "paid_on": "2026-05-04",
                },
            ),
            self.client.post(f"/debt-payments/{payment_id}/delete"),
        )
        self.assertTrue(all(response.status_code == 404 for response in attempts))
        self.assertEqual(database.get_assets(self.user_id)[0]["name"], "Private asset")
        self.assertEqual(database.get_income_records(self.user_id)[0]["name"], "Private income")
        self.assertEqual(database.get_expenses(self.user_id)[0]["name"], "Private expense")
        self.assertEqual(database.get_debt_payments(self.user_id)[0]["name"], "Private payment")


class MigrationTestCase(unittest.TestCase):
    def test_existing_expense_is_preserved_with_safe_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "legacy.db"
            connection = sqlite3.connect(database_path)
            with connection:
                connection.execute("""
                    CREATE TABLE users (
                        id INTEGER PRIMARY KEY,
                        username TEXT NOT NULL UNIQUE,
                        password_hash TEXT NOT NULL
                    )
                """)
                connection.execute("""
                    CREATE TABLE expenses (
                        id INTEGER PRIMARY KEY,
                        user_id INTEGER NOT NULL,
                        name TEXT NOT NULL,
                        amount_cents INTEGER NOT NULL
                    )
                """)
                connection.execute(
                    "INSERT INTO users VALUES (1, 'legacy', 'hash')"
                )
                connection.execute(
                    "INSERT INTO expenses VALUES (1, 1, 'Legacy rent', 120000)"
                )
            connection.close()

            original_path = database.DATABASE_PATH
            database.DATABASE_PATH = database_path
            try:
                database.initialize_database()
                expenses = database.get_expenses(1)
            finally:
                database.DATABASE_PATH = original_path

            self.assertEqual(len(expenses), 1)
            self.assertEqual(expenses[0]["name"], "Legacy rent")
            self.assertEqual(expenses[0]["amount_cents"], 120000)
            self.assertEqual(expenses[0]["category"], "Uncategorized")
            self.assertIsNone(expenses[0]["recorded_on"])


if __name__ == "__main__":
    unittest.main()
