import json
from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.payment import Payment
from app.models.webhook_log import WebhookLog
from app.services.webhook_processor import enqueue_payment_job, process_pending_jobs
from app.utils.webhook_signature import verify_kotani_signature
from app.config import settings

router = APIRouter()


@router.post("/kotani")
async def kotani_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Réception du webhook Flutterwave.

    Philosophie crash-safe :
      1. Vérifier la signature (401 si invalide)
      2. Idempotence : refuser si déjà reçu
      3. Logger le webhook en DB (atomique)
      4. Enqueue un PaymentJob persistant (survit aux crashs)
      5. Dispatcher en BackgroundTask LÉGÈRE (juste pickup des jobs DB)
         → si crash ici, le job est en DB et sera repris au prochain appel
    """
    body = await request.body()
    signature = request.headers.get("x-kotani-signature", "")
    payload = json.loads(body)
    
    # Extraire les infos selon le format Kotani V3
    event = payload.get("event", "")
    data = payload.get("data", {})

    # ── 1. Signature (Bypass en mode Mock) ────────────────────────────────────
    if settings.payment_mode != "mock":
        if not verify_kotani_signature(body, signature):
            raise HTTPException(status_code=401, detail="Signature webhook Kotani invalide")
    elif signature != "mock-signature":
        # En mode mock, on accepte une signature spécifique simple
        if not verify_kotani_signature(body, signature):
            raise HTTPException(status_code=401, detail="Signature mock invalide")

    tx_ref = data.get("metadata", {}).get("tx_ref", "")
    if not tx_ref:
        tx_ref = data.get("transactionId", "") # Fallback

    # ── 2. Idempotence ────────────────────────────────────────────────────────
    idempotency_key = f"kotani-{tx_ref}-{event}"
    existing_log = db.query(WebhookLog).filter(
        WebhookLog.idempotency_key == idempotency_key
    ).first()

    if existing_log:
        return {"status": "already_processed"}

    # ── 3. Logger atomiquement ────────────────────────────────────────────────
    log = WebhookLog(
        provider="kotani",
        idempotency_key=idempotency_key,
        payload=json.dumps(payload),
        processed=False,
    )
    db.add(log)
    db.commit()

    # Kotani events: usually 'withdrawal.success' or 'transaction.completed'
    if event in ("withdrawal.success", "transaction.completed", "charge.completed"):
        payment = db.query(Payment).filter(
            Payment.kotani_ref == tx_ref
        ).first()

        if payment and payment.status == "pending":
            enqueue_payment_job(str(payment.id), db)

            # Marquer le log comme enqueued
            log.processed = True
            db.commit()

    # ── 5. Dispatcher léger en background ────────────────────────────────────
    # BackgroundTask ne fait qu'appeler le dispatcher DB —
    # si elle crashe, les jobs sont toujours en DB (pending) et seront
    # repris au prochain webhook ou par /admin/retry-failed-jobs
    background_tasks.add_task(process_pending_jobs)

    return {"status": "received"}
