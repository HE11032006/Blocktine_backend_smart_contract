import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base


class Group(Base):
    __tablename__ = "groups"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    amount_fcfa = Column(Integer, nullable=False)
    frequency_days = Column(Integer, nullable=False)  # 7=hebdo, 30=mensuel
    max_members = Column(Integer, nullable=False, default=10)
    current_round = Column(Integer, default=0)
    start_date = Column(DateTime, nullable=True)
    is_public = Column(Boolean, default=False)
    invite_code = Column(String, unique=True, nullable=True)
    creator_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    contract_group_id = Column(Integer, nullable=True)  # ID dans le smart contract
    created_at = Column(DateTime, default=datetime.utcnow)

    creator = relationship("User", back_populates="created_groups")
    members = relationship("Member", back_populates="group")
    rounds = relationship("Round", back_populates="group")
    payments = relationship("Payment", back_populates="group")
