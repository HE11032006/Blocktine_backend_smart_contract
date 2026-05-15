from app.database import engine
from sqlalchemy import text
import secrets

def update():
    with engine.connect() as conn:
        # On récupère tous les users pour leur mettre un vrai format de wallet
        users = conn.execute(text("SELECT id, supabase_auth_id FROM users")).all()
        for user in users:
            new_wallet = f"0x{str(user.supabase_auth_id)[:8]}{secrets.token_hex(16)}"
            conn.execute(
                text("UPDATE users SET wallet_address = :w WHERE id = :id"),
                {"w": new_wallet, "id": user.id}
            )
        conn.commit()
    print('Wallets (longueur 42) mis à jour !')

if __name__ == "__main__":
    update()
