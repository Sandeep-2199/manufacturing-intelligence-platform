from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


Role = Literal["admin", "editor", "viewer"]


class Username(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")

    @field_validator("username")
    @classmethod
    def normalize_username(cls, username: str) -> str:
        return username.lower()


class Credentials(Username):
    password: SecretStr = Field(min_length=8, max_length=128)


class AccountCreate(Credentials):
    role: Role = "viewer"


class PasswordReset(BaseModel):
    token: SecretStr = Field(min_length=43, max_length=43)
    password: SecretStr = Field(min_length=8, max_length=128)


class AccountResponse(BaseModel):
    user_id: int
    username: str
    role: Role | Literal["customer"]
    is_active: bool

    model_config = ConfigDict(from_attributes=True)
