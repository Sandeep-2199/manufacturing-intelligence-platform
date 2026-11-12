from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String

from app.database import Base


class CustomerCompany(Base):
    __tablename__ = "customer_companies"

    company_id = Column(Integer, primary_key=True)
    name = Column(String(150), nullable=False, unique=True)


class CustomerInvitation(Base):
    __tablename__ = "customer_invitations"

    token_hash = Column(String(64), primary_key=True)
    company_id = Column(Integer, ForeignKey("customer_companies.company_id"), nullable=False)
    username = Column(String(64), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    consumed_at = Column(DateTime(timezone=True))


class CustomerJob(Base):
    __tablename__ = "customer_jobs"

    job_id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("customer_companies.company_id"), nullable=False)
    reference = Column(String(64), nullable=False)
    title = Column(String(150), nullable=False)
    status = Column(String(20), nullable=False)
    expected_delivery = Column(Date)
