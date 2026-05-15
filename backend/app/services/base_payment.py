from abc import ABC, abstractmethod
from typing import Dict, Any

class BasePaymentService(ABC):
    @abstractmethod
    def initiate_fiat_to_crypto(
        self, amount_fcfa: float, phone_number: str, wallet_address: str, tx_ref: str
    ) -> Dict[str, Any]:
        """Initie un dépôt Mobile Money vers Crypto."""
        pass

    @abstractmethod
    def verify_transaction(self, tx_ref: str) -> Dict[str, Any]:
        """Vérifie le statut d'une transaction chez le provider."""
        pass

    @abstractmethod
    def get_usdc_rate(self) -> float:
        """Récupère le taux de change actuel (ex: 1 USDC = 655 FCFA)."""
        pass
