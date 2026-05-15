import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Boolean, Text
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class WebhookLog(Base):
    __tablename__ = "webhook_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider = Column(String, nullable=False)          # flutterwave | polygon
    idempotency_key = Column(String, unique=True, nullable=False, index=True)
    payload = Column(Text, nullable=False)
    received_at = Column(DateTime, default=datetime.utcnow)
    processed = Column(Boolean, default=False)
