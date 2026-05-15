import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base


class Payment(Base):
    __tablename__ = "payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    group_id = Column(UUID(as_uuid=True), ForeignKey("groups.id"), nullable=False)
    round_id = Column(UUID(as_uuid=True), ForeignKey("rounds.id"), nullable=True)
    amount_fcfa = Column(Integer, nullable=False)
    amount_usdc = Column(Numeric(18, 6), nullable=True)
    tx_hash = Column(String, nullable=True)           # hash tx blockchain
    kotani_ref = Column(String, unique=True, nullable=True)  # idempotency key
    status = Column(String, default="pending")        # pending | confirmed | failed
    created_at = Column(DateTime, default=datetime.utcnow)
    confirmed_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="payments")
    group = relationship("Group", back_populates="payments")
    round = relationship("Round", back_populates="payments")
