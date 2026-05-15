"""
Tests — Webhook crash-safe avec PaymentJob
"""
import json
import hmac
import hashlib
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from app.models.payment import Payment
from app.models.payment_job import PaymentJob
from app.models.webhook_log import WebhookLog
from app.services.webhook_processor import (
    enqueue_payment_job,
    process_pending_jobs,
    retry_dead_jobs,
    _process_single_job,
)
from app.config import settings


def make_sig(payload: bytes) -> str:
    return hmac.new(
        settings.flutterwave_webhook_secret.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()


# ── Test 1 : Webhook crée un job persistant ───────────────────────────────────
def test_webhook_creates_persistent_job(client, db, sample_user, sample_group, sample_round):
    payment = Payment(
        user_id=sample_user.id,
        group_id=sample_group.id,
        round_id=sample_round.id,
        amount_fcfa=5000,
        flutterwave_ref="TF-JOB001",
        status="pending",
    )
    db.add(payment)
    db.commit()

    payload = {
        "event": "charge.completed",
        "data": {"status": "successful", "tx_ref": "TF-JOB001"},
    }
    body = json.dumps(payload).encode()

    with patch("app.routes.webhooks.process_pending_jobs"):
        response = client.post(
            "/webhook/flutterwave",
            content=body,
            headers={"verif-hash": make_sig(body)},
        )

    assert response.status_code == 200

    # Vérifier que le job a été créé en DB
    job = db.query(PaymentJob).filter(PaymentJob.payment_id == str(payment.id)).first()
    assert job is not None
    assert job.status == "pending"
    assert job.attempts == 0


# ── Test 2 : Idempotence — job non dupliqué ───────────────────────────────────
def test_enqueue_is_idempotent(db, sample_user, sample_group, sample_round):
    payment = Payment(
        user_id=sample_user.id,
        group_id=sample_group.id,
        round_id=sample_round.id,
        amount_fcfa=5000,
        flutterwave_ref="TF-IDEM02",
        status="pending",
    )
    db.add(payment)
    db.commit()

    job1 = enqueue_payment_job(str(payment.id), db)
    job2 = enqueue_payment_job(str(payment.id), db)

    # Même job retourné, pas de doublon
    assert str(job1.id) == str(job2.id)
    count = db.query(PaymentJob).filter(PaymentJob.payment_id == str(payment.id)).count()
    assert count == 1


# ── Test 3 : Job traité avec succès ───────────────────────────────────────────
def test_process_job_confirms_payment(db, sample_user, sample_group, sample_round):
    payment = Payment(
        user_id=sample_user.id,
        group_id=sample_group.id,
        round_id=sample_round.id,
        amount_fcfa=5000,
        flutterwave_ref="TF-PROC01",
        status="pending",
    )
    db.add(payment)
    db.commit()

    job = PaymentJob(payment_id=str(payment.id))
    db.add(job)
    db.commit()

    with patch("app.services.webhook_processor.flw") as mock_flw, \
         patch("app.services.webhook_processor.blockchain") as mock_bc:

        mock_flw.verify_transaction.return_value = {
            "data": {"status": "successful"}
        }
        mock_flw.get_usdc_rate.return_value = 600.0
        mock_bc.contract = None  # Pas de blockchain pour ce test

        _process_single_job(str(job.id))

    db.refresh(payment)
    db.refresh(job)
    assert payment.status == "confirmed"
    assert payment.amount_usdc is not None
    assert job.status == "done"
    assert job.processed_at is not None


# ── Test 4 : Retry après échec — backoff correct ──────────────────────────────
def test_job_retries_with_backoff(db, sample_user, sample_group, sample_round):
    payment = Payment(
        user_id=sample_user.id,
        group_id=sample_group.id,
        round_id=sample_round.id,
        amount_fcfa=5000,
        flutterwave_ref="TF-RETRY01",
        status="pending",
    )
    db.add(payment)
    db.commit()

    job = PaymentJob(payment_id=str(payment.id))
    db.add(job)
    db.commit()

    with patch("app.services.webhook_processor.flw") as mock_flw, \
         patch("app.services.webhook_processor.blockchain"):
        mock_flw.verify_transaction.side_effect = Exception("Timeout Flutterwave")

        _process_single_job(str(job.id))

    db.refresh(job)
    assert job.status == "failed"
    assert job.attempts == 1
    assert job.next_retry_at > datetime.utcnow()
    assert "Timeout" in job.last_error


# ── Test 5 : Job mort après max_retries ───────────────────────────────────────
def test_job_becomes_dead_after_max_retries(db, sample_user, sample_group, sample_round):
    payment = Payment(
        user_id=sample_user.id,
        group_id=sample_group.id,
        round_id=sample_round.id,
        amount_fcfa=5000,
        flutterwave_ref="TF-DEAD01",
        status="pending",
    )
    db.add(payment)
    db.commit()

    job = PaymentJob(payment_id=str(payment.id), attempts=2, max_retries=3)
    db.add(job)
    db.commit()

    with patch("app.services.webhook_processor.flw") as mock_flw, \
         patch("app.services.webhook_processor.blockchain"):
        mock_flw.verify_transaction.side_effect = Exception("Erreur permanente")

        _process_single_job(str(job.id))

    db.refresh(job)
    assert job.status == "dead"
    assert job.attempts == 3


# ── Test 6 : retry_dead_jobs remet en pending ─────────────────────────────────
def test_retry_dead_jobs_requeues(db, sample_user, sample_group, sample_round):
    payment = Payment(
        user_id=sample_user.id,
        group_id=sample_group.id,
        round_id=sample_round.id,
        amount_fcfa=5000,
        flutterwave_ref="TF-RDEAD01",
        status="pending",
    )
    db.add(payment)
    db.commit()

    job = PaymentJob(
        payment_id=str(payment.id),
        status="dead",
        attempts=3,
        last_error="Erreur passée",
    )
    db.add(job)
    db.commit()

    count = retry_dead_jobs(db)

    assert count == 1
    db.refresh(job)
    assert job.status == "pending"
    assert job.attempts == 0
    assert job.last_error is None


# ── Test 7 : Crash recovery — job processing depuis >10min repris ─────────────
def test_crash_recovery_picks_up_stale_processing_job(db, sample_user, sample_group, sample_round):
    """
    Simule un job bloqué en 'processing' depuis 15 minutes (crash serveur).
    Le dispatcher doit le récupérer.
    """
    payment = Payment(
        user_id=sample_user.id,
        group_id=sample_group.id,
        round_id=sample_round.id,
        amount_fcfa=5000,
        flutterwave_ref="TF-CRASH01",
        status="pending",
    )
    db.add(payment)
    db.commit()

    stale_time = datetime.utcnow() - timedelta(minutes=15)
    job = PaymentJob(
        payment_id=str(payment.id),
        status="processing",
        attempts=1,
        created_at=stale_time,
    )
    db.add(job)
    db.commit()

    with patch("app.services.webhook_processor._process_single_job") as mock_process:
        process_pending_jobs()
        # Le job doit avoir été dispatché
        mock_process.assert_called()


# ── Test 8 : Job déjà confirmé — pas re-traité ────────────────────────────────
def test_already_confirmed_payment_skips_processing(db, sample_user, sample_group, sample_round):
    payment = Payment(
        user_id=sample_user.id,
        group_id=sample_group.id,
        round_id=sample_round.id,
        amount_fcfa=5000,
        flutterwave_ref="TF-DONE01",
        status="confirmed",
        confirmed_at=datetime.utcnow(),
    )
    db.add(payment)
    db.commit()

    job = PaymentJob(payment_id=str(payment.id))
    db.add(job)
    db.commit()

    with patch("app.services.webhook_processor.flw") as mock_flw:
        _process_single_job(str(job.id))
        # verify_transaction ne doit PAS être appelé
        mock_flw.verify_transaction.assert_not_called()

    db.refresh(job)
    assert job.status == "done"
