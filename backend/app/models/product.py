
from sqlalchemy import Column
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import Text
from sqlalchemy import Boolean
from sqlalchemy import DateTime
from sqlalchemy import func

from app.database import Base


class Product(Base):

    __tablename__ = "products"

    product_id = Column(Integer, primary_key=True, index=True)

    part_number = Column(String(50), unique=True, nullable=False)

    product_name = Column(String(150), nullable=False)

    description = Column(Text, nullable=True)

    material = Column(String(100), nullable=True)

    unit = Column(String(30), default="piece")

    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
