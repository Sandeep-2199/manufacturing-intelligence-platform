from sqlalchemy import Column, Integer, String

from app.database import Base


class Vendor(Base):
    __tablename__ = "vendors"

    vendor_id = Column(Integer, primary_key=True)
    vendor_code = Column(String(50), unique=True, nullable=False)
    vendor_name = Column(String(150), nullable=False)
