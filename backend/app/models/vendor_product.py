from sqlalchemy import CheckConstraint, Column, ForeignKey, Integer, Numeric

from app.database import Base


class VendorProduct(Base):
    __tablename__ = "vendor_products"
    __table_args__ = (
        CheckConstraint("unit_price >= 0", name="ck_vendor_products_price"),
        CheckConstraint("lead_time_days >= 0", name="ck_vendor_products_lead_time"),
    )

    vendor_id = Column(Integer, ForeignKey("vendors.vendor_id"), primary_key=True)
    product_id = Column(
        Integer, ForeignKey("products.product_id"), primary_key=True, index=True
    )
    unit_price = Column(Numeric(12, 2), nullable=True)
    lead_time_days = Column(Integer, nullable=True)
