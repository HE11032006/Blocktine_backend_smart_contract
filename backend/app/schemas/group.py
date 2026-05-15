from datetime import datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel, field_validator


class GroupCreate(BaseModel):
    name: str
    amount_fcfa: int
    frequency_days: int
    max_members: int = 10
    is_public: bool = False

    @field_validator("amount_fcfa")
    @classmethod
    def validate_amount(cls, v: int) -> int:
        if v < 500:
            raise ValueError("Le montant minimum est 500 FCFA")
        return v

    @field_validator("frequency_days")
    @classmethod
    def validate_frequency(cls, v: int) -> int:
        if v not in [7, 14, 30]:
            raise ValueError("Fréquence invalide. Valeurs acceptées : 7, 14, 30 jours")
        return v

    @field_validator("max_members")
    @classmethod
    def validate_members(cls, v: int) -> int:
        if not 2 <= v <= 20:
            raise ValueError("Le groupe doit avoir entre 2 et 20 membres")
        return v


class GroupOut(BaseModel):
    id: UUID
    name: str
    amount_fcfa: int
    frequency_days: int
    max_members: int
    current_round: int
    is_public: bool
    invite_code: Optional[str] = None
    creator_id: UUID
    member_count: int = 1
    start_date: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class GroupJoin(BaseModel):
    invite_code: str


class GroupListOut(BaseModel):
    groups: List[GroupOut]
    total: int
