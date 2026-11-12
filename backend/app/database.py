
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker

# Load database configuration from .env
load_dotenv()

DATABASE_URL = make_url(os.environ["DATABASE_URL"])
if DATABASE_URL.drivername in {"postgres", "postgresql"}:
    DATABASE_URL = DATABASE_URL.set(drivername="postgresql+psycopg")

# Create connection to PostgreSQL
engine = create_engine(DATABASE_URL, pool_pre_ping=True, hide_parameters=True)

# Create database sessions
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# Base class for database models
Base = declarative_base()


# Provide a database session to API endpoints
def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()
