from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Supabase
    supabase_url: str
    supabase_key: str
    supabase_jwt_secret: str

    # Kotani Pay
    kotani_api_key: str
    kotani_base_url: str = "https://sandbox-api.kotanipay.io/api/v3"
    kotani_webhook_secret: str

    # Polygon / Web3
    polygon_rpc_url: str
    private_key: str
    contract_address: str
    usdc_token_address: str

    # Database
    database_url: str

    # App
    environment: str = "development"
    payment_mode: str = "live" # live | mock

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
