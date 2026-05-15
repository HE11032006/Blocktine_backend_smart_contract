"""
WebhookProcessor — Traitement crash-safe des paiements Flutterwave

Architecture :
  1. Webhook reçu → PaymentJob créé en DB (statut: pending)
  2. process_pending_jobs() tourne en BackgroundTask LÉGÈRE (juste dispatcher)
  3. Chaque job est traité avec retry + backoff exponentiel
  4. Si crash mid-job → statut reste "processing" → détecté au redémarrage
  5. /admin/retry-failed-jobs permet de forcer manuellement

Backoff : 1min → 5min → 15min (puis dead)
"""
import logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.payment import Payment
from app.models.payment_job import PaymentJob
from app.services import get_payment_service
from app.services.blockchain_service import BlockchainService

logger = logging.getLogger(__name__)

payment_service = get_payment_service()
blockchain = BlockchainService()

# Délais de retry en minutes (index = numéro de tentative)
RETRY_DELAYS_MINUTES = [1, 5, 15]


def enqueue_payment_job(payment_id: str, db: Session) -> PaymentJob:
    """
    Crée un job en DB pour traiter un paiement confirmé.
    Idempotent : si un job pending/processing existe déjà → on ne crée pas de doublon.
    """
    existing = db.query(PaymentJob).filter(
        PaymentJob.payment_id == payment_id,
        PaymentJob.status.in_(["pending", "processing", "done"]),
    ).first()

    if existing:
        logger.info(f"[Job] Job déjà existant pour payment {payment_id} ({existing.status})")
        return existing

    job = PaymentJob(payment_id=payment_id)
    db.add(job)
    db.commit()
    db.refresh(job)
    logger.info(f"[Job] Créé job {job.id} pour payment {payment_id}")
    return job


def _process_single_job(job_id: str) -> None:
    """
    Traite un seul job de paiement.
    Ouvre sa propre session DB — safe si appelé depuis un thread séparé.
    """
    db = SessionLocal()
    try:
        job = db.query(PaymentJob).filter(PaymentJob.id == job_id).first()
        if not job:
            logger.error(f"[Job] Job {job_id} introuvable")
            return

        if job.status not in ("pending", "failed"):
            logger.info(f"[Job] Job {job_id} ignoré (statut: {job.status})")
            return

        # Marquer comme en cours (détectable en cas de crash)
        job.status = "processing"
        job.attempts += 1
        db.commit()

        payment = db.query(Payment).filter(
            Payment.id == job.payment_id
        ).first()

        if not payment:
            raise ValueError(f"Payment {job.payment_id} introuvable")

        if payment.status == "confirmed":
            # Déjà traité (ex: race condition) → marquer done sans erreur
            job.status = "done"
            job.processed_at = datetime.utcnow()
            db.commit()
            return

        # ── Étape 1 : Vérifier la transaction côté Provider ────────────────────
        if payment.kotani_ref:
            verification = payment_service.verify_transaction(payment.kotani_ref)
            kotani_status = verification.get("status", "")
            if kotani_status != "success":
                raise ValueError(
                    f"Kotani status non confirmé : {kotani_status}"
                )

        # ── Étape 2 : Calculer le montant USDC ────────────────────────────────
        rate = payment_service.get_usdc_rate()
        payment.amount_usdc = round(payment.amount_fcfa / rate, 6)

        # ── Étape 3 : Dépôt blockchain (si contrat configuré) ─────────────────
        if (
            blockchain.contract is not None
            and payment.group is not None
            and payment.group.contract_group_id is not None
        ):
            try:
                # Récupérer le numéro du tour (round) pour la sécurité anti-replay
                expected_round = payment.round.round_number if payment.round else 0

                tx_hash = blockchain.deposit(
                    group_id=payment.group.contract_group_id,
                    expected_round=expected_round
                )
                payment.tx_hash = tx_hash
                logger.info(f"[Blockchain] Dépôt tx: {tx_hash}")
            except Exception as bc_err:
                # Erreur blockchain : on confirme le paiement en DB quand même
                # mais on log clairement pour intervention manuelle
                logger.error(
                    f"[Blockchain] Erreur dépôt pour payment {payment.id}: {bc_err}"
                )

        # ── Étape 4 : Confirmer en DB et Activer le Membre ─────────────────────
        payment.status = "confirmed"
        payment.confirmed_at = datetime.utcnow()

        # Activer le membre dans le groupe
        member = db.query(Member).filter(
            Member.user_id == payment.user_id,
            Member.group_id == payment.group_id
        ).first()
        
        if member:
            member.is_active = True
            logger.info(f"[Job] Membre {payment.user_id} activé dans le groupe {payment.group_id}")

        job.status = "done"
        job.processed_at = datetime.utcnow()
        job.last_error = None
        db.commit()

        logger.info(f"[Job] ✅ Job {job_id} terminé — payment {payment.id} confirmé")

    except Exception as e:
        db.rollback()
        logger.error(f"[Job] ❌ Erreur job {job_id} (tentative {job.attempts}): {e}")

        job = db.query(PaymentJob).filter(PaymentJob.id == job_id).first()
        if not job:
            return

        job.last_error = str(e)

        if job.attempts >= job.max_retries:
            job.status = "dead"
            logger.critical(
                f"[Job] 💀 Job {job_id} mort après {job.attempts} tentatives. "
                f"Payment {job.payment_id} nécessite une intervention manuelle."
            )
        else:
            # Backoff exponentiel
            delay_index = min(job.attempts - 1, len(RETRY_DELAYS_MINUTES) - 1)
            delay = RETRY_DELAYS_MINUTES[delay_index]
            job.status = "failed"
            job.next_retry_at = datetime.utcnow() + timedelta(minutes=delay)
            logger.warning(
                f"[Job] Retry dans {delay} min pour job {job_id} "
                f"(tentative {job.attempts}/{job.max_retries})"
            )

        db.commit()
    finally:
        db.close()


def process_pending_jobs() -> int:
    """
    Dispatcher léger — à appeler en BackgroundTask depuis les routes.
    Récupère tous les jobs éligibles et les traite séquentiellement.
    Retourne le nombre de jobs traités.

    Jobs éligibles :
      - statut "pending"
      - statut "failed" ET next_retry_at <= now
      - statut "processing" créé il y a plus de 10 min (crash recovery)
    """
    db = SessionLocal()
    processed = 0
    try:
        now = datetime.utcnow()
        crash_threshold = now - timedelta(minutes=10)

        jobs = db.query(PaymentJob).filter(
            (PaymentJob.status == "pending") |
            (
                (PaymentJob.status == "failed") &
                (PaymentJob.next_retry_at <= now)
            ) |
            (
                # Crash recovery : processing depuis trop longtemps
                (PaymentJob.status == "processing") &
                (PaymentJob.created_at <= crash_threshold)
            )
        ).order_by(PaymentJob.created_at).limit(20).all()

        job_ids = [str(j.id) for j in jobs]
        db.close()

        for job_id in job_ids:
            _process_single_job(job_id)
            processed += 1

    except Exception as e:
        logger.error(f"[Dispatcher] Erreur inattendue : {e}")
    finally:
        if not db.is_active:
            pass
        else:
            db.close()

    return processed


def retry_dead_jobs(db: Session) -> int:
    """
    Réinitialise les jobs morts pour une nouvelle tentative.
    Appelé par /admin/retry-failed-jobs.
    """
    dead_jobs = db.query(PaymentJob).filter(PaymentJob.status == "dead").all()
    for job in dead_jobs:
        job.status = "pending"
        job.attempts = 0
        job.last_error = None
        job.next_retry_at = datetime.utcnow()
    db.commit()
    logger.info(f"[Admin] {len(dead_jobs)} jobs morts remis en file")
    return len(dead_jobs)
