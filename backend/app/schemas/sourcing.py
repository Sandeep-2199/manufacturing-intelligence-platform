from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.product import ProductResponse
from app.schemas.vendor import VendorResponse


class SupplierTerms(BaseModel):
    unit_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    lead_time_days: int | None = Field(default=None, ge=0, le=2_147_483_647)


class VendorProductResponse(SupplierTerms):
    vendor_id: int
    product_id: int

    model_config = ConfigDict(from_attributes=True)


class SupplierOffer(SupplierTerms):
    vendor: VendorResponse


class ProductComparison(BaseModel):
    product: ProductResponse
    currency: str = "USD"
    suppliers: list[SupplierOffer]
