import json
import hmac
import hashlib
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime

from app.models.payment import Payment
from app.models.webhook_log import WebhookLog
from app.config import settings


def make_flw_signature(payload: bytes) -> str:
    return hmac.new(
        settings.flutterwave_webhook_secret.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()


# ── Test 1 : Paiement réussi → webhook → DB confirmée ─────────────────────────
def test_payment_confirmed_via_webhook(client, db, sample_user, sample_group, sample_round):
    # Créer un paiement pending
    payment = Payment(
        user_id=sample_user.id,
        group_id=sample_group.id,
        round_id=sample_round.id,
        amount_fcfa=5000,
        flutterwave_ref="TF-ABC123",
        status="pending",
    )
    db.add(payment)
    db.commit()

    payload = {
        "event": "charge.completed",
        "data": {
            "status": "successful",
            "tx_ref": "TF-ABC123",
            "id": "FLW-12345",
        },
    }
    body = json.dumps(payload).encode()
    sig = make_flw_signature(body)

    with patch("app.routes.webhooks.process_confirmed_payment") as mock_task:
        response = client.post(
            "/webhook/flutterwave",
            content=body,
            headers={"verif-hash": sig, "Content-Type": "application/json"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "received"
    mock_task.assert_called_once()


# ── Test 2 : Idempotence — webhook reçu deux fois ─────────────────────────────
def test_webhook_idempotence(client, db, sample_user, sample_group, sample_round):
    payment = Payment(
        user_id=sample_user.id,
        group_id=sample_group.id,
        round_id=sample_round.id,
        amount_fcfa=5000,
        flutterwave_ref="TF-IDEM01",
        status="pending",
    )
    db.add(payment)
    db.commit()

    payload = {
        "event": "charge.completed",
        "data": {"status": "successful", "tx_ref": "TF-IDEM01", "id": "FLW-99"},
    }
    body = json.dumps(payload).encode()
    sig = make_flw_signature(body)

    # Premier envoi
    r1 = client.post("/webhook/flutterwave", content=body, headers={"verif-hash": sig})
    assert r1.status_code == 200

    # Deuxième envoi identique
    r2 = client.post("/webhook/flutterwave", content=body, headers={"verif-hash": sig})
    assert r2.status_code == 200
    assert r2.json()["status"] == "already_processed"


# ── Test 3 : Membre paie deux fois → refusé ───────────────────────────────────
def test_double_payment_rejected(client, db, sample_user, sample_group, sample_round):
    # Simuler un paiement déjà confirmé
    existing = Payment(
        user_id=sample_user.id,
        group_id=sample_group.id,
        round_id=sample_round.id,
        amount_fcfa=5000,
        flutterwave_ref="TF-EXIST",
        status="confirmed",
    )
    db.add(existing)
    db.commit()

    # Mock le JWT
    with patch("app.utils.auth.get_current_user", return_value=sample_user):
        response = client.post(
            "/payment/initiate",
            json={
                "group_id": str(sample_group.id),
                "round_id": str(sample_round.id),
            },
        )

    assert response.status_code == 409
    assert "déjà initié" in response.json()["detail"]


# ── Test 4 : Signature webhook invalide ───────────────────────────────────────
def test_invalid_webhook_signature(client):
    payload = json.dumps({"event": "charge.completed", "data": {}}).encode()
    response = client.post(
        "/webhook/flutterwave",
        content=payload,
        headers={"verif-hash": "invalidsignature", "Content-Type": "application/json"},
    )
    assert response.status_code == 401
    assert "Signature" in response.json()["detail"]


# ── Test 5 : Admin skip round ─────────────────────────────────────────────────
def test_admin_can_skip_round(client, db, sample_user, sample_group, sample_round):
    with patch("app.utils.auth.get_current_user", return_value=sample_user):
        response = client.post(
            "/admin/skip_round",
            json={
                "group_id": str(sample_group.id),
                "round_id": str(sample_round.id),
                "reason": "Litige entre membres",
            },
        )
    assert response.status_code == 200
    assert response.json()["message"] == f"Tour #1 marqué comme sauté"

    db.refresh(sample_round)
    assert sample_round.status == "skipped"


# ── Test 6 : Non-admin ne peut pas skip ───────────────────────────────────────
def test_non_admin_cannot_skip_round(client, db, sample_group, sample_round):
    other_user = MagicMock()
    other_user.id = "00000000-0000-0000-0000-000000000999"

    with patch("app.utils.auth.get_current_user", return_value=other_user):
        response = client.post(
            "/admin/skip_round",
            json={
                "group_id": str(sample_group.id),
                "round_id": str(sample_round.id),
                "reason": "Tentative non autorisée",
            },
        )
    assert response.status_code == 403


# ── Test 7 : Webhook timeout puis confirmation tardive ────────────────────────
def test_late_webhook_still_confirms(client, db, sample_user, sample_group, sample_round):
    """Simule un webhook reçu longtemps après l'initiation."""
    payment = Payment(
        user_id=sample_user.id,
        group_id=sample_group.id,
        round_id=sample_round.id,
        amount_fcfa=5000,
        flutterwave_ref="TF-LATE01",
        status="pending",
    )
    db.add(payment)
    db.commit()

    payload = {
        "event": "charge.completed",
        "data": {"status": "successful", "tx_ref": "TF-LATE01"},
    }
    body = json.dumps(payload).encode()
    sig = make_flw_signature(body)

    with patch("app.routes.webhooks.process_confirmed_payment") as mock_task:
        response = client.post(
            "/webhook/flutterwave",
            content=body,
            headers={"verif-hash": sig},
        )

    assert response.status_code == 200
    mock_task.assert_called_once_with(str(payment.id), pytest.approx(db, abs=None))
