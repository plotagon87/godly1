from pydantic import BaseSettings, Field

class Settings(BaseSettings):
    BOT_TOKEN: str = Field(..., env="BOT_TOKEN")
    ADMIN_CHAT_ID: int = Field(..., env="ADMIN_CHAT_ID")
    MONGO_URI: str = Field(..., env="MONGO_URI")
    MONGO_DB_NAME: str = Field(..., env="MONGO_DB_NAME")
    SUBSCRIPTION_FEE: int = 5000
    RENEWAL_DAY: int = 25
    REFERRAL_REWARD: int = 2000

    class Config:
        env_file = ".env"

settings = Settings()