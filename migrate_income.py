import sqlite3

from database import DATABASE_PATH


def main():
    connection = sqlite3.connect(DATABASE_PATH)

    try:
        connection.execute("PRAGMA foreign_keys = ON")

        with connection:
            admin = connection.execute("""
                SELECT id FROM users WHERE username = ?
            """, ("admin",)).fetchone()

            if admin is None:
                raise RuntimeError("The admin account was not found.")

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
                INSERT INTO user_income (
                    user_id, name, amount_cents
                )
                SELECT ?, name, amount_cents
                FROM income
                WHERE name IN (?, ?)
                ON CONFLICT(user_id, name) DO NOTHING
            """, (
                admin["id"] if isinstance(admin, sqlite3.Row) else admin[0],
                "Your income",
                "Spouse income",
            ))

        print("Migration complete.")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
