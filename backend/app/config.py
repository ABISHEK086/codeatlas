from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./codeatlas.db"
    jwt_secret: str = "dev-secret"
    github_client_id: str = ""
    github_client_secret: str = ""
    groq_api_key: str = ""
    token_encryption_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    llm_max_steps: int = 6
    embedding_dim: int = 384
    backend_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:5173"
    max_commits: int = 50

    # Deployment settings
    cookie_secure: bool = False          # set True on HTTPS
    cors_origins: str = "http://localhost:5173,http://localhost:3000"  # comma-separated


settings = Settings()