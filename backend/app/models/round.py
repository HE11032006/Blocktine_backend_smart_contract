import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base


class Round(Base):
    __tablename__ = "rounds"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    group_id = Column(UUID(as_uuid=True), ForeignKey("groups.id"), nullable=False)
    round_number = Column(Integer, nullable=False)
    winner_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    scheduled_date = Column(DateTime, nullable=False)
    status = Column(String, default="pending")  # pending | completed | skipped
    tx_hash_distribute = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    group = relationship("Group", back_populates="rounds")
    payments = relationship("Payment", back_populates="round")
