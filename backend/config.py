from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True

    cache_ttl_stock: int = 300
    cache_ttl_news: int = 600
    cache_ttl_scoring: int = 300

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
