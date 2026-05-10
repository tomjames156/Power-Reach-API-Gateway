from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    auth_service_url:      str
    reporting_service_url: str
    messaging_service_url:  str
    messaging_service_ws_url: str
    notification_service_url: str
    notification_service_ws_url: str
    staff_frontend_url:      str
    customer_frontend_url:   str
    redis_url:               str
    secret_key:            str
    algorithm:             str = "HS256"

    class Config:
        env_file = ".env"

settings = Settings()