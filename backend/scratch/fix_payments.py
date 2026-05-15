from app.database import engine
from sqlalchemy import text

def update():
    with engine.connect() as conn:
        conn.execute(text('ALTER TABLE payments ALTER COLUMN round_id DROP NOT NULL'))
        conn.commit()
    print('Colonne round_id mise à jour !')

if __name__ == "__main__":
    update()
