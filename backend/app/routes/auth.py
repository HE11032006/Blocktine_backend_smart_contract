from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.user import UserCreate, UserLogin, UserOut, TokenOut
from app.models.user import User
from app.services.supabase_service import SupabaseService

router = APIRouter()
supabase_service = SupabaseService()


@router.post("/signup", status_code=status.HTTP_201_CREATED)
def signup(payload: UserCreate, db: Session = Depends(get_db)):
    """Crée un utilisateur et envoie un OTP par SMS."""
    existing = db.query(User).filter(User.phone_number == payload.phone_number).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ce numéro est déjà enregistré",
        )

    # Envoyer OTP via Supabase
    try:
        supabase_service.send_otp(payload.phone_number)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Impossible d'envoyer l'OTP : {str(e)}",
        )

    # Créer l'utilisateur en base (sans supabase_auth_id pour l'instant)
    user = User(
        phone_number=payload.phone_number,
        full_name=payload.full_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return {"message": "OTP envoyé", "phone_number": payload.phone_number}


@router.post("/verify-otp", response_model=TokenOut)
def verify_otp(payload: UserLogin, db: Session = Depends(get_db)):
    """Vérifie l'OTP et retourne un JWT Supabase."""
    try:
        session = supabase_service.verify_otp(payload.phone_number, payload.otp_token)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"OTP invalide : {str(e)}",
        )

    supabase_user = session.user
    access_token = session.session.access_token

    # Lier le supabase_auth_id à l'utilisateur local
    user = db.query(User).filter(User.phone_number == payload.phone_number).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")

    if not user.supabase_auth_id:
        user.supabase_auth_id = supabase_user.id
        db.commit()
        db.refresh(user)

    return TokenOut(access_token=access_token, user=UserOut.model_validate(user))


@router.post("/request-otp")
def request_otp(phone_number: str):
    """Demande un nouvel OTP (pour connexion)."""
    try:
        supabase_service.send_otp(phone_number)
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))
    return {"message": "OTP envoyé"}
