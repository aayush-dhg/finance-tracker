import os
import sqlite3
import time
from collections import defaultdict, deque
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from threading import Lock

from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import (
    LoginManager,
    UserMixin,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import check_password_hash

from database import (
    DEBT_PAYMENT_TYPES,
    LOAN_TYPES,
    add_asset,
    add_credit_card,
    add_debt_payment,
    add_expense,
    add_income_record,
    add_loan,
    add_paycheck,
    add_retirement_account,
    create_user,
    delete_asset,
    delete_credit_card,
    delete_debt_payment,
    delete_expense,
    delete_income_record,
    delete_loan,
    delete_paycheck,
    delete_retirement_account,
    get_assets,
    get_credit_cards,
    get_debt_payments,
    get_expense_categories,
    get_expenses,
    get_income,
    get_income_records,
    get_loans,
    get_paychecks,
    get_retirement_accounts,
    get_user_by_id,
    get_user_by_username,
    initialize_database,
    update_asset,
    update_credit_card,
    update_debt_payment,
    update_expense,
    update_income,
    update_income_record,
    update_loan,
    update_paycheck,
    update_retirement_account,
)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY")

if not app.config["SECRET_KEY"]:
    raise RuntimeError("Add SECRET_KEY to your .env file.")

app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config.setdefault("AUTH_RATE_LIMIT_WINDOW_SECONDS", 600)
app.config.setdefault("LOGIN_RATE_LIMIT_ATTEMPTS", 10)
app.config.setdefault("REGISTRATION_RATE_LIMIT_ATTEMPTS", 5)

csrf = CSRFProtect(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = None

# Tests set this before importing the app, then initialize their own temporary
# databases explicitly. Normal application and CLI startup still initialize the
# configured local database here.
if os.environ.get("FINANCE_SKIP_DATABASE_INIT") != "1":
    initialize_database()


class User(UserMixin):
    def __init__(self, row):
        self.id = row["id"]
        self.username = row["username"]


@login_manager.user_loader
def load_user(user_id):
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return None

    row = get_user_by_id(user_id)
    return User(row) if row else None


class AuthenticationRateLimiter:
    """Track failed authentication attempts for this local app process."""

    def __init__(self):
        self._attempts = defaultdict(deque)
        self._lock = Lock()

    def retry_after(self, action, client_address, limit, window_seconds):
        now = time.monotonic()
        key = (action, client_address)

        with self._lock:
            attempts = self._attempts[key]

            while attempts and attempts[0] <= now - window_seconds:
                attempts.popleft()

            if len(attempts) < limit:
                return 0

            return max(1, int(window_seconds - (now - attempts[0])) + 1)

    def record_failure(self, action, client_address):
        with self._lock:
            self._attempts[(action, client_address)].append(time.monotonic())

    def clear(self, action=None, client_address=None):
        with self._lock:
            if action is None and client_address is None:
                self._attempts.clear()
            else:
                self._attempts.pop((action, client_address), None)


auth_rate_limiter = AuthenticationRateLimiter()


def authentication_retry_after(action):
    limit_setting = (
        "LOGIN_RATE_LIMIT_ATTEMPTS"
        if action == "login"
        else "REGISTRATION_RATE_LIMIT_ATTEMPTS"
    )
    return auth_rate_limiter.retry_after(
        action,
        request.remote_addr or "unknown",
        app.config[limit_setting],
        app.config["AUTH_RATE_LIMIT_WINDOW_SECONDS"],
    )


def record_authentication_failure(action):
    auth_rate_limiter.record_failure(
        action,
        request.remote_addr or "unknown",
    )


def clear_authentication_failures(action):
    auth_rate_limiter.clear(action, request.remote_addr or "unknown")


@app.template_filter("money")
def format_money(cents):
    sign = "-" if cents < 0 else ""
    amount = Decimal(abs(cents)) / 100
    return f"{sign}${amount:,.2f}"


def dollars_to_cents(raw_value):
    try:
        amount = Decimal(raw_value)
    except (InvalidOperation, TypeError):
        raise ValueError("Enter a valid amount.")

    if not amount.is_finite() or amount < 0 or amount > 1_000_000:
        raise ValueError("Enter an amount between $0 and $1,000,000.")

    cents = amount * 100

    if cents != cents.to_integral_value():
        raise ValueError("Use no more than two decimal places.")

    return int(cents)


def positive_dollars_to_cents(raw_value):
    cents = dollars_to_cents(raw_value)

    if cents <= 0:
        raise ValueError("Enter an amount greater than $0.")

    return cents


def percent_to_basis_points(raw_value):
    try:
        percent = Decimal(raw_value)
    except (InvalidOperation, TypeError):
        raise ValueError("Enter a valid APR.")

    if not percent.is_finite() or not 0 <= percent <= 100:
        raise ValueError("APR must be between 0% and 100%.")

    basis_points = percent * 100

    if basis_points != basis_points.to_integral_value():
        raise ValueError("Use no more than two decimal places for APR.")

    return int(basis_points)


def due_day_from_form(form):
    try:
        return int(form.get("due_day", ""))
    except (TypeError, ValueError):
        raise ValueError("Due day must be a whole number between 1 and 31.")


def card_values_from_form(form):
    return {
        "nickname": form.get("nickname", ""),
        "balance_cents": dollars_to_cents(form.get("balance", "")),
        "apr_basis_points": percent_to_basis_points(form.get("apr", "")),
        "minimum_payment_cents": dollars_to_cents(
            form.get("minimum_payment", "")
        ),
        "due_day": due_day_from_form(form),
    }


def loan_values_from_form(form):
    return {
        "name": form.get("name", ""),
        "loan_type": form.get("loan_type", ""),
        "balance_cents": dollars_to_cents(form.get("balance", "")),
        "apr_basis_points": percent_to_basis_points(form.get("apr", "")),
        "monthly_payment_cents": dollars_to_cents(
            form.get("monthly_payment", "")
        ),
        "due_day": due_day_from_form(form),
    }


def expense_values_from_form(form):
    return {
        "name": form.get("name", ""),
        "category": form.get("category", ""),
        "amount_cents": positive_dollars_to_cents(
            form.get("amount", "")
        ),
        "recorded_on": form.get("recorded_on", "").strip() or None,
    }


def asset_values_from_form(form):
    return {
        "name": form.get("name", ""),
        "category": form.get("category", ""),
        "balance_cents": dollars_to_cents(form.get("balance", "")),
        "as_of_date": form.get("as_of_date", ""),
    }


def income_record_values_from_form(form):
    return {
        "name": form.get("name", ""),
        "amount_cents": positive_dollars_to_cents(
            form.get("amount", "")
        ),
        "recorded_on": form.get("recorded_on", ""),
    }


def debt_payment_values_from_form(form):
    return {
        "name": form.get("name", ""),
        "debt_type": form.get("debt_type", ""),
        "amount_cents": positive_dollars_to_cents(
            form.get("amount", "")
        ),
        "paid_on": form.get("paid_on", ""),
    }


def optional_dollars_to_cents(form, field_name):
    return dollars_to_cents(form.get(field_name, "0") or "0")


def retirement_account_values_from_form(form):
    return {
        "name": form.get("name", ""),
        "vested_balance_cents": dollars_to_cents(
            form.get("vested_balance", "")
        ),
        "unvested_balance_cents": optional_dollars_to_cents(
            form,
            "unvested_balance",
        ),
        "balance_date": form.get("balance_date", ""),
    }


def paycheck_values_from_form(form):
    raw_account_id = form.get("retirement_account_id", "").strip()

    if raw_account_id:
        try:
            retirement_account_id = int(raw_account_id)
        except ValueError:
            raise ValueError("Choose a valid 401(k) account.")
    else:
        retirement_account_id = None

    deduction_names = form.getlist("deduction_name")
    deduction_amounts = form.getlist("deduction_amount")

    if len(deduction_names) != len(deduction_amounts):
        raise ValueError("Each custom deduction needs a name and amount.")

    deductions = []

    for name, raw_amount in zip(deduction_names, deduction_amounts):
        name = name.strip()
        raw_amount = raw_amount.strip()

        if not name and not raw_amount:
            continue

        if not name or not raw_amount:
            raise ValueError("Each custom deduction needs a name and amount.")

        deductions.append({
            "name": name,
            "amount_cents": positive_dollars_to_cents(raw_amount),
        })

    return {
        "pay_date": form.get("pay_date", ""),
        "employee_name": form.get("employee_name", ""),
        "employer": form.get("employer", ""),
        "gross_pay_cents": positive_dollars_to_cents(
            form.get("gross_pay", "")
        ),
        "federal_tax_cents": optional_dollars_to_cents(
            form, "federal_tax"
        ),
        "state_tax_cents": optional_dollars_to_cents(form, "state_tax"),
        "social_security_tax_cents": optional_dollars_to_cents(
            form, "social_security_tax"
        ),
        "medicare_tax_cents": optional_dollars_to_cents(
            form, "medicare_tax"
        ),
        "other_tax_cents": optional_dollars_to_cents(form, "other_tax"),
        "health_insurance_cents": optional_dollars_to_cents(
            form, "health_insurance"
        ),
        "employee_401k_cents": optional_dollars_to_cents(
            form, "employee_401k"
        ),
        "actual_net_cents": dollars_to_cents(
            form.get("actual_net", "")
        ),
        "retirement_account_id": retirement_account_id,
        "employer_match_cents": optional_dollars_to_cents(
            form, "employer_match"
        ),
        "employer_match_vested": (
            form.get("employer_match_vested") == "on"
        ),
        "deductions": deductions,
    }


def validated_month(raw_month):
    if raw_month:
        try:
            return date.fromisoformat(f"{raw_month}-01").strftime("%Y-%m")
        except ValueError:
            pass

    return date.today().strftime("%Y-%m")


def validated_year(raw_year):
    try:
        year = int(raw_year)
    except (TypeError, ValueError):
        return date.today().year

    if not 2000 <= year <= 2100:
        return date.today().year

    return year


def percentage(value, maximum):
    if maximum <= 0:
        return 0

    return round(value / maximum * 100, 2)


def breakdown(items, key, label_key):
    grouped = {}

    for item in items:
        label = item[label_key]
        grouped[label] = grouped.get(label, 0) + item[key]

    total = sum(grouped.values())

    return [
        {
            "label": label,
            "amount_cents": amount,
            "percent": percentage(amount, total),
        }
        for label, amount in sorted(
            grouped.items(), key=lambda pair: (-pair[1], pair[0].lower())
        )
    ]


def manage_redirect(error=None, anchor=None):
    target = url_for("manage", error=error) if error else url_for("manage")

    if anchor:
        target = f"{target}#{anchor}"

    return redirect(target)


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("home"))

    error = None
    username = ""

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        retry_after = authentication_retry_after("login")

        if retry_after:
            response = app.make_response(render_template(
                "login.html",
                error=(
                    "Too many unsuccessful login attempts. "
                    f"Try again in {retry_after} seconds."
                ),
                username=username,
            ))
            response.status_code = 429
            response.headers["Retry-After"] = str(retry_after)
            return response

        row = get_user_by_username(username)

        if (
            12 <= len(password) <= 128
            and row is not None
            and check_password_hash(row["password_hash"], password)
        ):
            session.clear()
            login_user(User(row))
            clear_authentication_failures("login")
            return redirect(url_for("home"))

        record_authentication_failure("login")
        error = "Incorrect username or password."

    return render_template("login.html", error=error, username=username)


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("home"))

    error = None
    username = ""

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirmation = request.form.get("confirm_password", "")

        retry_after = authentication_retry_after("registration")

        if retry_after:
            response = app.make_response(render_template(
                "register.html",
                error=(
                    "Too many unsuccessful registration attempts. "
                    f"Try again in {retry_after} seconds."
                ),
                username=username,
            ))
            response.status_code = 429
            response.headers["Retry-After"] = str(retry_after)
            return response

        if password != confirmation:
            record_authentication_failure("registration")
            error = "Passwords do not match."
        else:
            try:
                create_user(username, password)
            except ValueError as validation_error:
                record_authentication_failure("registration")
                error = str(validation_error)
            except sqlite3.IntegrityError:
                record_authentication_failure("registration")
                error = "That username already exists."
            else:
                clear_authentication_failures("registration")
                flash("Account created. You can now log in.", "success")
                return redirect(url_for("login"))

    return render_template(
        "register.html",
        error=error,
        username=username,
    )


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def home():
    selected_month = validated_month(request.args.get("month"))
    selected_year = validated_year(request.args.get("year"))
    income_plan = get_income(current_user.id)
    expenses = get_expenses(current_user.id)
    income_records = get_income_records(current_user.id)
    paychecks = get_paychecks(current_user.id)
    debt_payments = get_debt_payments(current_user.id)
    assets = get_assets(current_user.id)
    retirement_accounts = get_retirement_accounts(current_user.id)
    credit_cards = get_credit_cards(current_user.id)
    loans = get_loans(current_user.id)

    retirement_assets_cents = sum(
        account["vested_balance_cents"]
        for account in retirement_accounts
    )
    total_assets_cents = (
        sum(asset["balance_cents"] for asset in assets)
        + retirement_assets_cents
    )
    card_debt_cents = sum(card["balance_cents"] for card in credit_cards)
    loan_debt_cents = sum(loan["balance_cents"] for loan in loans)
    total_debt_cents = card_debt_cents + loan_debt_cents
    net_worth_cents = total_assets_cents - total_debt_cents
    planned_income_cents = sum(income_plan.values())
    planned_expenses_cents = sum(
        expense["amount_cents"]
        for expense in expenses
        if expense["recorded_on"] is None
    )
    planned_debt_payments_cents = sum(
        card["minimum_payment_cents"] for card in credit_cards
    ) + sum(loan["monthly_payment_cents"] for loan in loans)

    month_income_records = [
        record
        for record in income_records
        if record["recorded_on"].startswith(selected_month)
    ]
    month_paychecks = [
        paycheck
        for paycheck in paychecks
        if paycheck["pay_date"].startswith(selected_month)
    ]
    monthly_paycheck_income_cents = sum(
        paycheck["actual_net_cents"] for paycheck in month_paychecks
    )
    month_expense_records = [
        expense
        for expense in expenses
        if expense["recorded_on"]
        and expense["recorded_on"].startswith(selected_month)
    ]
    monthly_has_history = bool(
        month_income_records or month_paychecks or month_expense_records
    )

    if monthly_has_history:
        monthly_income_cents = sum(
            record["amount_cents"] for record in month_income_records
        ) + monthly_paycheck_income_cents
        monthly_expenses_cents = sum(
            expense["amount_cents"] for expense in month_expense_records
        )
        monthly_label = "Recorded entries + planned debt payments"
    else:
        monthly_income_cents = planned_income_cents
        monthly_expenses_cents = planned_expenses_cents
        monthly_label = "Planned monthly estimate"

    monthly_net_cents = (
        monthly_income_cents
        - monthly_expenses_cents
        - planned_debt_payments_cents
    )
    monthly_maximum = max(
        monthly_income_cents,
        monthly_expenses_cents,
        planned_debt_payments_cents,
        1,
    )
    monthly_comparison = (
        {
            "label": "Income",
            "amount_cents": monthly_income_cents,
            "percent": percentage(monthly_income_cents, monthly_maximum),
        },
        {
            "label": "Expenses",
            "amount_cents": monthly_expenses_cents,
            "percent": percentage(monthly_expenses_cents, monthly_maximum),
        },
        {
            "label": "Planned debt",
            "amount_cents": planned_debt_payments_cents,
            "percent": percentage(
                planned_debt_payments_cents,
                monthly_maximum,
            ),
        },
    )

    yearly_months = []
    yearly_income_cents = 0
    yearly_expenses_cents = 0
    yearly_debt_payments_cents = 0

    for month_number in range(1, 13):
        period = f"{selected_year}-{month_number:02d}"
        income_cents = sum(
            record["amount_cents"]
            for record in income_records
            if record["recorded_on"].startswith(period)
        ) + sum(
            paycheck["actual_net_cents"]
            for paycheck in paychecks
            if paycheck["pay_date"].startswith(period)
        )
        expense_cents = sum(
            expense["amount_cents"]
            for expense in expenses
            if expense["recorded_on"]
            and expense["recorded_on"].startswith(period)
        )
        payment_cents = sum(
            payment["amount_cents"]
            for payment in debt_payments
            if payment["paid_on"].startswith(period)
        )
        net_cents = income_cents - expense_cents - payment_cents
        yearly_months.append(
            {
                "label": date(selected_year, month_number, 1).strftime("%b"),
                "income_cents": income_cents,
                "expense_cents": expense_cents,
                "payment_cents": payment_cents,
                "net_cents": net_cents,
            }
        )
        yearly_income_cents += income_cents
        yearly_expenses_cents += expense_cents
        yearly_debt_payments_cents += payment_cents

    year_prefix = str(selected_year)
    yearly_has_history = any(
        record["recorded_on"].startswith(year_prefix)
        for record in income_records
    ) or any(
        paycheck["pay_date"].startswith(year_prefix)
        for paycheck in paychecks
    ) or any(
        expense["recorded_on"]
        and expense["recorded_on"].startswith(year_prefix)
        for expense in expenses
    ) or any(
        payment["paid_on"].startswith(year_prefix)
        for payment in debt_payments
    )
    yearly_maximum = max(
        [
            max(
                month["income_cents"],
                month["expense_cents"],
                month["payment_cents"],
            )
            for month in yearly_months
        ]
        + [1]
    )

    for month in yearly_months:
        month["income_percent"] = percentage(
            month["income_cents"], yearly_maximum
        )
        month["expense_percent"] = percentage(
            month["expense_cents"], yearly_maximum
        )
        month["payment_percent"] = percentage(
            month["payment_cents"], yearly_maximum
        )

    net_worth_maximum = max(total_assets_cents, total_debt_cents, 1)

    return render_template(
        "home.html",
        owner=current_user.username,
        selected_month=selected_month,
        selected_month_label=date.fromisoformat(
            f"{selected_month}-01"
        ).strftime("%B %Y"),
        selected_year=selected_year,
        current_year=date.today().year,
        total_assets_cents=total_assets_cents,
        total_debt_cents=total_debt_cents,
        net_worth_cents=net_worth_cents,
        assets_breakdown=breakdown(
            assets
            + [
                {
                    "category": "401(k) retirement",
                    "balance_cents": account["vested_balance_cents"],
                }
                for account in retirement_accounts
            ],
            "balance_cents",
            "category",
        ),
        debt_breakdown=(
            {
                "label": "Credit cards",
                "amount_cents": card_debt_cents,
                "percent": percentage(card_debt_cents, total_debt_cents),
            },
            {
                "label": "Loans",
                "amount_cents": loan_debt_cents,
                "percent": percentage(loan_debt_cents, total_debt_cents),
            },
        ),
        assets_percent=percentage(total_assets_cents, net_worth_maximum),
        debt_percent=percentage(total_debt_cents, net_worth_maximum),
        monthly_net_cents=monthly_net_cents,
        monthly_label=monthly_label,
        monthly_has_history=monthly_has_history,
        monthly_paycheck_income_cents=monthly_paycheck_income_cents,
        monthly_comparison=monthly_comparison,
        yearly_net_cents=(
            yearly_income_cents
            - yearly_expenses_cents
            - yearly_debt_payments_cents
        ),
        yearly_has_history=yearly_has_history,
        yearly_months=yearly_months,
        yearly_income_cents=yearly_income_cents,
        yearly_expenses_cents=yearly_expenses_cents,
        yearly_debt_payments_cents=yearly_debt_payments_cents,
    )


@app.route("/add")
@login_required
def manage():
    income = get_income(current_user.id)

    return render_template(
        "manage.html",
        owner=current_user.username,
        today=date.today().isoformat(),
        your_income_cents=income["Your income"],
        spouse_income_cents=income["Spouse income"],
        income_records=get_income_records(current_user.id),
        paychecks=get_paychecks(current_user.id),
        expenses=get_expenses(current_user.id),
        expense_categories=get_expense_categories(current_user.id),
        assets=get_assets(current_user.id),
        retirement_accounts=get_retirement_accounts(current_user.id),
        credit_cards=get_credit_cards(current_user.id),
        loans=get_loans(current_user.id),
        debt_payments=get_debt_payments(current_user.id),
        loan_types=LOAN_TYPES,
        debt_payment_types=DEBT_PAYMENT_TYPES,
        error=request.args.get("error"),
    )


@app.route("/income/plan", methods=["POST"])
@login_required
def save_income_plan():
    try:
        your_cents = dollars_to_cents(request.form.get("your_income", ""))
        spouse_cents = dollars_to_cents(
            request.form.get("spouse_income", "")
        )
        update_income(current_user.id, your_cents, spouse_cents)
    except ValueError as exc:
        return manage_redirect(str(exc), "income")

    return manage_redirect(anchor="income")


@app.route("/income-records/add", methods=["POST"])
@login_required
def create_income_record():
    try:
        add_income_record(
            current_user.id,
            **income_record_values_from_form(request.form),
        )
    except ValueError as exc:
        return manage_redirect(str(exc), "income")

    return manage_redirect(anchor="income")


@app.route("/income-records/<int:income_id>/edit", methods=["POST"])
@login_required
def edit_income_record(income_id):
    try:
        updated = update_income_record(
            current_user.id,
            income_id,
            **income_record_values_from_form(request.form),
        )
    except ValueError as exc:
        return manage_redirect(str(exc), "income")

    if not updated:
        abort(404)

    return manage_redirect(anchor="income")


@app.route("/income-records/<int:income_id>/delete", methods=["POST"])
@login_required
def remove_income_record(income_id):
    if not delete_income_record(current_user.id, income_id):
        abort(404)

    return manage_redirect(anchor="income")


@app.route("/paychecks/add", methods=["POST"])
@login_required
def create_paycheck():
    try:
        add_paycheck(
            current_user.id,
            **paycheck_values_from_form(request.form),
        )
    except ValueError as exc:
        return manage_redirect(str(exc), "paychecks")

    return manage_redirect(anchor="paychecks")


@app.route("/paychecks/<int:paycheck_id>/edit", methods=["POST"])
@login_required
def edit_paycheck(paycheck_id):
    try:
        updated = update_paycheck(
            current_user.id,
            paycheck_id,
            **paycheck_values_from_form(request.form),
        )
    except ValueError as exc:
        return manage_redirect(str(exc), "paychecks")

    if not updated:
        abort(404)

    return manage_redirect(anchor="paychecks")


@app.route("/paychecks/<int:paycheck_id>/delete", methods=["POST"])
@login_required
def remove_paycheck(paycheck_id):
    if not delete_paycheck(current_user.id, paycheck_id):
        abort(404)

    return manage_redirect(anchor="paychecks")


@app.route("/expenses/add", methods=["POST"])
@login_required
def create_expense():
    try:
        add_expense(
            current_user.id,
            **expense_values_from_form(request.form),
        )
    except ValueError as exc:
        return manage_redirect(str(exc), "expenses")

    return manage_redirect(anchor="expenses")


@app.route("/expenses/<int:expense_id>/edit", methods=["POST"])
@login_required
def edit_expense(expense_id):
    try:
        updated = update_expense(
            current_user.id,
            expense_id,
            **expense_values_from_form(request.form),
        )
    except ValueError as exc:
        return manage_redirect(str(exc), "expenses")

    if not updated:
        abort(404)

    return manage_redirect(anchor="expenses")


@app.route("/expenses/<int:expense_id>/delete", methods=["POST"])
@login_required
def remove_expense(expense_id):
    if not delete_expense(current_user.id, expense_id):
        abort(404)

    return manage_redirect(anchor="expenses")


@app.route("/assets/add", methods=["POST"])
@login_required
def create_asset():
    try:
        add_asset(current_user.id, **asset_values_from_form(request.form))
    except ValueError as exc:
        return manage_redirect(str(exc), "assets")

    return manage_redirect(anchor="assets")


@app.route("/assets/<int:asset_id>/edit", methods=["POST"])
@login_required
def edit_asset(asset_id):
    try:
        updated = update_asset(
            current_user.id,
            asset_id,
            **asset_values_from_form(request.form),
        )
    except ValueError as exc:
        return manage_redirect(str(exc), "assets")

    if not updated:
        abort(404)

    return manage_redirect(anchor="assets")


@app.route("/assets/<int:asset_id>/delete", methods=["POST"])
@login_required
def remove_asset(asset_id):
    if not delete_asset(current_user.id, asset_id):
        abort(404)

    return manage_redirect(anchor="assets")


@app.route("/retirement-accounts/add", methods=["POST"])
@login_required
def create_retirement_account():
    try:
        add_retirement_account(
            current_user.id,
            **retirement_account_values_from_form(request.form),
        )
    except ValueError as exc:
        return manage_redirect(str(exc), "assets")

    return manage_redirect(anchor="assets")


@app.route(
    "/retirement-accounts/<int:account_id>/edit",
    methods=["POST"],
)
@login_required
def edit_retirement_account(account_id):
    try:
        updated = update_retirement_account(
            current_user.id,
            account_id,
            **retirement_account_values_from_form(request.form),
        )
    except ValueError as exc:
        return manage_redirect(str(exc), "assets")

    if not updated:
        abort(404)

    return manage_redirect(anchor="assets")


@app.route(
    "/retirement-accounts/<int:account_id>/delete",
    methods=["POST"],
)
@login_required
def remove_retirement_account(account_id):
    try:
        deleted = delete_retirement_account(current_user.id, account_id)
    except ValueError as exc:
        return manage_redirect(str(exc), "assets")

    if not deleted:
        abort(404)

    return manage_redirect(anchor="assets")


@app.route("/cards/add", methods=["POST"])
@login_required
def create_credit_card():
    try:
        add_credit_card(
            current_user.id,
            **card_values_from_form(request.form),
        )
    except ValueError as exc:
        return manage_redirect(str(exc), "debts")

    return manage_redirect(anchor="debts")


@app.route("/cards/<int:card_id>/edit", methods=["POST"])
@login_required
def edit_credit_card(card_id):
    try:
        updated = update_credit_card(
            current_user.id,
            card_id,
            **card_values_from_form(request.form),
        )
    except ValueError as exc:
        return manage_redirect(str(exc), "debts")

    if not updated:
        abort(404)

    return manage_redirect(anchor="debts")


@app.route("/cards/<int:card_id>/delete", methods=["POST"])
@login_required
def remove_credit_card(card_id):
    if not delete_credit_card(current_user.id, card_id):
        abort(404)

    return manage_redirect(anchor="debts")


@app.route("/loans/add", methods=["POST"])
@login_required
def create_loan():
    try:
        add_loan(current_user.id, **loan_values_from_form(request.form))
    except ValueError as exc:
        return manage_redirect(str(exc), "debts")

    return manage_redirect(anchor="debts")


@app.route("/loans/<int:loan_id>/edit", methods=["POST"])
@login_required
def edit_loan(loan_id):
    try:
        updated = update_loan(
            current_user.id,
            loan_id,
            **loan_values_from_form(request.form),
        )
    except ValueError as exc:
        return manage_redirect(str(exc), "debts")

    if not updated:
        abort(404)

    return manage_redirect(anchor="debts")


@app.route("/loans/<int:loan_id>/delete", methods=["POST"])
@login_required
def remove_loan(loan_id):
    if not delete_loan(current_user.id, loan_id):
        abort(404)

    return manage_redirect(anchor="debts")


@app.route("/debt-payments/add", methods=["POST"])
@login_required
def create_debt_payment():
    try:
        add_debt_payment(
            current_user.id,
            **debt_payment_values_from_form(request.form),
        )
    except ValueError as exc:
        return manage_redirect(str(exc), "debt-history")

    return manage_redirect(anchor="debt-history")


@app.route(
    "/debt-payments/<int:payment_id>/edit",
    methods=["POST"],
)
@login_required
def edit_debt_payment(payment_id):
    try:
        updated = update_debt_payment(
            current_user.id,
            payment_id,
            **debt_payment_values_from_form(request.form),
        )
    except ValueError as exc:
        return manage_redirect(str(exc), "debt-history")

    if not updated:
        abort(404)

    return manage_redirect(anchor="debt-history")


@app.route(
    "/debt-payments/<int:payment_id>/delete",
    methods=["POST"],
)
@login_required
def remove_debt_payment(payment_id):
    if not delete_debt_payment(current_user.id, payment_id):
        abort(404)

    return manage_redirect(anchor="debt-history")
