from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, StringConstraints

from app.schemas.account import Username


JobStatus = Literal["received", "in_progress", "ready", "delivered", "cancelled"]


class CompanyCreate(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]


class CompanyResponse(CompanyCreate):
    company_id: int

    model_config = ConfigDict(from_attributes=True)


class InvitationCreate(Username):
    pass


class InvitationResponse(BaseModel):
    token: str
    expires_at: datetime


class InvitationAccept(BaseModel):
    token: SecretStr = Field(min_length=43, max_length=43)
    password: SecretStr = Field(min_length=8, max_length=128)


class JobWrite(BaseModel):
    reference: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
    status: JobStatus = "received"
    expected_delivery: date | None = None


class JobResponse(JobWrite):
    job_id: int

    model_config = ConfigDict(from_attributes=True)
