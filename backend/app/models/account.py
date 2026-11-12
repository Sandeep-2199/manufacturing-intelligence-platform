from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String

from app.database import Base
from app.models.customer import CustomerCompany


class TeamUser(Base):
    __tablename__ = "team_users"

    user_id = Column(Integer, primary_key=True)
    username = Column(String(64), nullable=False, unique=True)
    password_hash = Column(String(160), nullable=False)
    role = Column(String(10), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    company_id = Column(Integer, ForeignKey(CustomerCompany.company_id))


class TeamSession(Base):
    __tablename__ = "team_sessions"

    token_hash = Column(String(64), primary_key=True)
    user_id = Column(Integer, ForeignKey("team_users.user_id", ondelete="CASCADE"), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)


class LoginAttempt(Base):
    __tablename__ = "login_attempts"

    client_ip = Column(String(64), primary_key=True)
    attempts = Column(Integer, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
