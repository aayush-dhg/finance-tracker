import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("FINANCE_SKIP_DATABASE_INIT", "1")

import app as app_module
import database


class CreditCardTestCase(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.original_database_path = database.DATABASE_PATH
        database.DATABASE_PATH = (
            Path(self.temporary_directory.name) / "test-finance.db"
        )
        database.initialize_database()

        self.user_id = database.create_user(
            "first_user", "a-secure-password"
        )
        self.other_user_id = database.create_user(
            "second_user", "another-secure-password"
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

    def card_form(self, **overrides):
        values = {
            "nickname": "Everyday Visa",
            "balance": "1234.56",
            "apr": "24.99",
            "minimum_payment": "45.67",
            "due_day": "18",
        }
        values.update(overrides)
        return values

    def test_add_edit_and_delete_card(self):
        self.login_as(self.user_id)

        response = self.client.post("/cards/add", data=self.card_form())
        self.assertEqual(response.status_code, 302)

        cards = database.get_credit_cards(self.user_id)
        self.assertEqual(len(cards), 1)
        card = cards[0]
        self.assertEqual(card["nickname"], "Everyday Visa")
        self.assertEqual(card["balance_cents"], 123456)
        self.assertEqual(card["apr_basis_points"], 2499)
        self.assertEqual(card["minimum_payment_cents"], 4567)
        self.assertEqual(card["due_day"], 18)

        response = self.client.post(
            f"/cards/{card['id']}/edit",
            data=self.card_form(
                nickname="Travel Card",
                balance="1000.01",
                apr="19.50",
                minimum_payment="40.00",
                due_day="7",
            ),
        )
        self.assertEqual(response.status_code, 302)

        edited = database.get_credit_cards(self.user_id)[0]
        self.assertEqual(edited["nickname"], "Travel Card")
        self.assertEqual(edited["balance_cents"], 100001)
        self.assertEqual(edited["apr_basis_points"], 1950)
        self.assertEqual(edited["minimum_payment_cents"], 4000)
        self.assertEqual(edited["due_day"], 7)

        response = self.client.post(f"/cards/{card['id']}/delete")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(database.get_credit_cards(self.user_id), [])

    def test_card_validation_rejects_bad_values(self):
        self.login_as(self.user_id)

        invalid_forms = (
            self.card_form(nickname=""),
            self.card_form(balance="-0.01"),
            self.card_form(balance="1.001"),
            self.card_form(apr="100.01"),
            self.card_form(apr="12.345"),
            self.card_form(minimum_payment="-1"),
            self.card_form(due_day="0"),
            self.card_form(due_day="32"),
            self.card_form(due_day="1.5"),
        )

        for form in invalid_forms:
            with self.subTest(form=form):
                response = self.client.post("/cards/add", data=form)
                self.assertEqual(response.status_code, 302)

        self.assertEqual(database.get_credit_cards(self.user_id), [])

    def test_cards_are_private_to_their_owner(self):
        card_id = database.add_credit_card(
            self.user_id,
            "Private Card",
            90000,
            2000,
            3000,
            12,
        )
        database.add_credit_card(
            self.other_user_id,
            "Second User Card",
            10000,
            1000,
            1000,
            2,
        )
        self.login_as(self.other_user_id)

        page = self.client.get("/add")
        self.assertEqual(page.status_code, 200)
        self.assertNotIn(b"Private Card", page.data)
        self.assertIn(b"Second User Card", page.data)

        edit_response = self.client.post(
            f"/cards/{card_id}/edit",
            data=self.card_form(nickname="Stolen Card"),
        )
        delete_response = self.client.post(f"/cards/{card_id}/delete")

        self.assertEqual(edit_response.status_code, 404)
        self.assertEqual(delete_response.status_code, 404)
        owner_card = database.get_credit_cards(self.user_id)[0]
        self.assertEqual(owner_card["nickname"], "Private Card")

    def test_budget_includes_card_minimums_and_debt_totals(self):
        database.update_income(self.user_id, 500000, 100000)
        database.add_expense(self.user_id, "Housing", 150000)
        database.add_credit_card(
            self.user_id, "Card One", 230000, 2100, 7500, 5
        )
        database.add_credit_card(
            self.user_id, "Card Two", 70000, 1800, 2500, 20
        )
        self.login_as(self.user_id)

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"$3,000.00", response.data)
        self.assertIn(b"$100.00", response.data)
        self.assertIn(b"$4,400.00", response.data)


if __name__ == "__main__":
    unittest.main()
