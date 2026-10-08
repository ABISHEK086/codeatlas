from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./codeatlas.db"
    jwt_secret: str = "dev-secret"
    github_client_id: str = ""
    github_client_secret: str = ""
    groq_api_key: str = ""
    embedding_dim: int = 384
    backend_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:8000/auth/me"
    max_commits: int = 50


settings = Settings()