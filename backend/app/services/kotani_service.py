import httpx
import logging
from app.config import settings
from app.services.base_payment import BasePaymentService

logger = logging.getLogger(__name__)

class KotaniService(BasePaymentService):
    def __init__(self):
        self.api_key = settings.kotani_api_key
        self.base_url = settings.kotani_base_url
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def initiate_fiat_to_crypto(
        self,
        amount_fcfa: int,
        phone_number: str,
        wallet_address: str,
        network: str = "MTN",
        tx_ref: str = None
    ) -> dict:
        """
        Initie un transfert Mobile Money (XOF) vers Crypto (USDC/CELO/etc).
        Dans Kotani Pay V3, c'est souvent l'endpoint 'withdrawals/mobile-money'.
        L'utilisateur "retire" de son MoMo vers la blockchain.
        """
        payload = {
            "amount": amount_fcfa,
            "currency": "XOF",
            "network": network.upper(),
            "phoneNumber": phone_number,
            "walletAddress": wallet_address,
            "callbackUrl": f"https://tontine-flow.render.com/webhook/kotani",
            "metadata": {
                "tx_ref": tx_ref
            }
        }
        
        try:
            with httpx.Client() as client:
                response = client.post(
                    f"{self.base_url}/withdrawals/mobile-money",
                    json=payload,
                    headers=self.headers,
                    timeout=30,
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Kotani Pay Error (Fiat->Crypto): {e.response.text}")
            return {"error": True, "message": e.response.text}
        except Exception as e:
            logger.error(f"Unexpected Error: {str(e)}")
            return {"error": True, "message": str(e)}

    def initiate_crypto_to_fiat(
        self,
        amount_crypto: float,
        phone_number: str,
        network: str = "MTN",
        tx_ref: str = None
    ) -> dict:
        """
        Initie un transfert Crypto vers Mobile Money (XOF).
        C'est l'endpoint 'deposits/mobile-money'.
        L'utilisateur "dépose" de la crypto pour recevoir du MoMo.
        """
        payload = {
            "amount": amount_crypto,
            "currency": "XOF", # Devise de réception
            "network": network.upper(),
            "phoneNumber": phone_number,
            "metadata": {
                "tx_ref": tx_ref
            }
        }
        
        try:
            with httpx.Client() as client:
                response = client.post(
                    f"{self.base_url}/deposits/mobile-money",
                    json=payload,
                    headers=self.headers,
                    timeout=30,
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Kotani Pay Error (Crypto->Fiat): {e.response.text}")
            return {"error": True, "message": e.response.text}

    def verify_transaction(self, transaction_id: str) -> dict:
        """Vérifie le statut d'une transaction Kotani."""
        try:
            with httpx.Client() as client:
                response = client.get(
                    f"{self.base_url}/transactions/{transaction_id}",
                    headers=self.headers,
                    timeout=30,
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Kotani Verification Error: {str(e)}")
            return {"error": True, "message": str(e)}

    def get_usdc_rate(self) -> float:
        """
        Retourne le taux de change.
        Kotani a un endpoint /rates pour cela.
        """
        try:
            with httpx.Client() as client:
                response = client.get(
                    f"{self.base_url}/rates?pair=XOF_USDC",
                    headers=self.headers
                )
                if response.status_code == 200:
                    return float(response.json().get("rate", 600.0))
        except:
            pass
        return 600.0 # Taux de repli
