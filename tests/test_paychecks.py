import os
import tempfile
import unittest
from pathlib import Path

from werkzeug.datastructures import MultiDict

os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("FINANCE_SKIP_DATABASE_INIT", "1")

import app as app_module
import database


class PaycheckTestCase(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.original_database_path = database.DATABASE_PATH
        database.DATABASE_PATH = (
            Path(self.temporary_directory.name) / "test-finance.db"
        )
        database.initialize_database()
        self.user_id = database.create_user(
            "paycheck_user", "a-secure-password"
        )
        self.other_user_id = database.create_user(
            "other_paycheck_user", "another-secure-password"
        )
        self.account_id = database.add_retirement_account(
            self.user_id,
            "Private Employer Plan",
            1000000,
            200000,
            "2026-03-31",
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

    def paycheck_values(self, **overrides):
        values = {
            "pay_date": "2026-04-15",
            "employee_name": "Taylor",
            "employer": "Example Company",
            "gross_pay_cents": 500000,
            "federal_tax_cents": 60000,
            "state_tax_cents": 20000,
            "social_security_tax_cents": 31000,
            "medicare_tax_cents": 7000,
            "other_tax_cents": 2000,
            "health_insurance_cents": 15000,
            "employee_401k_cents": 25000,
            "actual_net_cents": 330000,
            "retirement_account_id": self.account_id,
            "employer_match_cents": 12500,
            "employer_match_vested": False,
            "deductions": [
                {"name": "Parking", "amount_cents": 5000},
                {"name": "Union dues", "amount_cents": 2500},
            ],
        }
        values.update(overrides)
        return values

    def paycheck_form(self, **overrides):
        values = {
            "pay_date": "2026-04-15",
            "employee_name": "Taylor",
            "employer": "Example Company",
            "gross_pay": "5000.00",
            "federal_tax": "600.00",
            "state_tax": "200.00",
            "social_security_tax": "310.00",
            "medicare_tax": "70.00",
            "other_tax": "20.00",
            "health_insurance": "150.00",
            "employee_401k": "250.00",
            "actual_net": "3300.00",
            "retirement_account_id": str(self.account_id),
            "employer_match": "125.00",
        }
        values.update(overrides)
        pairs = list(values.items())
        pairs.extend((
            ("deduction_name", "Parking"),
            ("deduction_amount", "50.00"),
            ("deduction_name", "Union dues"),
            ("deduction_amount", "25.00"),
        ))
        return MultiDict(pairs)

    def test_expected_net_discrepancy_and_contribution_tracking(self):
        paycheck_id = database.add_paycheck(
            self.user_id,
            **self.paycheck_values(),
        )

        paycheck = database.get_paychecks(self.user_id)[0]
        self.assertEqual(paycheck["id"], paycheck_id)
        self.assertEqual(paycheck["taxes_cents"], 120000)
        self.assertEqual(paycheck["custom_deductions_cents"], 7500)
        self.assertEqual(paycheck["payroll_deductions_cents"], 167500)
        self.assertEqual(paycheck["expected_net_cents"], 332500)
        self.assertEqual(paycheck["actual_net_cents"], 330000)
        self.assertEqual(paycheck["discrepancy_cents"], -2500)

        contributions = database.get_retirement_contributions(self.user_id)
        self.assertEqual(len(contributions), 2)
        employee = next(
            item
            for item in contributions
            if item["contribution_type"] == "employee"
        )
        employer = next(
            item
            for item in contributions
            if item["contribution_type"] == "employer_match"
        )
        self.assertEqual(employee["amount_cents"], 25000)
        self.assertEqual(employee["vested"], 1)
        self.assertEqual(employer["amount_cents"], 12500)
        self.assertEqual(employer["vested"], 0)

        account = database.get_retirement_accounts(self.user_id)[0]
        self.assertEqual(account["vested_balance_cents"], 1000000)
        self.assertEqual(account["unvested_balance_cents"], 200000)
        self.assertEqual(account["employee_contributions_cents"], 25000)
        self.assertEqual(
            account["unvested_match_contributions_cents"],
            12500,
        )

    def test_actual_net_drives_cash_flow_without_double_counting(self):
        database.update_income(self.user_id, 900000, 100000)
        database.add_paycheck(self.user_id, **self.paycheck_values())
        database.add_paycheck(
            self.user_id,
            **self.paycheck_values(
                pay_date="2026-05-15",
                actual_net_cents=340000,
            ),
        )

        response = self.client.get("/?month=2026-04&year=2026")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"$3,300.00", response.data)
        self.assertIn(b"actual paycheck deposits", response.data)
        self.assertIn(b"Payroll deductions are not", response.data)
        self.assertIn(b"2026 recorded net cash flow", response.data)
        self.assertIn(b"$6,700.00", response.data)
        self.assertNotIn(b"$13,300.00", response.data)

        # Net worth uses the reported vested balance only. It excludes the
        # $2,000 unvested balance and does not add $750 of contributions.
        self.assertIn(b"$10,000.00", response.data)
        self.assertNotIn(b"$12,000.00", response.data)
        self.assertNotIn(b"$10,750.00", response.data)

        empty_year = self.client.get("/?month=2025-04&year=2025")
        self.assertIn(b"No recorded history for 2025", empty_year.data)

    def test_edit_replaces_linked_deductions_and_contributions(self):
        paycheck_id = database.add_paycheck(
            self.user_id,
            **self.paycheck_values(),
        )
        updated_values = self.paycheck_values(
            pay_date="2026-05-01",
            gross_pay_cents=600000,
            employee_401k_cents=30000,
            employer_match_cents=15000,
            employer_match_vested=True,
            actual_net_cents=430000,
            deductions=[{"name": "Transit", "amount_cents": 10000}],
        )

        updated = database.update_paycheck(
            self.user_id,
            paycheck_id,
            **updated_values,
        )

        self.assertTrue(updated)
        paycheck = database.get_paychecks(self.user_id)[0]
        self.assertEqual(paycheck["pay_date"], "2026-05-01")
        self.assertEqual(paycheck["deductions"], [
            {
                "id": paycheck["deductions"][0]["id"],
                "name": "Transit",
                "amount_cents": 10000,
            }
        ])
        contributions = database.get_retirement_contributions(self.user_id)
        self.assertEqual(len(contributions), 2)
        self.assertEqual(
            {
                item["contribution_type"]: (
                    item["amount_cents"], item["vested"]
                )
                for item in contributions
            },
            {
                "employee": (30000, 1),
                "employer_match": (15000, 1),
            },
        )

        updated_dashboard = self.client.get("/?month=2026-05&year=2026")
        self.assertIn(b"$4,300.00", updated_dashboard.data)
        self.assertIn(b"actual paycheck deposits", updated_dashboard.data)

        self.assertTrue(database.delete_paycheck(self.user_id, paycheck_id))
        self.assertEqual(database.get_paychecks(self.user_id), [])
        self.assertEqual(database.get_retirement_contributions(self.user_id), [])
        account = database.get_retirement_accounts(self.user_id)[0]
        self.assertEqual(account["employee_contributions_cents"], 0)
        self.assertEqual(account["vested_match_contributions_cents"], 0)
        deleted_dashboard = self.client.get("/?month=2026-05&year=2026")
        self.assertIn(b"No recorded history for 2026", deleted_dashboard.data)

    def test_route_crud_and_custom_deduction_names(self):
        response = self.client.post("/paychecks/add", data=self.paycheck_form())
        self.assertEqual(response.status_code, 302)
        paycheck = database.get_paychecks(self.user_id)[0]
        self.assertEqual(
            [item["name"] for item in paycheck["deductions"]],
            ["Parking", "Union dues"],
        )

        manage_page = self.client.get("/add")
        self.assertIn(b"Expected net", manage_page.data)
        self.assertIn(b"-$25.00", manage_page.data)
        self.assertIn(b"Union dues", manage_page.data)
        self.assertIn(b"$125.00", manage_page.data)
        self.assertIn(b"unvested", manage_page.data)

        delete_response = self.client.post(
            f"/paychecks/{paycheck['id']}/delete"
        )
        self.assertEqual(delete_response.status_code, 302)
        self.assertEqual(database.get_paychecks(self.user_id), [])

    def test_validation_and_user_isolation(self):
        with self.assertRaisesRegex(ValueError, "cannot exceed gross pay"):
            database.add_paycheck(
                self.user_id,
                **self.paycheck_values(
                    gross_pay_cents=10000,
                    federal_tax_cents=20000,
                ),
            )

        with self.assertRaisesRegex(ValueError, "Choose a 401"):
            database.add_paycheck(
                self.user_id,
                **self.paycheck_values(retirement_account_id=None),
            )

        other_account_id = database.add_retirement_account(
            self.other_user_id,
            "Other user's account",
            500000,
            0,
            "2026-04-01",
        )
        with self.assertRaisesRegex(ValueError, "your own"):
            database.add_paycheck(
                self.user_id,
                **self.paycheck_values(
                    retirement_account_id=other_account_id
                ),
            )

        paycheck_id = database.add_paycheck(
            self.user_id,
            **self.paycheck_values(),
        )
        self.login_as(self.other_user_id)
        manage_page = self.client.get("/add")
        self.assertNotIn(b"Example Company", manage_page.data)
        self.assertNotIn(b"Private Employer Plan", manage_page.data)

        safe_values = self.paycheck_form(
            employee_401k="0",
            employer_match="0",
            retirement_account_id="",
        )
        edit_response = self.client.post(
            f"/paychecks/{paycheck_id}/edit",
            data=safe_values,
        )
        delete_response = self.client.post(
            f"/paychecks/{paycheck_id}/delete"
        )
        account_edit_response = self.client.post(
            f"/retirement-accounts/{self.account_id}/edit",
            data={
                "name": "Taken account",
                "vested_balance": "1.00",
                "unvested_balance": "0",
                "balance_date": "2026-04-01",
            },
        )

        self.assertEqual(edit_response.status_code, 404)
        self.assertEqual(delete_response.status_code, 404)
        self.assertEqual(account_edit_response.status_code, 404)
        self.assertEqual(
            database.get_paychecks(self.user_id)[0]["employer"],
            "Example Company",
        )

    def test_linked_account_cannot_be_deleted_before_paycheck(self):
        paycheck_id = database.add_paycheck(
            self.user_id,
            **self.paycheck_values(),
        )

        with self.assertRaisesRegex(ValueError, "linked paychecks"):
            database.delete_retirement_account(
                self.user_id,
                self.account_id,
            )

        database.delete_paycheck(self.user_id, paycheck_id)
        self.assertTrue(
            database.delete_retirement_account(
                self.user_id,
                self.account_id,
            )
        )


if __name__ == "__main__":
    unittest.main()
