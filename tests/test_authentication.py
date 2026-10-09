import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from werkzeug.security import check_password_hash

os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("FINANCE_SKIP_DATABASE_INIT", "1")

import app as app_module
import create_account
import database


class AuthenticationTestCase(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.original_database_path = database.DATABASE_PATH
        self.original_config = {
            "TESTING": app_module.app.config.get("TESTING"),
            "WTF_CSRF_ENABLED": app_module.app.config.get(
                "WTF_CSRF_ENABLED"
            ),
            "LOGIN_RATE_LIMIT_ATTEMPTS": app_module.app.config[
                "LOGIN_RATE_LIMIT_ATTEMPTS"
            ],
            "REGISTRATION_RATE_LIMIT_ATTEMPTS": app_module.app.config[
                "REGISTRATION_RATE_LIMIT_ATTEMPTS"
            ],
            "AUTH_RATE_LIMIT_WINDOW_SECONDS": app_module.app.config[
                "AUTH_RATE_LIMIT_WINDOW_SECONDS"
            ],
        }
        database.DATABASE_PATH = (
            Path(self.temporary_directory.name) / "test-finance.db"
        )
        database.initialize_database()
        self.existing_user_id = database.create_user(
            "existing_user",
            "existing-password",
        )
        database.update_income(self.existing_user_id, 765432, 123456)
        database.add_expense(
            self.existing_user_id,
            "Private family expense",
            5000,
            "Private category",
        )

        app_module.app.config.update(
            TESTING=True,
            WTF_CSRF_ENABLED=False,
            LOGIN_RATE_LIMIT_ATTEMPTS=10,
            REGISTRATION_RATE_LIMIT_ATTEMPTS=10,
            AUTH_RATE_LIMIT_WINDOW_SECONDS=600,
        )
        app_module.auth_rate_limiter.clear()
        self.client = app_module.app.test_client()

    def tearDown(self):
        app_module.auth_rate_limiter.clear()
        app_module.app.config.update(self.original_config)
        database.DATABASE_PATH = self.original_database_path
        self.temporary_directory.cleanup()

    def registration_form(self, **overrides):
        values = {
            "username": "New_Household",
            "password": "secure-password-123",
            "confirm_password": "secure-password-123",
        }
        values.update(overrides)
        return values

    def test_successful_registration_login_and_empty_dashboard(self):
        password = "secure-password-123"
        response = self.client.post(
            "/register",
            data=self.registration_form(password=password,
                                        confirm_password=password),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/login")

        created_user = database.get_user_by_username("new_household")
        self.assertIsNotNone(created_user)
        self.assertNotEqual(created_user["password_hash"], password)
        self.assertNotIn(password, created_user["password_hash"])
        self.assertTrue(check_password_hash(
            created_user["password_hash"],
            password,
        ))
        self.assertEqual(
            database.get_income(created_user["id"]),
            {"Your income": 0, "Spouse income": 0},
        )
        self.assertEqual(database.get_expenses(created_user["id"]), [])

        login_page = self.client.get("/login")
        self.assertIn(b"Account created. You can now log in.", login_page.data)

        response = self.client.post(
            "/login",
            data={"username": " NEW_HOUSEHOLD ", "password": password},
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"new_household", response.data)
        self.assertNotIn(b"Private family expense", response.data)
        self.assertNotIn(b"Private category", response.data)

    def test_duplicate_username_is_handled_and_username_is_retained(self):
        response = self.client.post(
            "/register",
            data=self.registration_form(username=" EXISTING_USER "),
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"That username already exists.", response.data)
        self.assertIn(b'value="EXISTING_USER"', response.data)
        self.assertNotIn(b"secure-password-123", response.data)

    def test_login_and_logout_end_the_authenticated_session(self):
        login_response = self.client.post(
            "/login",
            data={
                "username": "existing_user",
                "password": "existing-password",
            },
        )
        self.assertEqual(login_response.status_code, 302)
        self.assertEqual(self.client.get("/").status_code, 200)

        logout_response = self.client.post("/logout")
        self.assertEqual(logout_response.status_code, 302)
        self.assertEqual(logout_response.headers["Location"], "/login")
        protected_response = self.client.get("/")
        self.assertEqual(protected_response.status_code, 302)
        self.assertIn("/login", protected_response.headers["Location"])

    def test_registration_validation_errors(self):
        cases = (
            (
                self.registration_form(username="bad name"),
                b"Use letters, numbers, and underscores",
            ),
            (
                self.registration_form(password="short",
                                       confirm_password="short"),
                b"Password must contain 12",
            ),
            (
                self.registration_form(confirm_password="different-value"),
                b"Passwords do not match.",
            ),
        )

        for form, expected_error in cases:
            with self.subTest(expected_error=expected_error):
                response = self.client.post("/register", data=form)
                self.assertEqual(response.status_code, 200)
                self.assertIn(expected_error, response.data)
                self.assertNotIn(form["password"].encode(), response.data)
                app_module.auth_rate_limiter.clear()

    def test_login_error_retains_only_safely_rendered_username(self):
        response = self.client.post(
            "/login",
            data={
                "username": '<script id="unsafe">',
                "password": "not-the-right-password",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Incorrect username or password.", response.data)
        self.assertIn(b"&lt;script id=&#34;unsafe&#34;&gt;", response.data)
        self.assertNotIn(b'<script id="unsafe">', response.data)
        self.assertNotIn(b"not-the-right-password", response.data)

    def test_login_and_registration_require_csrf_tokens(self):
        app_module.app.config["WTF_CSRF_ENABLED"] = True
        client = app_module.app.test_client()

        login_response = client.post(
            "/login",
            data={"username": "existing_user", "password": "existing-password"},
        )
        registration_response = client.post(
            "/register",
            data=self.registration_form(),
        )

        self.assertEqual(login_response.status_code, 400)
        self.assertEqual(registration_response.status_code, 400)
        self.assertIsNone(database.get_user_by_username("new_household"))

        page = client.get("/register")
        token_match = re.search(
            rb'name="csrf_token"\s+value="([^"]+)"',
            page.data,
        )
        self.assertIsNotNone(token_match)
        valid_response = client.post(
            "/register",
            data={
                **self.registration_form(),
                "csrf_token": token_match.group(1).decode(),
            },
        )
        self.assertEqual(valid_response.status_code, 302)

    def test_failed_authentication_attempts_are_rate_limited(self):
        app_module.app.config.update(
            LOGIN_RATE_LIMIT_ATTEMPTS=2,
            REGISTRATION_RATE_LIMIT_ATTEMPTS=2,
        )

        for _ in range(2):
            response = self.client.post(
                "/login",
                data={"username": "nobody", "password": "wrong-password"},
            )
            self.assertEqual(response.status_code, 200)

        limited_login = self.client.post(
            "/login",
            data={"username": "nobody", "password": "wrong-password"},
        )
        self.assertEqual(limited_login.status_code, 429)
        self.assertIn("Retry-After", limited_login.headers)

        for _ in range(2):
            response = self.client.post(
                "/register",
                data=self.registration_form(confirm_password="does-not-match"),
            )
            self.assertEqual(response.status_code, 200)

        limited_registration = self.client.post(
            "/register",
            data=self.registration_form(confirm_password="does-not-match"),
        )
        self.assertEqual(limited_registration.status_code, 429)

    def test_password_controls_are_independent_and_accessible(self):
        login_page = self.client.get("/login").data
        registration_page = self.client.get("/register").data

        self.assertIn(b'autocomplete="current-password"', login_page)
        self.assertIn(b'aria-controls="password"', login_page)
        self.assertIn(b'type="button"', login_page)

        self.assertEqual(
            registration_page.count(b'autocomplete="new-password"'),
            2,
        )
        self.assertIn(b'aria-controls="password"', registration_page)
        self.assertIn(
            b'aria-controls="confirm-password"',
            registration_page,
        )
        self.assertEqual(
            registration_page.count(b'aria-pressed="false"'),
            2,
        )
        self.assertNotIn(b'name="password" value=', registration_page)
        self.assertNotIn(b'name="confirm_password" value=', registration_page)

    def test_command_line_account_creation_still_uses_shared_helper(self):
        with (
            patch("builtins.input", return_value="Cli_User"),
            patch(
                "create_account.getpass",
                side_effect=["cli-secure-password", "cli-secure-password"],
            ),
            patch("builtins.print") as print_mock,
        ):
            create_account.main()

        created_user = database.get_user_by_username("cli_user")
        self.assertIsNotNone(created_user)
        self.assertTrue(check_password_hash(
            created_user["password_hash"],
            "cli-secure-password",
        ))
        self.assertIn(
            "Account created successfully",
            print_mock.call_args.args[0],
        )


if __name__ == "__main__":
    unittest.main()
