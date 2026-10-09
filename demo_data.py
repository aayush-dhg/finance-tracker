"""Create an isolated SQLite database containing fictional portfolio data."""

import argparse
from datetime import date
from pathlib import Path

import database


PROJECT_DIRECTORY = Path(__file__).resolve().parent
PRODUCTION_DATABASE_PATH = PROJECT_DIRECTORY / "finance.db"
DEMO_DATABASE_PATH = PROJECT_DIRECTORY / "demo_finance.db"
DEMO_USERNAME = "demo_user"
DEMO_PASSWORD = "demo-password-123"


def _demo_date(day):
    today = date.today()
    return date(today.year, today.month, day).isoformat()


def create_demo_database(database_path=DEMO_DATABASE_PATH, replace=False):
    database_path = Path(database_path).resolve()

    if database_path == PRODUCTION_DATABASE_PATH.resolve():
        raise ValueError("The demo script cannot write to finance.db.")

    if database_path.exists():
        if not replace:
            raise FileExistsError(
                f"{database_path.name} already exists. Use --replace to "
                "rebuild only the demo database."
            )
        database_path.unlink()

    original_database_path = database.DATABASE_PATH
    database.DATABASE_PATH = database_path

    try:
        database.initialize_database()
        user_id = database.create_user(DEMO_USERNAME, DEMO_PASSWORD)
        other_user_id = database.create_user(
            "demo_neighbor",
            "neighbor-password-123",
        )

        database.update_income(user_id, 550000, 0)
        database.add_asset(
            user_id,
            "Emergency savings",
            "Cash",
            980000,
            _demo_date(1),
        )
        database.add_asset(
            user_id,
            "Index fund",
            "Investments",
            1675000,
            _demo_date(1),
        )
        retirement_account_id = database.add_retirement_account(
            user_id,
            "Example Company 401(k)",
            2440000,
            185000,
            _demo_date(1),
        )
        database.add_credit_card(
            user_id,
            "Everyday Rewards",
            185000,
            2099,
            6500,
            18,
        )
        database.add_loan(
            user_id,
            "Used car loan",
            "auto",
            1240000,
            625,
            38500,
            12,
        )

        database.add_expense(user_id, "Rent", 165000, "Housing")
        database.add_expense(user_id, "Utilities", 18500, "Household")
        database.add_expense(
            user_id,
            "Groceries",
            46250,
            "Food",
            _demo_date(8),
        )
        database.add_expense(
            user_id,
            "Train pass",
            9500,
            "Transportation",
            _demo_date(10),
        )
        database.add_income_record(
            user_id,
            "Freelance design",
            48000,
            _demo_date(20),
        )
        database.add_debt_payment(
            user_id,
            "Rewards card payment",
            "credit_card",
            12500,
            _demo_date(24),
        )

        paycheck = {
            "employee_name": "Jordan Lee",
            "employer": "Example Company",
            "gross_pay_cents": 420000,
            "federal_tax_cents": 52000,
            "state_tax_cents": 17000,
            "social_security_tax_cents": 26040,
            "medicare_tax_cents": 6090,
            "other_tax_cents": 0,
            "health_insurance_cents": 14000,
            "employee_401k_cents": 25200,
            "actual_net_cents": 275170,
            "retirement_account_id": retirement_account_id,
            "employer_match_cents": 12600,
            "employer_match_vested": True,
            "deductions": [
                {"name": "Transit benefit", "amount_cents": 4500},
            ],
        }
        database.add_paycheck(
            user_id,
            pay_date=_demo_date(5),
            **paycheck,
        )
        database.add_paycheck(
            user_id,
            pay_date=_demo_date(19),
            **paycheck,
        )

        # A second fictional owner makes isolation easy to demonstrate without
        # exposing or copying any local user data.
        database.add_asset(
            other_user_id,
            "Neighbor-only savings",
            "Cash",
            321000,
            _demo_date(1),
        )
    finally:
        database.DATABASE_PATH = original_database_path

    return database_path


def main():
    parser = argparse.ArgumentParser(
        description="Create an isolated database with fictional demo data."
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="replace demo_finance.db if it already exists",
    )
    arguments = parser.parse_args()

    try:
        path = create_demo_database(replace=arguments.replace)
    except (FileExistsError, ValueError) as error:
        parser.error(str(error))

    print(f"Created fictional demo database: {path.name}")
    print(f"Demo username: {DEMO_USERNAME}")
    print(f"Demo password: {DEMO_PASSWORD}")
    print("Your normal finance.db was not opened or changed.")


if __name__ == "__main__":
    main()
