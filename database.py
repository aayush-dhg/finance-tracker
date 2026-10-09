import os
import sqlite3
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from werkzeug.security import generate_password_hash


load_dotenv(Path(__file__).resolve().parent / ".env")

DEFAULT_DATABASE_PATH = Path(__file__).resolve().parent / "finance.db"
DATABASE_PATH = Path(
    os.environ.get("FINANCE_DATABASE_PATH", DEFAULT_DATABASE_PATH)
).expanduser().resolve()
LOAN_TYPES = ("auto", "mortgage", "personal", "individual")
DEBT_PAYMENT_TYPES = ("credit_card", "loan", "other")


def initialize_database():
    connection = sqlite3.connect(DATABASE_PATH)

    try:
        connection.execute("PRAGMA foreign_keys = ON")

        with connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL
                )
            """)

            connection.execute("""
                CREATE TABLE IF NOT EXISTS income (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    amount_cents INTEGER NOT NULL
                        CHECK (amount_cents >= 0)
                )
            """)

            connection.execute("""
                CREATE TABLE IF NOT EXISTS user_income (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    amount_cents INTEGER NOT NULL
                        CHECK (amount_cents >= 0),
                    FOREIGN KEY (user_id) REFERENCES users(id),
                    UNIQUE (user_id, name)
                )
            """)

            connection.execute("""
                CREATE TABLE IF NOT EXISTS expenses (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'Uncategorized',
                    amount_cents INTEGER NOT NULL
                        CHECK (amount_cents > 0),
                    recorded_on TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """)

            expense_columns = {
                row[1]
                for row in connection.execute(
                    "PRAGMA table_info(expenses)"
                ).fetchall()
            }

            if "category" not in expense_columns:
                connection.execute("""
                    ALTER TABLE expenses
                    ADD COLUMN category TEXT NOT NULL
                        DEFAULT 'Uncategorized'
                """)

            if "recorded_on" not in expense_columns:
                connection.execute("""
                    ALTER TABLE expenses
                    ADD COLUMN recorded_on TEXT
                """)

            connection.execute("""
                CREATE TABLE IF NOT EXISTS credit_cards (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    nickname TEXT NOT NULL,
                    balance_cents INTEGER NOT NULL
                        CHECK (balance_cents >= 0),
                    apr_basis_points INTEGER NOT NULL
                        CHECK (
                            apr_basis_points >= 0
                            AND apr_basis_points <= 10000
                        ),
                    minimum_payment_cents INTEGER NOT NULL
                        CHECK (minimum_payment_cents >= 0),
                    due_day INTEGER NOT NULL
                        CHECK (due_day BETWEEN 1 AND 31),
                    FOREIGN KEY (user_id) REFERENCES users(id)
                        ON DELETE CASCADE
                )
            """)

            connection.execute("""
                CREATE INDEX IF NOT EXISTS credit_cards_user_id_idx
                ON credit_cards(user_id)
            """)

            connection.execute("""
                CREATE TABLE IF NOT EXISTS loans (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    loan_type TEXT NOT NULL
                        CHECK (
                            loan_type IN (
                                'auto',
                                'mortgage',
                                'personal',
                                'individual'
                            )
                        ),
                    balance_cents INTEGER NOT NULL
                        CHECK (balance_cents >= 0),
                    apr_basis_points INTEGER NOT NULL
                        CHECK (
                            apr_basis_points >= 0
                            AND apr_basis_points <= 10000
                        ),
                    monthly_payment_cents INTEGER NOT NULL
                        CHECK (monthly_payment_cents >= 0),
                    due_day INTEGER NOT NULL
                        CHECK (due_day BETWEEN 1 AND 31),
                    FOREIGN KEY (user_id) REFERENCES users(id)
                        ON DELETE CASCADE
                )
            """)

            connection.execute("""
                CREATE INDEX IF NOT EXISTS loans_user_id_idx
                ON loans(user_id)
            """)

            connection.execute("""
                CREATE TABLE IF NOT EXISTS assets (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    balance_cents INTEGER NOT NULL
                        CHECK (balance_cents >= 0),
                    as_of_date TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                        ON DELETE CASCADE
                )
            """)

            connection.execute("""
                CREATE INDEX IF NOT EXISTS assets_user_id_idx
                ON assets(user_id)
            """)

            connection.execute("""
                CREATE TABLE IF NOT EXISTS income_records (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    amount_cents INTEGER NOT NULL
                        CHECK (amount_cents > 0),
                    recorded_on TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                        ON DELETE CASCADE
                )
            """)

            connection.execute("""
                CREATE INDEX IF NOT EXISTS income_records_user_date_idx
                ON income_records(user_id, recorded_on)
            """)

            connection.execute("""
                CREATE TABLE IF NOT EXISTS debt_payments (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    debt_type TEXT NOT NULL
                        CHECK (
                            debt_type IN (
                                'credit_card', 'loan', 'other'
                            )
                        ),
                    amount_cents INTEGER NOT NULL
                        CHECK (amount_cents > 0),
                    paid_on TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                        ON DELETE CASCADE
                )
            """)

            connection.execute("""
                CREATE INDEX IF NOT EXISTS debt_payments_user_date_idx
                ON debt_payments(user_id, paid_on)
            """)

            connection.execute("""
                CREATE TABLE IF NOT EXISTS retirement_accounts (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    vested_balance_cents INTEGER NOT NULL
                        CHECK (vested_balance_cents >= 0),
                    unvested_balance_cents INTEGER NOT NULL
                        CHECK (unvested_balance_cents >= 0),
                    balance_date TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                        ON DELETE CASCADE
                )
            """)

            connection.execute("""
                CREATE INDEX IF NOT EXISTS retirement_accounts_user_id_idx
                ON retirement_accounts(user_id)
            """)

            connection.execute("""
                CREATE TABLE IF NOT EXISTS paychecks (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    pay_date TEXT NOT NULL,
                    employee_name TEXT NOT NULL,
                    employer TEXT NOT NULL,
                    gross_pay_cents INTEGER NOT NULL
                        CHECK (gross_pay_cents > 0),
                    federal_tax_cents INTEGER NOT NULL
                        CHECK (federal_tax_cents >= 0),
                    state_tax_cents INTEGER NOT NULL
                        CHECK (state_tax_cents >= 0),
                    social_security_tax_cents INTEGER NOT NULL
                        CHECK (social_security_tax_cents >= 0),
                    medicare_tax_cents INTEGER NOT NULL
                        CHECK (medicare_tax_cents >= 0),
                    other_tax_cents INTEGER NOT NULL
                        CHECK (other_tax_cents >= 0),
                    health_insurance_cents INTEGER NOT NULL
                        CHECK (health_insurance_cents >= 0),
                    employee_401k_cents INTEGER NOT NULL
                        CHECK (employee_401k_cents >= 0),
                    actual_net_cents INTEGER NOT NULL
                        CHECK (actual_net_cents >= 0),
                    retirement_account_id INTEGER,
                    employer_match_cents INTEGER NOT NULL
                        CHECK (employer_match_cents >= 0),
                    employer_match_vested INTEGER NOT NULL
                        CHECK (employer_match_vested IN (0, 1)),
                    FOREIGN KEY (user_id) REFERENCES users(id)
                        ON DELETE CASCADE,
                    FOREIGN KEY (retirement_account_id)
                        REFERENCES retirement_accounts(id)
                        ON DELETE SET NULL
                )
            """)

            connection.execute("""
                CREATE INDEX IF NOT EXISTS paychecks_user_date_idx
                ON paychecks(user_id, pay_date)
            """)

            connection.execute("""
                CREATE TABLE IF NOT EXISTS paycheck_deductions (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    paycheck_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    amount_cents INTEGER NOT NULL
                        CHECK (amount_cents > 0),
                    FOREIGN KEY (user_id) REFERENCES users(id)
                        ON DELETE CASCADE,
                    FOREIGN KEY (paycheck_id) REFERENCES paychecks(id)
                        ON DELETE CASCADE
                )
            """)

            connection.execute("""
                CREATE TABLE IF NOT EXISTS retirement_contributions (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    paycheck_id INTEGER NOT NULL,
                    retirement_account_id INTEGER NOT NULL,
                    contribution_type TEXT NOT NULL
                        CHECK (
                            contribution_type IN (
                                'employee', 'employer_match'
                            )
                        ),
                    amount_cents INTEGER NOT NULL
                        CHECK (amount_cents > 0),
                    contribution_date TEXT NOT NULL,
                    vested INTEGER NOT NULL
                        CHECK (vested IN (0, 1)),
                    FOREIGN KEY (user_id) REFERENCES users(id)
                        ON DELETE CASCADE,
                    FOREIGN KEY (paycheck_id) REFERENCES paychecks(id)
                        ON DELETE CASCADE,
                    FOREIGN KEY (retirement_account_id)
                        REFERENCES retirement_accounts(id)
                        ON DELETE CASCADE,
                    UNIQUE (paycheck_id, contribution_type)
                )
            """)
    finally:
        connection.close()


def _validate_credit_card(
    nickname,
    balance_cents,
    apr_basis_points,
    minimum_payment_cents,
    due_day,
):
    nickname = nickname.strip()

    if not 1 <= len(nickname) <= 100:
        raise ValueError("Card nickname must contain 1–100 characters.")

    if type(balance_cents) is not int or balance_cents < 0:
        raise ValueError("Card balance must be zero or positive whole cents.")

    if (
        type(apr_basis_points) is not int
        or not 0 <= apr_basis_points <= 10000
    ):
        raise ValueError("APR must be between 0% and 100%.")

    if (
        type(minimum_payment_cents) is not int
        or minimum_payment_cents < 0
    ):
        raise ValueError(
            "Minimum payment must be zero or positive whole cents."
        )

    if type(due_day) is not int or not 1 <= due_day <= 31:
        raise ValueError("Due day must be between 1 and 31.")

    return nickname


def _validate_loan(
    name,
    loan_type,
    balance_cents,
    apr_basis_points,
    monthly_payment_cents,
    due_day,
):
    name = name.strip()

    if not 1 <= len(name) <= 100:
        raise ValueError("Loan name must contain 1–100 characters.")

    if loan_type not in LOAN_TYPES:
        raise ValueError("Choose a valid loan type.")

    if type(balance_cents) is not int or balance_cents < 0:
        raise ValueError("Loan balance must be zero or positive whole cents.")

    if (
        type(apr_basis_points) is not int
        or not 0 <= apr_basis_points <= 10000
    ):
        raise ValueError("APR must be between 0% and 100%.")

    if (
        type(monthly_payment_cents) is not int
        or monthly_payment_cents < 0
    ):
        raise ValueError(
            "Monthly payment must be zero or positive whole cents."
        )

    if type(due_day) is not int or not 1 <= due_day <= 31:
        raise ValueError("Due day must be between 1 and 31.")

    return name


def _validate_label(value, label, maximum_length=100):
    value = value.strip()

    if not 1 <= len(value) <= maximum_length:
        raise ValueError(
            f"{label} must contain 1–{maximum_length} characters."
        )

    return value


def _validate_category(category):
    return _validate_label(category, "Category", 50)


def _validate_positive_cents(amount_cents, label="Amount"):
    if type(amount_cents) is not int or amount_cents <= 0:
        raise ValueError(f"{label} must be positive whole cents.")


def _validate_nonnegative_cents(amount_cents, label="Balance"):
    if type(amount_cents) is not int or amount_cents < 0:
        raise ValueError(f"{label} must be zero or positive whole cents.")


def _validate_iso_date(raw_date, label="Date", optional=False):
    if optional and not raw_date:
        return None

    try:
        parsed_date = date.fromisoformat(raw_date)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be a valid date.")

    return parsed_date.isoformat()


def get_income(user_id):
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row

    try:
        rows = connection.execute("""
            SELECT name, amount_cents
            FROM user_income
            WHERE user_id = ?
        """, (user_id,)).fetchall()

        income = {
            "Your income": 0,
            "Spouse income": 0,
        }

        for row in rows:
            income[row["name"]] = row["amount_cents"]

        return income
    finally:
        connection.close()


def update_income(user_id, your_cents, spouse_cents):
    connection = sqlite3.connect(DATABASE_PATH)

    try:
        connection.execute("PRAGMA foreign_keys = ON")

        with connection:
            connection.executemany("""
                INSERT INTO user_income (
                    user_id, name, amount_cents
                )
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, name)
                DO UPDATE SET amount_cents = excluded.amount_cents
            """, [
                (user_id, "Your income", your_cents),
                (user_id, "Spouse income", spouse_cents),
            ])
    finally:
        connection.close()

def create_user(username, password):
    username = username.strip().lower()

    if not 3 <= len(username) <= 30:
        raise ValueError("Username must contain 3–30 characters.")

    if not all(
        character in "abcdefghijklmnopqrstuvwxyz0123456789_"
        for character in username
    ):
        raise ValueError(
            "Use letters, numbers, and underscores for your username."
        )

    if not 12 <= len(password) <= 128:
        raise ValueError("Password must contain 12–128 characters.")

    password_hash = generate_password_hash(password)
    connection = sqlite3.connect(DATABASE_PATH)

    try:
        with connection:
            cursor = connection.execute("""
                INSERT INTO users (username, password_hash)
                VALUES (?, ?)
            """, (username, password_hash))

            return cursor.lastrowid
    finally:
        connection.close()

def get_user_by_username(username):
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row

    try:
        return connection.execute("""
            SELECT id, username, password_hash
            FROM users
            WHERE username = ?
        """, (username.strip().lower(),)).fetchone()
    finally:
        connection.close()


def get_user_by_id(user_id):
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row

    try:
        return connection.execute("""
            SELECT id, username
            FROM users
            WHERE id = ?
        """, (user_id,)).fetchone()
    finally:
        connection.close()

def initialize_expenses():
    connection = sqlite3.connect(DATABASE_PATH)

    try:
        connection.execute("PRAGMA foreign_keys = ON")

        with connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS expenses (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    amount_cents INTEGER NOT NULL
                        CHECK (amount_cents > 0),
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """)
    finally:
        connection.close()

def add_expense(
    user_id,
    name,
    amount_cents,
    category="Uncategorized",
    recorded_on=None,
):
    name = _validate_label(name, "Expense name")
    category = _validate_category(category)
    _validate_positive_cents(amount_cents, "Expense amount")
    recorded_on = _validate_iso_date(
        recorded_on,
        "Expense date",
        optional=True,
    )

    connection = sqlite3.connect(DATABASE_PATH)

    try:
        connection.execute("PRAGMA foreign_keys = ON")

        with connection:
            cursor = connection.execute("""
                INSERT INTO expenses (
                    user_id,
                    name,
                    category,
                    amount_cents,
                    recorded_on
                )
                VALUES (?, ?, ?, ?, ?)
            """, (
                user_id,
                name,
                category,
                amount_cents,
                recorded_on,
            ))

            return cursor.lastrowid
    finally:
        connection.close()


def get_expenses(user_id):
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row

    try:
        rows = connection.execute("""
            SELECT id, name, category, amount_cents, recorded_on
            FROM expenses
            WHERE user_id = ?
            ORDER BY recorded_on IS NULL DESC, recorded_on DESC, id DESC
        """, (user_id,)).fetchall()

        return [dict(row) for row in rows]
    finally:
        connection.close()


def get_expense_categories(user_id):
    connection = sqlite3.connect(DATABASE_PATH)

    try:
        rows = connection.execute("""
            SELECT DISTINCT category
            FROM expenses
            WHERE user_id = ? AND trim(category) <> ''
            ORDER BY category COLLATE NOCASE
        """, (user_id,)).fetchall()

        return [row[0] for row in rows]
    finally:
        connection.close()


def update_expense(
    user_id,
    expense_id,
    name,
    amount_cents,
    category,
    recorded_on=None,
):
    name = _validate_label(name, "Expense name")
    category = _validate_category(category)
    _validate_positive_cents(amount_cents, "Expense amount")
    recorded_on = _validate_iso_date(
        recorded_on,
        "Expense date",
        optional=True,
    )
    connection = sqlite3.connect(DATABASE_PATH)

    try:
        with connection:
            cursor = connection.execute("""
                UPDATE expenses
                SET
                    name = ?,
                    category = ?,
                    amount_cents = ?,
                    recorded_on = ?
                WHERE id = ? AND user_id = ?
            """, (
                name,
                category,
                amount_cents,
                recorded_on,
                expense_id,
                user_id,
            ))

            return cursor.rowcount == 1
    finally:
        connection.close()

def delete_expense(user_id, expense_id):
    connection = sqlite3.connect(DATABASE_PATH)

    try:
        with connection:
            cursor = connection.execute("""
                DELETE FROM expenses
                WHERE id = ? AND user_id = ?
            """, (expense_id, user_id))

            return cursor.rowcount == 1
    finally:
        connection.close()


def add_credit_card(
    user_id,
    nickname,
    balance_cents,
    apr_basis_points,
    minimum_payment_cents,
    due_day,
):
    nickname = _validate_credit_card(
        nickname,
        balance_cents,
        apr_basis_points,
        minimum_payment_cents,
        due_day,
    )
    connection = sqlite3.connect(DATABASE_PATH)

    try:
        connection.execute("PRAGMA foreign_keys = ON")

        with connection:
            cursor = connection.execute("""
                INSERT INTO credit_cards (
                    user_id,
                    nickname,
                    balance_cents,
                    apr_basis_points,
                    minimum_payment_cents,
                    due_day
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                user_id,
                nickname,
                balance_cents,
                apr_basis_points,
                minimum_payment_cents,
                due_day,
            ))

            return cursor.lastrowid
    finally:
        connection.close()


def get_credit_cards(user_id):
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row

    try:
        rows = connection.execute("""
            SELECT
                id,
                nickname,
                balance_cents,
                apr_basis_points,
                minimum_payment_cents,
                due_day
            FROM credit_cards
            WHERE user_id = ?
            ORDER BY due_day, nickname COLLATE NOCASE, id
        """, (user_id,)).fetchall()

        return [dict(row) for row in rows]
    finally:
        connection.close()


def update_credit_card(
    user_id,
    card_id,
    nickname,
    balance_cents,
    apr_basis_points,
    minimum_payment_cents,
    due_day,
):
    nickname = _validate_credit_card(
        nickname,
        balance_cents,
        apr_basis_points,
        minimum_payment_cents,
        due_day,
    )
    connection = sqlite3.connect(DATABASE_PATH)

    try:
        with connection:
            cursor = connection.execute("""
                UPDATE credit_cards
                SET
                    nickname = ?,
                    balance_cents = ?,
                    apr_basis_points = ?,
                    minimum_payment_cents = ?,
                    due_day = ?
                WHERE id = ? AND user_id = ?
            """, (
                nickname,
                balance_cents,
                apr_basis_points,
                minimum_payment_cents,
                due_day,
                card_id,
                user_id,
            ))

            return cursor.rowcount == 1
    finally:
        connection.close()


def delete_credit_card(user_id, card_id):
    connection = sqlite3.connect(DATABASE_PATH)

    try:
        with connection:
            cursor = connection.execute("""
                DELETE FROM credit_cards
                WHERE id = ? AND user_id = ?
            """, (card_id, user_id))

            return cursor.rowcount == 1
    finally:
        connection.close()


def add_loan(
    user_id,
    name,
    loan_type,
    balance_cents,
    apr_basis_points,
    monthly_payment_cents,
    due_day,
):
    name = _validate_loan(
        name,
        loan_type,
        balance_cents,
        apr_basis_points,
        monthly_payment_cents,
        due_day,
    )
    connection = sqlite3.connect(DATABASE_PATH)

    try:
        connection.execute("PRAGMA foreign_keys = ON")

        with connection:
            cursor = connection.execute("""
                INSERT INTO loans (
                    user_id,
                    name,
                    loan_type,
                    balance_cents,
                    apr_basis_points,
                    monthly_payment_cents,
                    due_day
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id,
                name,
                loan_type,
                balance_cents,
                apr_basis_points,
                monthly_payment_cents,
                due_day,
            ))

            return cursor.lastrowid
    finally:
        connection.close()


def get_loans(user_id):
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row

    try:
        rows = connection.execute("""
            SELECT
                id,
                name,
                loan_type,
                balance_cents,
                apr_basis_points,
                monthly_payment_cents,
                due_day
            FROM loans
            WHERE user_id = ?
            ORDER BY due_day, name COLLATE NOCASE, id
        """, (user_id,)).fetchall()

        return [dict(row) for row in rows]
    finally:
        connection.close()


def update_loan(
    user_id,
    loan_id,
    name,
    loan_type,
    balance_cents,
    apr_basis_points,
    monthly_payment_cents,
    due_day,
):
    name = _validate_loan(
        name,
        loan_type,
        balance_cents,
        apr_basis_points,
        monthly_payment_cents,
        due_day,
    )
    connection = sqlite3.connect(DATABASE_PATH)

    try:
        with connection:
            cursor = connection.execute("""
                UPDATE loans
                SET
                    name = ?,
                    loan_type = ?,
                    balance_cents = ?,
                    apr_basis_points = ?,
                    monthly_payment_cents = ?,
                    due_day = ?
                WHERE id = ? AND user_id = ?
            """, (
                name,
                loan_type,
                balance_cents,
                apr_basis_points,
                monthly_payment_cents,
                due_day,
                loan_id,
                user_id,
            ))

            return cursor.rowcount == 1
    finally:
        connection.close()


def delete_loan(user_id, loan_id):
    connection = sqlite3.connect(DATABASE_PATH)

    try:
        with connection:
            cursor = connection.execute("""
                DELETE FROM loans
                WHERE id = ? AND user_id = ?
            """, (loan_id, user_id))

            return cursor.rowcount == 1
    finally:
        connection.close()


def add_asset(user_id, name, category, balance_cents, as_of_date):
    name = _validate_label(name, "Asset name")
    category = _validate_category(category)
    _validate_nonnegative_cents(balance_cents, "Asset balance")
    as_of_date = _validate_iso_date(as_of_date, "Asset date")
    connection = sqlite3.connect(DATABASE_PATH)

    try:
        connection.execute("PRAGMA foreign_keys = ON")

        with connection:
            cursor = connection.execute("""
                INSERT INTO assets (
                    user_id, name, category, balance_cents, as_of_date
                )
                VALUES (?, ?, ?, ?, ?)
            """, (
                user_id,
                name,
                category,
                balance_cents,
                as_of_date,
            ))

            return cursor.lastrowid
    finally:
        connection.close()


def get_assets(user_id):
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row

    try:
        rows = connection.execute("""
            SELECT id, name, category, balance_cents, as_of_date
            FROM assets
            WHERE user_id = ?
            ORDER BY balance_cents DESC, name COLLATE NOCASE, id
        """, (user_id,)).fetchall()

        return [dict(row) for row in rows]
    finally:
        connection.close()


def update_asset(
    user_id,
    asset_id,
    name,
    category,
    balance_cents,
    as_of_date,
):
    name = _validate_label(name, "Asset name")
    category = _validate_category(category)
    _validate_nonnegative_cents(balance_cents, "Asset balance")
    as_of_date = _validate_iso_date(as_of_date, "Asset date")
    connection = sqlite3.connect(DATABASE_PATH)

    try:
        with connection:
            cursor = connection.execute("""
                UPDATE assets
                SET
                    name = ?,
                    category = ?,
                    balance_cents = ?,
                    as_of_date = ?
                WHERE id = ? AND user_id = ?
            """, (
                name,
                category,
                balance_cents,
                as_of_date,
                asset_id,
                user_id,
            ))

            return cursor.rowcount == 1
    finally:
        connection.close()


def delete_asset(user_id, asset_id):
    connection = sqlite3.connect(DATABASE_PATH)

    try:
        with connection:
            cursor = connection.execute("""
                DELETE FROM assets
                WHERE id = ? AND user_id = ?
            """, (asset_id, user_id))

            return cursor.rowcount == 1
    finally:
        connection.close()


def add_income_record(user_id, name, amount_cents, recorded_on):
    name = _validate_label(name, "Income name")
    _validate_positive_cents(amount_cents, "Income amount")
    recorded_on = _validate_iso_date(recorded_on, "Income date")
    connection = sqlite3.connect(DATABASE_PATH)

    try:
        connection.execute("PRAGMA foreign_keys = ON")

        with connection:
            cursor = connection.execute("""
                INSERT INTO income_records (
                    user_id, name, amount_cents, recorded_on
                )
                VALUES (?, ?, ?, ?)
            """, (user_id, name, amount_cents, recorded_on))

            return cursor.lastrowid
    finally:
        connection.close()


def get_income_records(user_id):
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row

    try:
        rows = connection.execute("""
            SELECT id, name, amount_cents, recorded_on
            FROM income_records
            WHERE user_id = ?
            ORDER BY recorded_on DESC, id DESC
        """, (user_id,)).fetchall()

        return [dict(row) for row in rows]
    finally:
        connection.close()


def update_income_record(
    user_id,
    income_id,
    name,
    amount_cents,
    recorded_on,
):
    name = _validate_label(name, "Income name")
    _validate_positive_cents(amount_cents, "Income amount")
    recorded_on = _validate_iso_date(recorded_on, "Income date")
    connection = sqlite3.connect(DATABASE_PATH)

    try:
        with connection:
            cursor = connection.execute("""
                UPDATE income_records
                SET name = ?, amount_cents = ?, recorded_on = ?
                WHERE id = ? AND user_id = ?
            """, (
                name,
                amount_cents,
                recorded_on,
                income_id,
                user_id,
            ))

            return cursor.rowcount == 1
    finally:
        connection.close()


def delete_income_record(user_id, income_id):
    connection = sqlite3.connect(DATABASE_PATH)

    try:
        with connection:
            cursor = connection.execute("""
                DELETE FROM income_records
                WHERE id = ? AND user_id = ?
            """, (income_id, user_id))

            return cursor.rowcount == 1
    finally:
        connection.close()


def add_debt_payment(
    user_id,
    name,
    debt_type,
    amount_cents,
    paid_on,
):
    name = _validate_label(name, "Debt payment name")

    if debt_type not in DEBT_PAYMENT_TYPES:
        raise ValueError("Choose a valid debt payment type.")

    _validate_positive_cents(amount_cents, "Debt payment")
    paid_on = _validate_iso_date(paid_on, "Payment date")
    connection = sqlite3.connect(DATABASE_PATH)

    try:
        connection.execute("PRAGMA foreign_keys = ON")

        with connection:
            cursor = connection.execute("""
                INSERT INTO debt_payments (
                    user_id, name, debt_type, amount_cents, paid_on
                )
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, name, debt_type, amount_cents, paid_on))

            return cursor.lastrowid
    finally:
        connection.close()


def get_debt_payments(user_id):
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row

    try:
        rows = connection.execute("""
            SELECT id, name, debt_type, amount_cents, paid_on
            FROM debt_payments
            WHERE user_id = ?
            ORDER BY paid_on DESC, id DESC
        """, (user_id,)).fetchall()

        return [dict(row) for row in rows]
    finally:
        connection.close()


def update_debt_payment(
    user_id,
    payment_id,
    name,
    debt_type,
    amount_cents,
    paid_on,
):
    name = _validate_label(name, "Debt payment name")

    if debt_type not in DEBT_PAYMENT_TYPES:
        raise ValueError("Choose a valid debt payment type.")

    _validate_positive_cents(amount_cents, "Debt payment")
    paid_on = _validate_iso_date(paid_on, "Payment date")
    connection = sqlite3.connect(DATABASE_PATH)

    try:
        with connection:
            cursor = connection.execute("""
                UPDATE debt_payments
                SET
                    name = ?,
                    debt_type = ?,
                    amount_cents = ?,
                    paid_on = ?
                WHERE id = ? AND user_id = ?
            """, (
                name,
                debt_type,
                amount_cents,
                paid_on,
                payment_id,
                user_id,
            ))

            return cursor.rowcount == 1
    finally:
        connection.close()


def delete_debt_payment(user_id, payment_id):
    connection = sqlite3.connect(DATABASE_PATH)

    try:
        with connection:
            cursor = connection.execute("""
                DELETE FROM debt_payments
                WHERE id = ? AND user_id = ?
            """, (payment_id, user_id))

            return cursor.rowcount == 1
    finally:
        connection.close()


def add_retirement_account(
    user_id,
    name,
    vested_balance_cents,
    unvested_balance_cents,
    balance_date,
):
    name = _validate_label(name, "401(k) account name")
    _validate_nonnegative_cents(
        vested_balance_cents,
        "Vested retirement balance",
    )
    _validate_nonnegative_cents(
        unvested_balance_cents,
        "Unvested retirement balance",
    )
    balance_date = _validate_iso_date(balance_date, "Balance date")
    connection = sqlite3.connect(DATABASE_PATH)

    try:
        connection.execute("PRAGMA foreign_keys = ON")

        with connection:
            cursor = connection.execute("""
                INSERT INTO retirement_accounts (
                    user_id,
                    name,
                    vested_balance_cents,
                    unvested_balance_cents,
                    balance_date
                )
                VALUES (?, ?, ?, ?, ?)
            """, (
                user_id,
                name,
                vested_balance_cents,
                unvested_balance_cents,
                balance_date,
            ))

            return cursor.lastrowid
    finally:
        connection.close()


def get_retirement_accounts(user_id):
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row

    try:
        rows = connection.execute("""
            SELECT
                account.id,
                account.name,
                account.vested_balance_cents,
                account.unvested_balance_cents,
                account.balance_date,
                COALESCE(SUM(
                    CASE
                        WHEN contribution.contribution_type = 'employee'
                        THEN contribution.amount_cents
                        ELSE 0
                    END
                ), 0) AS employee_contributions_cents,
                COALESCE(SUM(
                    CASE
                        WHEN contribution.contribution_type = 'employer_match'
                            AND contribution.vested = 1
                        THEN contribution.amount_cents
                        ELSE 0
                    END
                ), 0) AS vested_match_contributions_cents,
                COALESCE(SUM(
                    CASE
                        WHEN contribution.contribution_type = 'employer_match'
                            AND contribution.vested = 0
                        THEN contribution.amount_cents
                        ELSE 0
                    END
                ), 0) AS unvested_match_contributions_cents
            FROM retirement_accounts AS account
            LEFT JOIN retirement_contributions AS contribution
                ON contribution.retirement_account_id = account.id
                AND contribution.user_id = account.user_id
            WHERE account.user_id = ?
            GROUP BY account.id
            ORDER BY account.name COLLATE NOCASE, account.id
        """, (user_id,)).fetchall()

        return [dict(row) for row in rows]
    finally:
        connection.close()


def update_retirement_account(
    user_id,
    account_id,
    name,
    vested_balance_cents,
    unvested_balance_cents,
    balance_date,
):
    name = _validate_label(name, "401(k) account name")
    _validate_nonnegative_cents(
        vested_balance_cents,
        "Vested retirement balance",
    )
    _validate_nonnegative_cents(
        unvested_balance_cents,
        "Unvested retirement balance",
    )
    balance_date = _validate_iso_date(balance_date, "Balance date")
    connection = sqlite3.connect(DATABASE_PATH)

    try:
        with connection:
            cursor = connection.execute("""
                UPDATE retirement_accounts
                SET
                    name = ?,
                    vested_balance_cents = ?,
                    unvested_balance_cents = ?,
                    balance_date = ?
                WHERE id = ? AND user_id = ?
            """, (
                name,
                vested_balance_cents,
                unvested_balance_cents,
                balance_date,
                account_id,
                user_id,
            ))

            return cursor.rowcount == 1
    finally:
        connection.close()


def delete_retirement_account(user_id, account_id):
    connection = sqlite3.connect(DATABASE_PATH)

    try:
        connection.execute("PRAGMA foreign_keys = ON")

        with connection:
            linked_paycheck = connection.execute("""
                SELECT id
                FROM paychecks
                WHERE retirement_account_id = ? AND user_id = ?
                LIMIT 1
            """, (account_id, user_id)).fetchone()

            if linked_paycheck is not None:
                raise ValueError(
                    "Edit or delete linked paychecks before deleting this "
                    "401(k) account."
                )

            cursor = connection.execute("""
                DELETE FROM retirement_accounts
                WHERE id = ? AND user_id = ?
            """, (account_id, user_id))

            return cursor.rowcount == 1
    finally:
        connection.close()


def _validate_paycheck(
    pay_date,
    employee_name,
    employer,
    gross_pay_cents,
    federal_tax_cents,
    state_tax_cents,
    social_security_tax_cents,
    medicare_tax_cents,
    other_tax_cents,
    health_insurance_cents,
    employee_401k_cents,
    actual_net_cents,
    retirement_account_id,
    employer_match_cents,
    employer_match_vested,
    deductions,
):
    pay_date = _validate_iso_date(pay_date, "Pay date")
    employee_name = _validate_label(
        employee_name,
        "Employee or household member",
    )
    employer = _validate_label(employer, "Employer or income source")
    _validate_positive_cents(gross_pay_cents, "Gross pay")

    deduction_fields = (
        (federal_tax_cents, "Federal tax"),
        (state_tax_cents, "State tax"),
        (social_security_tax_cents, "Social Security tax"),
        (medicare_tax_cents, "Medicare tax"),
        (other_tax_cents, "Other tax"),
        (health_insurance_cents, "Health insurance deduction"),
        (employee_401k_cents, "Employee 401(k) contribution"),
        (employer_match_cents, "Employer 401(k) match"),
    )

    for amount_cents, label in deduction_fields:
        _validate_nonnegative_cents(amount_cents, label)

    _validate_nonnegative_cents(actual_net_cents, "Actual net deposit")

    if type(employer_match_vested) is not bool:
        raise ValueError("Employer match vesting must be selected.")

    if retirement_account_id is not None and (
        type(retirement_account_id) is not int
        or retirement_account_id <= 0
    ):
        raise ValueError("Choose a valid 401(k) account.")

    if (
        employee_401k_cents > 0 or employer_match_cents > 0
    ) and retirement_account_id is None:
        raise ValueError(
            "Choose a 401(k) account when recording retirement contributions."
        )

    clean_deductions = []

    for deduction in deductions:
        name = _validate_label(deduction["name"], "Deduction name")
        amount_cents = deduction["amount_cents"]
        _validate_positive_cents(amount_cents, f"{name} deduction")
        clean_deductions.append(
            {"name": name, "amount_cents": amount_cents}
        )

    payroll_deductions_cents = (
        federal_tax_cents
        + state_tax_cents
        + social_security_tax_cents
        + medicare_tax_cents
        + other_tax_cents
        + health_insurance_cents
        + employee_401k_cents
        + sum(item["amount_cents"] for item in clean_deductions)
    )

    if payroll_deductions_cents > gross_pay_cents:
        raise ValueError("Employee payroll deductions cannot exceed gross pay.")

    return {
        "pay_date": pay_date,
        "employee_name": employee_name,
        "employer": employer,
        "deductions": clean_deductions,
        "expected_net_cents": gross_pay_cents - payroll_deductions_cents,
    }


def _ensure_owned_retirement_account(
    connection,
    user_id,
    retirement_account_id,
):
    if retirement_account_id is None:
        return

    owned_account = connection.execute("""
        SELECT id
        FROM retirement_accounts
        WHERE id = ? AND user_id = ?
    """, (retirement_account_id, user_id)).fetchone()

    if owned_account is None:
        raise ValueError("Choose one of your own 401(k) accounts.")


def _replace_paycheck_children(
    connection,
    user_id,
    paycheck_id,
    pay_date,
    retirement_account_id,
    employee_401k_cents,
    employer_match_cents,
    employer_match_vested,
    deductions,
):
    connection.execute(
        "DELETE FROM paycheck_deductions WHERE paycheck_id = ?",
        (paycheck_id,),
    )
    connection.execute(
        "DELETE FROM retirement_contributions WHERE paycheck_id = ?",
        (paycheck_id,),
    )

    connection.executemany("""
        INSERT INTO paycheck_deductions (
            user_id, paycheck_id, name, amount_cents
        )
        VALUES (?, ?, ?, ?)
    """, [
        (
            user_id,
            paycheck_id,
            deduction["name"],
            deduction["amount_cents"],
        )
        for deduction in deductions
    ])

    contributions = []

    if employee_401k_cents > 0:
        contributions.append((
            user_id,
            paycheck_id,
            retirement_account_id,
            "employee",
            employee_401k_cents,
            pay_date,
            1,
        ))

    if employer_match_cents > 0:
        contributions.append((
            user_id,
            paycheck_id,
            retirement_account_id,
            "employer_match",
            employer_match_cents,
            pay_date,
            int(employer_match_vested),
        ))

    connection.executemany("""
        INSERT INTO retirement_contributions (
            user_id,
            paycheck_id,
            retirement_account_id,
            contribution_type,
            amount_cents,
            contribution_date,
            vested
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, contributions)


def add_paycheck(
    user_id,
    pay_date,
    employee_name,
    employer,
    gross_pay_cents,
    federal_tax_cents,
    state_tax_cents,
    social_security_tax_cents,
    medicare_tax_cents,
    other_tax_cents,
    health_insurance_cents,
    employee_401k_cents,
    actual_net_cents,
    retirement_account_id,
    employer_match_cents,
    employer_match_vested,
    deductions,
):
    clean = _validate_paycheck(
        pay_date,
        employee_name,
        employer,
        gross_pay_cents,
        federal_tax_cents,
        state_tax_cents,
        social_security_tax_cents,
        medicare_tax_cents,
        other_tax_cents,
        health_insurance_cents,
        employee_401k_cents,
        actual_net_cents,
        retirement_account_id,
        employer_match_cents,
        employer_match_vested,
        deductions,
    )
    connection = sqlite3.connect(DATABASE_PATH)

    try:
        connection.execute("PRAGMA foreign_keys = ON")

        with connection:
            _ensure_owned_retirement_account(
                connection,
                user_id,
                retirement_account_id,
            )
            cursor = connection.execute("""
                INSERT INTO paychecks (
                    user_id,
                    pay_date,
                    employee_name,
                    employer,
                    gross_pay_cents,
                    federal_tax_cents,
                    state_tax_cents,
                    social_security_tax_cents,
                    medicare_tax_cents,
                    other_tax_cents,
                    health_insurance_cents,
                    employee_401k_cents,
                    actual_net_cents,
                    retirement_account_id,
                    employer_match_cents,
                    employer_match_vested
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id,
                clean["pay_date"],
                clean["employee_name"],
                clean["employer"],
                gross_pay_cents,
                federal_tax_cents,
                state_tax_cents,
                social_security_tax_cents,
                medicare_tax_cents,
                other_tax_cents,
                health_insurance_cents,
                employee_401k_cents,
                actual_net_cents,
                retirement_account_id,
                employer_match_cents,
                int(employer_match_vested),
            ))
            paycheck_id = cursor.lastrowid
            _replace_paycheck_children(
                connection,
                user_id,
                paycheck_id,
                clean["pay_date"],
                retirement_account_id,
                employee_401k_cents,
                employer_match_cents,
                employer_match_vested,
                clean["deductions"],
            )

            return paycheck_id
    finally:
        connection.close()


def get_paychecks(user_id):
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row

    try:
        rows = connection.execute("""
            SELECT
                paycheck.*,
                account.name AS retirement_account_name
            FROM paychecks AS paycheck
            LEFT JOIN retirement_accounts AS account
                ON account.id = paycheck.retirement_account_id
                AND account.user_id = paycheck.user_id
            WHERE paycheck.user_id = ?
            ORDER BY paycheck.pay_date DESC, paycheck.id DESC
        """, (user_id,)).fetchall()
        paychecks = []

        for row in rows:
            paycheck = dict(row)
            deduction_rows = connection.execute("""
                SELECT id, name, amount_cents
                FROM paycheck_deductions
                WHERE paycheck_id = ? AND user_id = ?
                ORDER BY id
            """, (paycheck["id"], user_id)).fetchall()
            paycheck["deductions"] = [
                dict(deduction) for deduction in deduction_rows
            ]
            paycheck["taxes_cents"] = sum(
                paycheck[field]
                for field in (
                    "federal_tax_cents",
                    "state_tax_cents",
                    "social_security_tax_cents",
                    "medicare_tax_cents",
                    "other_tax_cents",
                )
            )
            paycheck["custom_deductions_cents"] = sum(
                deduction["amount_cents"]
                for deduction in paycheck["deductions"]
            )
            paycheck["payroll_deductions_cents"] = (
                paycheck["taxes_cents"]
                + paycheck["health_insurance_cents"]
                + paycheck["employee_401k_cents"]
                + paycheck["custom_deductions_cents"]
            )
            paycheck["expected_net_cents"] = (
                paycheck["gross_pay_cents"]
                - paycheck["payroll_deductions_cents"]
            )
            paycheck["discrepancy_cents"] = (
                paycheck["actual_net_cents"]
                - paycheck["expected_net_cents"]
            )
            paychecks.append(paycheck)

        return paychecks
    finally:
        connection.close()


def update_paycheck(
    user_id,
    paycheck_id,
    pay_date,
    employee_name,
    employer,
    gross_pay_cents,
    federal_tax_cents,
    state_tax_cents,
    social_security_tax_cents,
    medicare_tax_cents,
    other_tax_cents,
    health_insurance_cents,
    employee_401k_cents,
    actual_net_cents,
    retirement_account_id,
    employer_match_cents,
    employer_match_vested,
    deductions,
):
    clean = _validate_paycheck(
        pay_date,
        employee_name,
        employer,
        gross_pay_cents,
        federal_tax_cents,
        state_tax_cents,
        social_security_tax_cents,
        medicare_tax_cents,
        other_tax_cents,
        health_insurance_cents,
        employee_401k_cents,
        actual_net_cents,
        retirement_account_id,
        employer_match_cents,
        employer_match_vested,
        deductions,
    )
    connection = sqlite3.connect(DATABASE_PATH)

    try:
        connection.execute("PRAGMA foreign_keys = ON")

        with connection:
            _ensure_owned_retirement_account(
                connection,
                user_id,
                retirement_account_id,
            )
            cursor = connection.execute("""
                UPDATE paychecks
                SET
                    pay_date = ?,
                    employee_name = ?,
                    employer = ?,
                    gross_pay_cents = ?,
                    federal_tax_cents = ?,
                    state_tax_cents = ?,
                    social_security_tax_cents = ?,
                    medicare_tax_cents = ?,
                    other_tax_cents = ?,
                    health_insurance_cents = ?,
                    employee_401k_cents = ?,
                    actual_net_cents = ?,
                    retirement_account_id = ?,
                    employer_match_cents = ?,
                    employer_match_vested = ?
                WHERE id = ? AND user_id = ?
            """, (
                clean["pay_date"],
                clean["employee_name"],
                clean["employer"],
                gross_pay_cents,
                federal_tax_cents,
                state_tax_cents,
                social_security_tax_cents,
                medicare_tax_cents,
                other_tax_cents,
                health_insurance_cents,
                employee_401k_cents,
                actual_net_cents,
                retirement_account_id,
                employer_match_cents,
                int(employer_match_vested),
                paycheck_id,
                user_id,
            ))

            if cursor.rowcount != 1:
                return False

            _replace_paycheck_children(
                connection,
                user_id,
                paycheck_id,
                clean["pay_date"],
                retirement_account_id,
                employee_401k_cents,
                employer_match_cents,
                employer_match_vested,
                clean["deductions"],
            )

            return True
    finally:
        connection.close()


def delete_paycheck(user_id, paycheck_id):
    connection = sqlite3.connect(DATABASE_PATH)

    try:
        connection.execute("PRAGMA foreign_keys = ON")

        with connection:
            cursor = connection.execute("""
                DELETE FROM paychecks
                WHERE id = ? AND user_id = ?
            """, (paycheck_id, user_id))

            return cursor.rowcount == 1
    finally:
        connection.close()


def get_retirement_contributions(user_id):
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row

    try:
        rows = connection.execute("""
            SELECT
                contribution.id,
                contribution.paycheck_id,
                contribution.retirement_account_id,
                contribution.contribution_type,
                contribution.amount_cents,
                contribution.contribution_date,
                contribution.vested,
                account.name AS retirement_account_name
            FROM retirement_contributions AS contribution
            JOIN retirement_accounts AS account
                ON account.id = contribution.retirement_account_id
                AND account.user_id = contribution.user_id
            WHERE contribution.user_id = ?
            ORDER BY contribution.contribution_date DESC, contribution.id DESC
        """, (user_id,)).fetchall()

        return [dict(row) for row in rows]
    finally:
        connection.close()


if __name__ == "__main__":
    initialize_database()
    print(f"Database ready: {DATABASE_PATH}")
