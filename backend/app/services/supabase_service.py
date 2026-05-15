from supabase import create_client, Client
from app.config import settings


def get_supabase_client() -> Client:
    return create_client(settings.supabase_url, settings.supabase_key)


class SupabaseService:
    def __init__(self):
        self.client: Client = get_supabase_client()

    def send_otp(self, phone_number: str) -> dict:
        """Envoie un OTP par SMS via Supabase Auth."""
        response = self.client.auth.sign_in_with_otp({"phone": phone_number})
        return response

    def verify_otp(self, phone_number: str, token: str) -> dict:
        """Vérifie l'OTP et retourne la session Supabase."""
        response = self.client.auth.verify_otp(
            {"phone": phone_number, "token": token, "type": "sms"}
        )
        return response

    def get_user(self, jwt_token: str) -> dict:
        """Récupère l'utilisateur Supabase depuis son JWT."""
        response = self.client.auth.get_user(jwt_token)
        return response
