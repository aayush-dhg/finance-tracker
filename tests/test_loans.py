import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("FINANCE_SKIP_DATABASE_INIT", "1")

import app as app_module
import database


class LoanTestCase(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.original_database_path = database.DATABASE_PATH
        database.DATABASE_PATH = (
            Path(self.temporary_directory.name) / "test-finance.db"
        )
        database.initialize_database()

        self.user_id = database.create_user(
            "loan_owner", "a-secure-password"
        )
        self.other_user_id = database.create_user(
            "other_owner", "another-secure-password"
        )

        app_module.app.config.update(
            TESTING=True,
            WTF_CSRF_ENABLED=False,
        )
        self.client = app_module.app.test_client()

    def tearDown(self):
        database.DATABASE_PATH = self.original_database_path
        self.temporary_directory.cleanup()

    def login_as(self, user_id):
        with self.client.session_transaction() as session:
            session.clear()
            session["_user_id"] = str(user_id)
            session["_fresh"] = True

    def loan_form(self, **overrides):
        values = {
            "name": "Family SUV",
            "loan_type": "auto",
            "balance": "24500.75",
            "apr": "6.49",
            "monthly_payment": "525.10",
            "due_day": "14",
        }
        values.update(overrides)
        return values

    def test_all_dropdown_types_can_be_added(self):
        self.login_as(self.user_id)

        for loan_type in database.LOAN_TYPES:
            response = self.client.post(
                "/loans/add",
                data=self.loan_form(
                    name=f"{loan_type.title()} Loan",
                    loan_type=loan_type,
                ),
            )
            self.assertEqual(response.status_code, 302)

        loans = database.get_loans(self.user_id)
        self.assertEqual(len(loans), 4)
        self.assertEqual(
            {loan["loan_type"] for loan in loans},
            {"auto", "mortgage", "personal", "individual"},
        )

    def test_add_edit_and_delete_loan(self):
        self.login_as(self.user_id)

        response = self.client.post("/loans/add", data=self.loan_form())
        self.assertEqual(response.status_code, 302)

        loan = database.get_loans(self.user_id)[0]
        self.assertEqual(loan["name"], "Family SUV")
        self.assertEqual(loan["loan_type"], "auto")
        self.assertEqual(loan["balance_cents"], 2450075)
        self.assertEqual(loan["apr_basis_points"], 649)
        self.assertEqual(loan["monthly_payment_cents"], 52510)
        self.assertEqual(loan["due_day"], 14)

        response = self.client.post(
            f"/loans/{loan['id']}/edit",
            data=self.loan_form(
                name="Home Loan",
                loan_type="mortgage",
                balance="300000.00",
                apr="5.75",
                monthly_payment="2100.00",
                due_day="1",
            ),
        )
        self.assertEqual(response.status_code, 302)

        edited = database.get_loans(self.user_id)[0]
        self.assertEqual(edited["name"], "Home Loan")
        self.assertEqual(edited["loan_type"], "mortgage")
        self.assertEqual(edited["balance_cents"], 30000000)
        self.assertEqual(edited["monthly_payment_cents"], 210000)

        response = self.client.post(f"/loans/{loan['id']}/delete")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(database.get_loans(self.user_id), [])

    def test_loan_validation_rejects_bad_values(self):
        self.login_as(self.user_id)

        invalid_forms = (
            self.loan_form(name=""),
            self.loan_form(loan_type="business"),
            self.loan_form(balance="-0.01"),
            self.loan_form(apr="100.01"),
            self.loan_form(monthly_payment="1.001"),
            self.loan_form(due_day="0"),
            self.loan_form(due_day="32"),
        )

        for form in invalid_forms:
            with self.subTest(form=form):
                response = self.client.post("/loans/add", data=form)
                self.assertEqual(response.status_code, 302)

        self.assertEqual(database.get_loans(self.user_id), [])

    def test_loans_are_private_to_their_owner(self):
        loan_id = database.add_loan(
            self.user_id,
            "Private Mortgage",
            "mortgage",
            25000000,
            550,
            180000,
            1,
        )
        database.add_loan(
            self.other_user_id,
            "Other Auto Loan",
            "auto",
            2000000,
            700,
            45000,
            15,
        )
        self.login_as(self.other_user_id)

        page = self.client.get("/add")
        self.assertEqual(page.status_code, 200)
        self.assertNotIn(b"Private Mortgage", page.data)
        self.assertIn(b"Other Auto Loan", page.data)

        edit_response = self.client.post(
            f"/loans/{loan_id}/edit",
            data=self.loan_form(name="Taken Loan"),
        )
        delete_response = self.client.post(f"/loans/{loan_id}/delete")

        self.assertEqual(edit_response.status_code, 404)
        self.assertEqual(delete_response.status_code, 404)
        owner_loan = database.get_loans(self.user_id)[0]
        self.assertEqual(owner_loan["name"], "Private Mortgage")

    def test_budget_includes_monthly_loan_payments(self):
        database.update_income(self.user_id, 500000, 100000)
        database.add_expense(self.user_id, "Housing", 150000)
        database.add_credit_card(
            self.user_id, "Card", 300000, 2000, 10000, 10
        )
        database.add_loan(
            self.user_id,
            "Auto Loan",
            "auto",
            2000000,
            650,
            50000,
            14,
        )
        self.login_as(self.user_id)

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"$20,000.00", response.data)
        self.assertIn(b"$600.00", response.data)
        self.assertIn(b"$3,900.00", response.data)


if __name__ == "__main__":
    unittest.main()
