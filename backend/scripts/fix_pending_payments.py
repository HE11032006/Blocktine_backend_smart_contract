"""
Script one-shot : expire tous les paiements pending orphelins en base.
Lancer depuis le dossier backend/ :
  python scripts/fix_pending_payments.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.payment import Payment


def fix_pending_payments():
    db = SessionLocal()
    try:
        all_pending = db.query(Payment).filter(Payment.status == "pending").all()

        print(f"Paiements pending trouvés : {len(all_pending)}")
        for p in all_pending:
            print(f"  → {p.id} | user={p.user_id} | group={p.group_id} | créé={p.created_at}")

        if not all_pending:
            print("Rien à nettoyer.")
            return

        confirm = input("\nExpirer tous ces pending ? (oui/non) : ")
        if confirm.strip().lower() != "oui":
            print("Annulé.")
            return

        db.query(Payment).filter(Payment.status == "pending").update(
            {"status": "failed"}, synchronize_session=False
        )
        db.commit()
        print(f"✅ {len(all_pending)} paiements marqués 'failed'.")

    finally:
        db.close()


if __name__ == "__main__":
    fix_pending_payments()
