from app.config import settings
from app.services.kotani_service import KotaniService
from app.services.mock_payment_service import PaymentMockService
from app.services.base_payment import BasePaymentService

def get_payment_service() -> BasePaymentService:
    if settings.payment_mode == "mock":
        return PaymentMockService()
    return KotaniService()

# Instance globale pour usage direct si besoin (attention aux cycles d'import)
payment_service = get_payment_service()
