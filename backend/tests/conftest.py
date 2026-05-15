import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database import Base, get_db
from app.models.user import User
from app.models.group import Group
from app.models.member import Member
from app.models.round import Round
from app.models.payment import Payment
from app.models.webhook_log import WebhookLog

# ── DB en mémoire pour les tests ──────────────────────────────────────────────
SQLALCHEMY_TEST_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_TEST_URL, connect_args={"check_same_thread": False})
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db():
    db = TestSessionLocal()
    yield db
    db.close()


@pytest.fixture
def sample_user(db):
    user = User(
        phone_number="+22961000001",
        full_name="Test User",
        supabase_auth_id="supabase-test-uid",
        wallet_address="0x1234567890123456789012345678901234567890",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def sample_group(db, sample_user):
    group = Group(
        name="Tontine Test",
        amount_fcfa=5000,
        frequency_days=30,
        max_members=5,
        invite_code="TESTCODE",
        creator_id=sample_user.id,
    )
    db.add(group)
    db.flush()
    member = Member(group_id=group.id, user_id=sample_user.id, reception_rank=1)
    db.add(member)
    db.commit()
    db.refresh(group)
    return group


@pytest.fixture
def sample_round(db, sample_group):
    from datetime import datetime
    round_ = Round(
        group_id=sample_group.id,
        round_number=1,
        scheduled_date=datetime.utcnow(),
        status="pending",
    )
    db.add(round_)
    db.commit()
    db.refresh(round_)
    return round_
