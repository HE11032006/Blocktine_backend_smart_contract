import httpx
from app.config import settings


FLUTTERWAVE_BASE_URL = "https://api.flutterwave.com/v3"


class FlutterwaveService:
    def __init__(self):
        self.secret_key = settings.flutterwave_secret_key
        self.headers = {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json",
        }

    def initiate_mobile_money(
        self,
        amount_fcfa: int,
        phone_number: str,
        tx_ref: str,
        user_name: str,
        user_email: str = "noreply@tontine-flow.com",
        network: str = "MTN",
    ) -> dict:
        """
        Initie un paiement Mobile Money (MTN ou Moov Bénin).
        network: 'MTN' ou 'MOOV'
        """
        payload = {
            "amount": amount_fcfa,
            "currency": "XOF",
            "country": "BJ",
            "email": user_email,
            "phone_number": phone_number,
            "fullname": user_name,
            "tx_ref": tx_ref,
            "network": network,
            "redirect_url": "https://tontine-flow.vercel.app/payment/callback",
        }
        with httpx.Client() as client:
            response = client.post(
                f"{FLUTTERWAVE_BASE_URL}/charges?type=mobile_money_franco",
                json=payload,
                headers=self.headers,
                timeout=30,
            )
        return response.json()

    def verify_transaction(self, transaction_id: str) -> dict:
        """Vérifie le statut d'une transaction Flutterwave."""
        with httpx.Client() as client:
            response = client.get(
                f"{FLUTTERWAVE_BASE_URL}/transactions/{transaction_id}/verify",
                headers=self.headers,
                timeout=30,
            )
        return response.json()

    def get_usdc_rate(self) -> float:
        """
        Retourne le taux FCFA/USDC.
        En prod, utiliser un oracle ou l'API de change Flutterwave.
        Pour le testnet, on utilise un taux fixe approximatif.
        """
        # 1 USD ≈ 600 XOF (taux fixe CFA)
        # 1 USDC ≈ 1 USD
        return 600.0

    def initiate_payout(
        self,
        amount_fcfa: int,
        phone_number: str,
        bank_code: str,
        account_bank: str,
        beneficiary_name: str,
        reference: str,
    ) -> dict:
        """Envoie les fonds au gagnant via Mobile Money."""
        payload = {
            "account_bank": account_bank,
            "account_number": phone_number,
            "amount": amount_fcfa,
            "narration": "Tontine-Flow - Paiement cagnotte",
            "currency": "XOF",
            "reference": reference,
            "beneficiary_name": beneficiary_name,
        }
        with httpx.Client() as client:
            response = client.post(
                f"{FLUTTERWAVE_BASE_URL}/transfers",
                json=payload,
                headers=self.headers,
                timeout=30,
            )
        return response.json()
