from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    auth_service_url:      str = "http://127.0.0.1:8000"
    reporting_service_url: str = "http://127.0.0.1:8001"
    messaging_service_url:  str = "http://127.0.0.1:8002"
    secret_key:            str  # same key as auth service uses to sign JWTs
    algorithm:             str = "HS256"

    class Config:
        env_file = ".env"

settings = Settings()