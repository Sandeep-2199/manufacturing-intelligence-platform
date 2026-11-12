"""Create the first administrator when a deployment supplies a bootstrap password."""

import os

from pydantic import ValidationError
from sqlalchemy import select, text

from app.database import SessionLocal
from app.models.account import TeamUser
from app.schemas.account import Credentials
from app.services.security import hash_password


def main():
    password = os.getenv("MIP_BOOTSTRAP_ADMIN_PASSWORD")
    if not password:
        return

    with SessionLocal.begin() as db:
        db.execute(text("SELECT pg_advisory_xact_lock(3814207602)"))
        if db.scalar(select(TeamUser.user_id).where(
            TeamUser.role == "admin", TeamUser.is_active.is_(True)
        ).limit(1)) is not None:
            return

        try:
            credentials = Credentials(username="teamadmin", password=password)
        except ValidationError:
            raise SystemExit("MIP_BOOTSTRAP_ADMIN_PASSWORD must be 12–128 characters.") from None

        if db.scalar(select(TeamUser.user_id).where(TeamUser.username == credentials.username)) is not None:
            raise SystemExit("Bootstrap could not create teamadmin because that username already exists.")

        db.add(TeamUser(
            username=credentials.username,
            role="admin",
            password_hash=hash_password(credentials.password.get_secret_value()),
        ))
    print("Created the initial team administrator.")


if __name__ == "__main__":
    main()
