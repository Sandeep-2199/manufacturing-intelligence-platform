"""Apply each pending SQL migration atomically on PostgreSQL."""

from pathlib import Path

from sqlalchemy import text

from app.database import engine


def migrate():
    directory = Path(__file__).resolve().parents[1] / "migrations"
    with engine.begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(3814207601)"))
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                name text PRIMARY KEY,
                applied_at timestamptz NOT NULL DEFAULT now()
            )
        """))
        applied = set(connection.scalars(text("SELECT name FROM schema_migrations")))
        for path in sorted(directory.glob("*.sql")):
            if path.name in applied:
                continue
            connection.exec_driver_sql(path.read_text(encoding="utf-8"))
            connection.execute(
                text("INSERT INTO schema_migrations (name) VALUES (:name)"),
                {"name": path.name},
            )
            print(f"Applied {path.name}")


if __name__ == "__main__":
    migrate()
