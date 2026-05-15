import logging
import uuid
import time
from typing import Dict, Any
from app.services.base_payment import BasePaymentService

logger = logging.getLogger(__name__)

class PaymentMockService(BasePaymentService):
    def __init__(self):
        logger.info("[Mock] PaymentMockService initialisé")

    def initiate_fiat_to_crypto(
        self, amount_fcfa: float, phone_number: str, wallet_address: str, tx_ref: str
    ) -> Dict[str, Any]:
        """Simule l'initiation d'un paiement."""
        logger.info(f"[Mock] Initiation paiement: {amount_fcfa} FCFA pour {phone_number}")
        
        # Simuler un délai réseau
        time.sleep(0.5)

        return {
            "status": "success",
            "transactionId": f"MOCK-TX-{uuid.uuid4().hex[:8].upper()}",
            "message": "Paiement Mobile Money initié avec succès (MOCK)",
            "data": {
                "tx_ref": tx_ref,
                "status": "pending"
            }
        }

    def verify_transaction(self, tx_ref: str) -> Dict[str, Any]:
        """
        Simule la vérification.
        Si tx_ref contient 'ERR', on simule un échec pour la démo.
        """
        logger.info(f"[Mock] Vérification transaction: {tx_ref}")
        
        if "ERR" in tx_ref:
            return {
                "status": "failed",
                "transactionStatus": "FAILED",
                "message": "Échec simulé pour la démonstration"
            }
        
        return {
            "status": "success",
            "transactionStatus": "COMPLETED",
            "amount": 1000,
            "currency": "XOF"
        }

    def get_usdc_rate(self) -> float:
        """Taux fixe pour la démo."""
        return 655.957 # Taux Franc CFA fixe
