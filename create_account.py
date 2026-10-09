import sqlite3
from getpass import getpass

from database import create_user, initialize_database


def main():
    initialize_database()

    username = input("Choose a username: ")
    password = getpass("Choose a password (12–128 characters): ")
    confirmation = getpass("Confirm password: ")

    if password != confirmation:
        print("Passwords do not match. Account was not created.")
        return

    try:
        user_id = create_user(username, password)
    except ValueError as error:
        print(f"Account was not created: {error}")
    except sqlite3.IntegrityError:
        print("That username already exists.")
    else:
        print(f"Account created successfully. User ID: {user_id}")


if __name__ == "__main__":
    main()