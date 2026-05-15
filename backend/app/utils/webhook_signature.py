import hmac
import hashlib
from app.config import settings


def verify_kotani_signature(payload: bytes, signature: str) -> bool:
    """Vérifie la signature HMAC-SHA256 du webhook Kotani Pay."""
    if not settings.kotani_webhook_secret:
        return True # Pour le dev si non configuré
    expected = hmac.new(
        settings.kotani_webhook_secret.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def fcfa_to_usdc(amount_fcfa: int, rate: float) -> float:
    """Convertit un montant FCFA en USDC selon le taux fourni."""
    return round(amount_fcfa / rate, 6)
