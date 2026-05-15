import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class PaymentJob(Base):
    """
    File de jobs persistante pour le traitement des webhooks Flutterwave.
    Remplace BackgroundTasks (volatile) par un système crash-safe.

    Lifecycle :
      pending → processing → done
                           → failed (retry < max_retries)
                           → dead   (retry >= max_retries)
    """
    __tablename__ = "payment_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    payment_id = Column(String, nullable=False, index=True)
    status = Column(String, default="pending", index=True)  # pending | processing | done | failed | dead
    attempts = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    next_retry_at = Column(DateTime, default=datetime.utcnow)  # backoff exponentiel
    processed_at = Column(DateTime, nullable=True)
