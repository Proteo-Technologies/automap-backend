from __future__ import annotations

import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

_PASSWORD_RULES = re.compile(
    r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z0-9]).+$"
)
_PHONE_RULES = re.compile(r"^\+?[0-9]{10,15}$")


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    confirm_password: str = Field(min_length=8, max_length=128)
    first_name: str = Field(min_length=2, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    last_name: str = Field(min_length=2, max_length=100)
    second_last_name: str | None = Field(default=None, max_length=100)
    organization: str = Field(min_length=2, max_length=200)
    phone: str = Field(min_length=10, max_length=20)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        if not _PASSWORD_RULES.match(value):
            raise ValueError(
                "La contraseña debe incluir mayúscula, minúscula, número y símbolo."
            )
        return value

    @field_validator(
        "first_name", "middle_name", "last_name", "second_last_name", "organization"
    )
    @classmethod
    def validate_text_fields(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if len(normalized) < 2:
            raise ValueError("Campo inválido.")
        return normalized

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        normalized = value.strip()
        if not _PHONE_RULES.match(normalized):
            raise ValueError("Teléfono inválido. Usa solo dígitos y opcional +.")
        return normalized

    @model_validator(mode="after")
    def validate_passwords_match(self) -> "UserCreate":
        if self.password != self.confirm_password:
            raise ValueError("La confirmación de contraseña no coincide.")
        return self


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserPublic(BaseModel):
    id: UUID
    email: str
    first_name: str
    middle_name: str | None
    last_name: str
    second_last_name: str | None
    organization: str
    phone: str
    created_at: datetime

    model_config = {"from_attributes": True}


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
