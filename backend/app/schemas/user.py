from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, field_validator
import re


class UserCreate(BaseModel):
    phone_number: str
    full_name: str

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        # Format Bénin : +229XXXXXXXX
        pattern = r"^\+229\d{8,10}$"
        if not re.match(pattern, v):
            raise ValueError("Numéro invalide. Format attendu : +229XXXXXXXX")
        return v


class UserLogin(BaseModel):
    phone_number: str
    otp_token: str


class UserOut(BaseModel):
    id: UUID
    phone_number: str
    full_name: str
    wallet_address: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
