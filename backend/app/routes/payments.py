import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from datetime import datetime

from app.database import get_db
from app.models.user import User
from app.models.group import Group
from app.models.member import Member
from app.models.payment import Payment
from app.schemas.payment import PaymentInitiate, PaymentOut, BalanceOut
from app.utils.auth import get_current_user
from app.services import get_payment_service
from app.services.blockchain_service import BlockchainService
from app.config import settings
import httpx
import time

router = APIRouter()
payment_service = get_payment_service()
blockchain = BlockchainService()


@router.get("/balance", response_model=BalanceOut)
def get_balance(current_user: User = Depends(get_current_user)):
    if not current_user.wallet_address:
        return BalanceOut(
            wallet_address="Non configuré",
            balance_usdc="0.00",
        )
    balance = blockchain.get_balance_usdc(current_user.wallet_address)
    return BalanceOut(
        wallet_address=current_user.wallet_address,
        balance_usdc=balance,
    )


def simulate_mock_webhook(tx_ref: str, phone_number: str):
    """Simule un appel de webhook après quelques secondes (mode mock)."""
    time.sleep(5)
    payload = {
        "event": "transaction.completed",
        "data": {
            "transactionId": f"MOCK-{tx_ref}",
            "status": "success",
            "phoneNumber": phone_number,
            "metadata": {"tx_ref": tx_ref},
        },
    }
    try:
        with httpx.Client() as client:
            client.post(
                "http://localhost:8000/webhook/kotani",
                json=payload,
                headers={"x-kotani-signature": "mock-signature"},
            )
    except Exception as e:
        print(f"[Mock Webhook] Erreur: {e}")


@router.post("/initiate", response_model=PaymentOut)
def initiate_payment(
    payload: PaymentInitiate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # ── 1. Vérifier membership ────────────────────────────────────────────────
    member = db.query(Member).filter(
        Member.group_id == payload.group_id,
        Member.user_id == current_user.id,
        Member.is_active == True,
    ).first()
    if not member:
        raise HTTPException(status_code=403, detail="Vous n'êtes pas membre de ce groupe")

    group = db.query(Group).filter(Group.id == payload.group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Groupe introuvable")

    # ── 2. Idempotence — uniquement sur les paiements CONFIRMÉS ───────────────
    # On ne bloque PAS sur "pending" car un pending peut être orphelin
    # (session précédente sans webhook reçu). On laisse créer un nouveau
    # paiement et on expire les anciens pending.
    #
    # Si round_id fourni : vérifier confirmed pour ce round précis
    # Si round_id absent : vérifier confirmed pour ce groupe (tour en cours)
    confirmed_query = db.query(Payment).filter(
        Payment.user_id == current_user.id,
        Payment.group_id == payload.group_id,
        Payment.status == "confirmed",
    )
    if payload.round_id is not None:
        confirmed_query = confirmed_query.filter(Payment.round_id == payload.round_id)

    already_confirmed = confirmed_query.first()
    if already_confirmed:
        raise HTTPException(
            status_code=409,
            detail="Paiement déjà confirmé pour ce tour",
        )

    # ── 3. Expirer les anciens pending orphelins pour ce user/groupe ──────────
    # Un pending de plus de 30 minutes sans confirmation = orphelin
    from datetime import timedelta
    cutoff = datetime.utcnow() - timedelta(minutes=30)
    orphan_pendings = db.query(Payment).filter(
        Payment.user_id == current_user.id,
        Payment.group_id == payload.group_id,
        Payment.status == "pending",
        Payment.created_at < cutoff,
    )
    if payload.round_id is not None:
        orphan_pendings = orphan_pendings.filter(Payment.round_id == payload.round_id)

    orphan_count = orphan_pendings.count()
    if orphan_count > 0:
        orphan_pendings.update({"status": "failed"}, synchronize_session=False)
        db.commit()

    # ── 4. Vérifier s'il y a un pending récent (< 30 min) ────────────────────
    # Évite de spammer Kotani si l'utilisateur reclique trop vite
    recent_pending_query = db.query(Payment).filter(
        Payment.user_id == current_user.id,
        Payment.group_id == payload.group_id,
        Payment.status == "pending",
        Payment.created_at >= cutoff,
    )
    if payload.round_id is not None:
        recent_pending_query = recent_pending_query.filter(
            Payment.round_id == payload.round_id
        )

    recent_pending = recent_pending_query.first()
    if recent_pending:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Un paiement est déjà en attente (initié à "
                f"{recent_pending.created_at.strftime('%H:%M:%S')}). "
                "Attendez la confirmation ou réessayez dans 30 minutes."
            ),
        )

    # ── 5. Créer le paiement ──────────────────────────────────────────────────
    tx_ref = f"TF-{uuid.uuid4().hex[:12].upper()}"

    kotani_response = payment_service.initiate_fiat_to_crypto(
        amount_fcfa=group.amount_fcfa,
        phone_number=payload.phone_number,
        wallet_address=blockchain.account.address,
        tx_ref=tx_ref,
    )

    if kotani_response.get("error"):
        raise HTTPException(
            status_code=502,
            detail=f"Erreur Kotani Pay : {kotani_response.get('message', 'Inconnu')}",
        )

    payment = Payment(
        user_id=current_user.id,
        group_id=payload.group_id,
        round_id=payload.round_id,
        amount_fcfa=group.amount_fcfa,
        kotani_ref=tx_ref,
        status="pending",
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)

    # Mode mock : simuler le webhook automatiquement
    if settings.payment_mode == "mock":
        background_tasks.add_task(
            simulate_mock_webhook, tx_ref, payload.phone_number
        )

    return payment


@router.get("/group/{group_id}", response_model=List[PaymentOut])
def get_group_payments(
    group_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return (
        db.query(Payment)
        .filter(Payment.group_id == group_id)
        .order_by(Payment.created_at.desc())
        .all()
    )
