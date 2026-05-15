from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime

from app.database import get_db
from app.models.user import User
from app.models.group import Group
from app.models.round import Round
from app.models.payment import Payment
from app.models.payment_job import PaymentJob
from app.schemas.payment import SkipRoundRequest
from app.utils.auth import get_current_user
from app.services.webhook_processor import retry_dead_jobs, process_pending_jobs
from app.services.blockchain_service import BlockchainService

router = APIRouter()


def require_group_admin(group_id: str, current_user: User, db: Session) -> Group:
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Groupe introuvable")
    if str(group.creator_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Réservé à l'admin du groupe")
    return group


@router.post("/skip_round")
def skip_round(
    payload: SkipRoundRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    group = require_group_admin(str(payload.group_id), current_user, db)
    round_ = db.query(Round).filter(
        Round.id == payload.round_id,
        Round.group_id == payload.group_id,
        Round.status == "pending",
    ).first()
    if not round_:
        raise HTTPException(status_code=404, detail="Tour introuvable ou déjà traité")
    round_.status = "skipped"
    db.commit()
    return {
        "message": f"Tour #{round_.round_number} marqué comme sauté",
        "reason": payload.reason,
        "round_id": str(round_.id),
    }


@router.post("/retry-failed-jobs")
def retry_failed_jobs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    count = retry_dead_jobs(db)
    processed = process_pending_jobs()
    return {"requeued": count, "processed_immediately": processed}


@router.get("/jobs/status")
def jobs_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    statuses = ["pending", "processing", "done", "failed", "dead"]
    result = {s: db.query(PaymentJob).filter(PaymentJob.status == s).count() for s in statuses}
    dead_jobs = db.query(PaymentJob).filter(PaymentJob.status == "dead").all()
    result["dead_details"] = [
        {
            "job_id": str(j.id),
            "payment_id": j.payment_id,
            "attempts": j.attempts,
            "last_error": j.last_error,
            "created_at": j.created_at.isoformat(),
        }
        for j in dead_jobs
    ]
    return result


@router.get("/debug/payments")
def debug_payments(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Diagnostic : tous les paiements en base avec leur statut.
    À supprimer avant la mise en production.
    """
    rows = db.query(Payment).order_by(Payment.created_at.desc()).limit(50).all()
    return [
        {
            "id": str(p.id),
            "user_id": str(p.user_id),
            "group_id": str(p.group_id),
            "round_id": str(p.round_id) if p.round_id else None,
            "status": p.status,
            "amount_fcfa": p.amount_fcfa,
            "kotani_ref": p.kotani_ref,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "confirmed_at": p.confirmed_at.isoformat() if p.confirmed_at else None,
        }
        for p in rows
    ]


@router.post("/debug/fix-pending")
def fix_pending_payments(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Force l'expiration de tous les paiements 'pending' en 'failed'.
    Utile pour débloquer une situation après des tests.
    À supprimer avant la mise en production.
    """
    pendings = db.query(Payment).filter(Payment.status == "pending").all()
    count = len(pendings)
    for p in pendings:
        p.status = "failed"
    db.commit()
    return {"fixed": count, "message": f"{count} paiements pending → failed"}


@router.post("/{group_id}/distribute")
def distribute_funds(
    group_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    group = require_group_admin(group_id, current_user, db)
    if group.contract_group_id is None:
        raise HTTPException(status_code=400, detail="Groupe non activé sur la blockchain")
    blockchain = BlockchainService()
    try:
        tx_hash = blockchain.distribute(group.contract_group_id)
        return {"status": "success", "tx_hash": tx_hash}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur Blockchain : {str(e)}")
