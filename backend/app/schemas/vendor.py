from pydantic import BaseModel, ConfigDict, Field


class VendorCreate(BaseModel):
    vendor_code: str = Field(min_length=1, max_length=50)
    vendor_name: str = Field(min_length=1, max_length=150)


class VendorResponse(VendorCreate):
    vendor_id: int

    model_config = ConfigDict(from_attributes=True)
