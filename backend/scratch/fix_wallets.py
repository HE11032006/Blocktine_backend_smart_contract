from app.database import engine
from sqlalchemy import text

def update():
    with engine.connect() as conn:
        conn.execute(text("UPDATE users SET wallet_address = '0x' || substring(supabase_auth_id::text from 1 for 8) || '0000000000' WHERE wallet_address IS NULL"))
        conn.commit()
    print('Wallets mis à jour !')

if __name__ == "__main__":
    update()
