from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    api_key: str = ""

    jwt_secret: str = ""       # JWT 서명 키 (비어있으면 JWT 비활성)
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60  # 토큰 만료 시간

    cors_origins: str = "http://localhost:8000"
    rate_limit_per_minute: int = 60

    cache_ttl_stock: int = 300
    cache_ttl_news: int = 600
    cache_ttl_scoring: int = 300

    database_url: str = ""  # 비어있으면 DB 비활성화 (기존 동작 유지)

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
