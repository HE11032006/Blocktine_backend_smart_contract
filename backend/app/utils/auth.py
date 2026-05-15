import secrets
import string
from jose import jwt, JWTError
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.config import settings
from app.database import get_db
from app.models.user import User

bearer_scheme = HTTPBearer()


def generate_invite_code(length: int = 8) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    token = credentials.credentials
    try:
        
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256", "HS384", "HS512", "ES256"],
            options={"verify_aud": False, "verify_signature": False},
        )
        supabase_id: str = payload.get("sub")
        if not supabase_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalide")
    except JWTError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Token invalide: {str(e)}")

    user = db.query(User).filter(User.supabase_auth_id == supabase_id).first()
    if not user:
        # Auto-create user for seamless integration with Supabase Auth
        email = payload.get("email", "")
        # Get name from user_metadata if available
        user_metadata = payload.get("user_metadata", {})
        full_name = user_metadata.get("full_name", email.split("@")[0] if email else "User")
        
        user = User(
            supabase_auth_id=supabase_id,
            email=email,
            full_name=full_name,
            phone_number=user_metadata.get("phone"),
            wallet_address=f"0x{supabase_id[:8]}{secrets.token_hex(16)}" # Simulation de wallet
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        
    return user
