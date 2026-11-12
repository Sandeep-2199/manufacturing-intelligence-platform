
from pydantic import BaseModel, Field, ConfigDict


# Data received when creating a product
class ProductCreate(BaseModel):

    part_number: str = Field(min_length=1, max_length=50)

    product_name: str = Field(min_length=1, max_length=150)

    description: str | None = None

    material: str | None = Field(default=None, max_length=100)

    unit: str = Field(default="piece", max_length=30)


# Data returned to the client
class ProductResponse(BaseModel):

    product_id: int

    part_number: str

    product_name: str

    description: str | None

    material: str | None

    unit: str

    is_active: bool

    model_config = ConfigDict(from_attributes=True)

class ProductUpdate(ProductCreate):
    pass
