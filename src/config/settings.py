import os
from typing import List
from pydantic import Field
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Settings(BaseSettings):
    """Application settings"""

    # DeepSeek API Configuration
    deepseek_api_key: str = Field(..., env="DEEPSEEK_API_KEY")
    deepseek_api_base: str = Field("https://api.deepseek.com/v1", env="DEEPSEEK_API_BASE")

    # Gmail API Configuration
    gmail_credentials_path: str = Field("./credentials.json", env="GMAIL_CREDENTIALS_PATH")
    gmail_token_path: str = Field("./token.json", env="GMAIL_TOKEN_PATH")
    gmail_scopes: str = Field(
        "https://www.googleapis.com/auth/gmail.readonly,"
        "https://www.googleapis.com/auth/gmail.modify,"
        "https://www.googleapis.com/auth/gmail.compose",
        env="GMAIL_SCOPES"
    )

    # Database Configuration
    database_url: str = Field("sqlite:///email_agent.db", env="DATABASE_URL")

    # WeChat Notification
    wechat_webhook_url: str = Field("", env="WECHAT_WEBHOOK_URL")

    # Application Settings
    app_name: str = Field("EmailAgent", env="APP_NAME")
    log_level: str = Field("INFO", env="LOG_LEVEL")
    check_interval_seconds: int = Field(15, env="CHECK_INTERVAL_SECONDS")
    max_emails_per_check: int = Field(10, env="MAX_EMAILS_PER_CHECK")

    # Email Filter Settings
    blacklisted_domains: str = Field(
        "no-reply,newsletter,marketing,notification",
        env="BLACKLISTED_DOMAINS"
    )
    blacklisted_subjects: str = Field(
        "unsubscribe,newsletter,promotion,advertisement",
        env="BLACKLISTED_SUBJECTS"
    )
    min_content_length: int = Field(50, env="MIN_CONTENT_LENGTH")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

# Create global settings instance
settings = Settings()
