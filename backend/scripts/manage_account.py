"""Bootstrap an administrator, reset a password, or disable an account."""

import argparse
from getpass import getpass

from pydantic import ValidationError
from sqlalchemy import delete, select, text

from app.database import SessionLocal
from app.models.account import TeamSession, TeamUser
from app.schemas.account import Credentials
from app.services.security import hash_password


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["create-admin", "reset-password", "disable"])
    parser.add_argument("username")
    args = parser.parse_args()
    username = args.username.lower()

    password_hash = None
    if args.action != "disable":
        password = getpass("Password: ")
        if password != getpass("Confirm password: "):
            parser.error("Passwords differ")
        try:
            credentials = Credentials(username=username, password=password)
        except ValidationError:
            parser.error("Use a 3–64 character username and a 8–128 character password")
        password_hash = hash_password(credentials.password.get_secret_value())

    with SessionLocal.begin() as db:
        db.execute(text("SELECT pg_advisory_xact_lock(3814207602)"))
        user = db.scalar(select(TeamUser).where(TeamUser.username == username).with_for_update())
        if args.action == "create-admin":
            if user:
                parser.error("Username already exists")
            db.add(TeamUser(username=username, role="admin", password_hash=password_hash))
        else:
            if user is None:
                parser.error("Account not found")
            if args.action == "disable":
                other_admin = db.scalar(select(TeamUser.user_id).where(
                    TeamUser.is_active.is_(True), TeamUser.role == "admin",
                    TeamUser.user_id != user.user_id,
                ).limit(1))
                if user.role == "admin" and other_admin is None:
                    parser.error("At least one active administrator is required")
                user.is_active = False
            else:
                user.password_hash = password_hash
            user.reset_token_hash = None
            user.reset_expires_at = None
            db.execute(delete(TeamSession).where(TeamSession.user_id == user.user_id))
    print(f"{args.action} completed for {username}")


if __name__ == "__main__":
    main()
