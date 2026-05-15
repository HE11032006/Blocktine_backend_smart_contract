from datetime import datetime
from typing import Optional
from uuid import UUID
from decimal import Decimal
from pydantic import BaseModel


class PaymentInitiate(BaseModel):
    group_id: UUID
    round_id: Optional[UUID] = None


class PaymentOut(BaseModel):
    id: UUID
    user_id: UUID
    group_id: UUID
    round_id: Optional[UUID] = None
    amount_fcfa: int
    amount_usdc: Optional[Decimal] = None
    flutterwave_ref: Optional[str] = None
    tx_hash: Optional[str] = None
    status: str
    created_at: datetime
    confirmed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class FlutterwaveWebhookPayload(BaseModel):
    event: str
    data: dict


class RoundOut(BaseModel):
    id: UUID
    group_id: UUID
    round_number: int
    winner_user_id: Optional[UUID] = None
    scheduled_date: datetime
    status: str
    tx_hash_distribute: Optional[str] = None

    model_config = {"from_attributes": True}


class BalanceOut(BaseModel):
    wallet_address: str
    balance_usdc: str
    network: str = "Polygon Amoy"


class SkipRoundRequest(BaseModel):
    group_id: UUID
    round_id: UUID
    reason: str
